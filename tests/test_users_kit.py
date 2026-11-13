"""The users kit (FL-133): the page on which an administrator manages the other accounts.

Driven against a real MySQL (`test_db`), on the account kit's own test world:
a FastAPI app that mounts both routers from an adapter whose tables are named
like no real tool's. Every route is executed and what a person gets is
asserted: the page, the redirect, the row, the audit action and the mail.

One test per rule the owner decided on 12 November 2026 (README §11, "The
Users page"), and one per fault the fleet review found in the eight pages this
one replaces.
"""
from __future__ import annotations

import re
import sys

import pytest

from phronon_common import account_kit as kit_mod
from phronon_common import users_kit

from test_account_kit import PASSWORD, World, _tok  # the account kit's test world

USERS = "/backoffice/users"


class UsersWorld(World):
    """The account kit's world with the Users page mounted on it."""

    def __init__(self, get_db, tmp_path, roles=("admin", "educator"), users_adapter=None, **adapter):
        super().__init__(get_db, tmp_path, **adapter)
        self.owned: dict[int, int] = {}       # account id -> sessions it owns
        self.mail_ok = True
        mail = sys.modules[self._mail_name]

        def sender(name):
            def send(*args):
                self.mails.append((name, *args))
                return self.mail_ok
            return send
        for name in ("send_account_invitation", "send_password_reset",
                     "send_account_change_notice"):
            setattr(mail, name, sender(name))
        self.roles = roles
        self.users = users_kit.UsersKit(account=self.kit,
                                        session_counts=lambda: dict(self.owned),
                                        admin_role=roles[0], educator_role=roles[1],
                                        **(users_adapter or {}))
        self.app.include_router(users_kit.build_users_router(self.users))

    def admin(self, **cols):
        # With an authenticator: the account gate holds an administrator
        # without one to the enrolment page.
        return self.account(role=self.roles[0], **{"totp_enabled": 1, **cols})

    def educator(self, **cols):
        return self.account(role=self.roles[1], **cols)

    def by_email(self, email):
        return self.one(f"SELECT * FROM {self.T} WHERE email=%s", (email,))

    def sent(self, name):
        return [m for m in self.mails if m[0] == name]


@pytest.fixture
def world(test_db, tmp_path):
    made = []

    def build(**adapter):
        w = UsersWorld(test_db, tmp_path / f"u{len(made)}", **adapter)
        made.append(w)
        return w
    yield build
    for w in made:
        w.drop()


def _post(c, me, path, **data):
    return c.post(path, data={"csrf_token": _tok(me), **data})


def _where(r):
    assert r.status_code == 303, r.text
    return r.headers["location"]


def _path(template, uid):
    return template.replace("{user_id}", str(uid))


# ── who may ──────────────────────────────────────────────────────────────────

def test_the_router_answers_exactly_its_paths(world):
    w = world()
    served = {(r.path, m) for r in users_kit.build_users_router(w.users).routes
              for m in r.methods}
    assert {p for p, _m in served} == set(users_kit.PATHS)
    assert {p for p, m in served if m == "GET"} == set(users_kit.GET_PATHS)
    assert {p for p, m in served if m == "HEAD"} == set(users_kit.GET_PATHS)
    assert {p for p, m in served if m == "POST"} == set(users_kit.PATHS) - {USERS}


def test_only_an_administrator_reaches_any_of_it(world):
    """The read as well as every write: an educator who can open the list has
    the whole staff directory, whatever the buttons show (adminroutes.py)."""
    w = world()
    educator, other = w.educator(), w.educator()
    c, nobody = w.signed_in(educator), w.client()
    for path in users_kit.PATHS:
        path = _path(path, other["id"])
        if path == USERS or path.endswith("/edit"):
            assert c.get(path).status_code == 403, path
            assert _where(nobody.get(path)) == "/backoffice/login", path
        if path != USERS:
            r = _post(c, educator, path, display_name="X", email="x@example.invalid",
                      role="admin", action="deactivate", ids=str(other["id"]))
            assert r.status_code == 403, path
            assert _where(nobody.post(path, data={"csrf_token": "pre"})) == "/backoffice/login"
    after = w.row(other["id"])
    assert (after["is_active"], after["role"], after["email"]) == (1, "educator", other["email"])
    assert w.by_email("x@example.invalid") is None
    assert w.mails == [] and w.audits == []


def test_every_write_refuses_a_token_that_is_not_the_administrators(world):
    w = world()
    admin, other = w.admin(), w.educator()
    c = w.signed_in(admin)
    for path in set(users_kit.PATHS) - {USERS}:
        r = c.post(_path(path, other["id"]), data={"csrf_token": "acct-0", "action": "deactivate",
                                                   "ids": str(other["id"])})
        assert r.status_code == 400, path
    assert w.row(other["id"])["is_active"] == 1 and w.audits == []


# ── decision 1: a new account sets its own password from a mailed link ───────

def test_a_new_account_gets_a_link_and_nobody_types_its_password(world):
    w = world()
    admin = w.admin()
    c = w.signed_in(admin)
    page = c.get(USERS)
    assert page.status_code == 200 and 'action="/backoffice/users/invite"' in page.text
    assert 'type="password"' not in page.text, "the page asks the administrator for a password"

    r = _post(c, admin, users_kit.INVITE_URL, display_name="  Ada Lovelace ",
              email=" Ada@Example.Invalid ", role="educator")
    assert _where(r) == f"{USERS}?msg=invited"
    made = w.by_email("ada@example.invalid")
    assert made and (made["role"], made["is_active"], made["must_change_password"]) == (
        "educator", 1, 0)
    assert made[w.name_col] == "Ada Lovelace"
    (name, to, url, hours), = w.sent("send_account_invitation")
    assert to == "ada@example.invalid" and hours == 72
    assert url.startswith("https://kit.example/backoffice/password-reset?token=")
    left = w.one(f"SELECT TIMESTAMPDIFF(MINUTE, NOW(), expires_at) AS m FROM {w.RT} "
                 f"WHERE holder_id=%s", (made["id"],))["m"]
    assert 72 * 60 - 2 <= left <= 72 * 60, "the link does not live 72 hours"
    assert ("admin_created", admin["id"], str(made["id"])) == w.audits[-1][:3]
    assert w.audits[-1][3] == {"email": "ada@example.invalid", "role": "educator",
                               "invitation_sent": True}
    assert "72 hours" in c.get(_where(r)).text

    # The password nobody knows does not sign in; the link sets one that does.
    fresh = w.client()
    token = url.split("token=")[1]
    done = fresh.post("/backoffice/password-reset", data={
        "csrf_token": "pre", "token": token, "new_password": PASSWORD})
    assert "DONE[" in done.text, done.text
    w.reset_limits()
    signed = fresh.post("/backoffice/login", data={
        "csrf_token": "pre", "email": "ada@example.invalid", "password": PASSWORD})
    assert _where(signed) == "/backoffice/dashboard"


def test_an_invitation_that_could_not_be_mailed_leaves_no_link(world):
    """The fleet's rule for a mailed link: it is stored once the mail server
    has taken the mail, so a failed send leaves no live credential."""
    w = world()
    admin = w.admin()
    c = w.signed_in(admin)
    w.mail_ok = False
    r = _post(c, admin, users_kit.INVITE_URL, display_name="Bo", email="bo@example.invalid")
    assert _where(r) == f"{USERS}?msg=invited_unsent"
    made = w.by_email("bo@example.invalid")
    assert made and w.tokens(made["id"]) == []
    assert "could not be sent" in c.get(_where(r)).text
    assert w.audits[-1][3]["invitation_sent"] is False
    # "Send link" tries again, and says so when it still fails.
    assert _where(_post(c, admin, _path(users_kit.SEND_LINK_URL, made["id"]))) == f"{USERS}?err=mail"
    assert w.tokens(made["id"]) == [] and w.actions().count("admin_password_reset_sent") == 0
    w.mail_ok = True
    assert _where(_post(c, admin, _path(users_kit.SEND_LINK_URL, made["id"]))) == f"{USERS}?msg=link_sent"
    assert w.tokens(made["id"]) == [(0, 1)]


@pytest.mark.parametrize("sent, says", [
    (dict(display_name="", email="c@example.invalid"), "Enter a name."),
    (dict(display_name="Cy", email=""), "Enter an e-mail address."),
    (dict(display_name="Cy", email="not-an-address"), "does not look like an e-mail address"),
    (dict(display_name="Cy", email="c@example.invalid", role="owner"), "Choose a role"),
])
def test_a_form_with_a_mistake_comes_back_and_stores_nothing(world, sent, says):
    """OrgDesignSim's page accepted an empty address."""
    w = world()
    admin = w.admin()
    r = _post(w.signed_in(admin), admin, users_kit.INVITE_URL, **sent)
    assert r.status_code == 400 and says in r.text
    if sent["display_name"]:
        assert 'value="Cy"' in r.text, "what was typed is gone"
    assert w.one(f"SELECT COUNT(*) AS n FROM {w.T}")["n"] == 1
    assert w.mails == [] and w.audits == []


def test_an_address_that_has_an_account_is_refused(world):
    w = world()
    admin, other = w.admin(), w.educator()
    r = _post(w.signed_in(admin), admin, users_kit.INVITE_URL, display_name="Twin",
              email=other["email"].upper())
    assert r.status_code == 400 and "already uses that address" in r.text
    assert w.one(f"SELECT COUNT(*) AS n FROM {w.T}")["n"] == 2 and w.mails == []


# ── decision 5: a link, never a password ─────────────────────────────────────

def test_send_link_is_an_invitation_first_and_a_reset_afterwards(world):
    w = world()
    admin, person = w.admin(), w.educator()
    c = w.signed_in(admin)
    assert _where(_post(c, admin, _path(users_kit.SEND_LINK_URL, person["id"]))) == f"{USERS}?msg=link_sent"
    assert [m[0] for m in w.mails] == ["send_account_invitation"]
    w.run(f"UPDATE {w.T} SET last_login_at=NOW() WHERE id=%s", (person["id"],))
    assert _where(_post(c, admin, _path(users_kit.SEND_LINK_URL, person["id"]))) == f"{USERS}?msg=link_sent"
    assert [m[0] for m in w.mails] == ["send_account_invitation", "send_password_reset"]
    minutes = [r["m"] for r in w.all(
        f"SELECT TIMESTAMPDIFF(MINUTE, NOW(), expires_at) AS m FROM {w.RT} "
        f"WHERE holder_id=%s ORDER BY id", (person["id"],))]
    assert minutes[0] > 71 * 60 and 118 <= minutes[1] <= 120
    assert w.actions().count("admin_password_reset_sent") == 2


def test_no_link_for_a_deactivated_account_or_one_that_does_not_exist(world):
    """Five tools minted a link for a deactivated account that the sign-in
    would not honour, and three answered "Reset link sent." for an id that
    names nobody."""
    w = world()
    admin, off = w.admin(), w.educator(is_active=0)
    c = w.signed_in(admin)
    assert _where(_post(c, admin, _path(users_kit.SEND_LINK_URL, off["id"]))) == f"{USERS}?err=inactive"
    assert _where(_post(c, admin, _path(users_kit.SEND_LINK_URL, 1))) == f"{USERS}?err=missing"
    assert w.mails == [] and w.audits == [] and w.tokens(off["id"]) == []
    assert "gets no link" in c.get(f"{USERS}?err=inactive").text
    assert "does not exist" in c.get(f"{USERS}?err=missing").text


# ── decision 2: delete only what owns no sessions ────────────────────────────

def test_an_account_that_owns_sessions_is_not_deleted(world):
    """In three tools a delete removed the account's sessions and their
    participants' data with it."""
    w = world()
    admin, teacher, idle = w.admin(), w.educator(), w.educator()
    w.owned[teacher["id"]] = 3
    w.run(f"INSERT INTO {w.RT} (holder_id, token_hash, expires_at) "
          f"VALUES (%s, 'x', NOW() + INTERVAL 1 HOUR)", (idle["id"],))
    c = w.signed_in(admin)
    page = c.get(USERS).text
    assert f'action="/backoffice/users/{idle["id"]}/delete"' in page
    assert f'action="/backoffice/users/{teacher["id"]}/delete"' not in page, \
        "the page offers a delete that would be refused"

    assert _where(_post(c, admin, _path(users_kit.DELETE_URL, teacher["id"]))) == f"{USERS}?err=has_sessions"
    assert w.row(teacher["id"]) is not None and w.audits == []
    assert "Deactivate it" in c.get(f"{USERS}?err=has_sessions").text

    assert _where(_post(c, admin, _path(users_kit.DELETE_URL, idle["id"]))) == f"{USERS}?msg=deleted"
    assert w.row(idle["id"]) is None and w.tokens(idle["id"]) == []
    assert w.audits[-1][:3] == ("admin_deleted", admin["id"], str(idle["id"]))
    assert w.audits[-1][3] == {"email": idle["email"]}
    # A second click finds nobody and records nothing.
    assert _where(_post(c, admin, _path(users_kit.DELETE_URL, idle["id"]))) == f"{USERS}?err=missing"
    assert w.actions().count("admin_deleted") == 1


def test_a_refused_delete_changes_nothing_at_all(world):
    """FL-148 (a): the passkeys and links were deleted before the account, apart.
    Where another table of the tool refuses the delete (Drawbridge's
    baseline_batches is ON DELETE RESTRICT), the account stayed without its
    passkeys and links. Now the three go in one transaction or not at all."""
    w = world()
    admin, uploader = w.admin(), w.educator()
    uploads = w.T.replace("kit_accounts_", "kit_uploads_")
    w.run(f"CREATE TABLE {uploads} (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
          f"uploaded_by INT NOT NULL, FOREIGN KEY (uploaded_by) REFERENCES {w.T} (id) "
          f"ON DELETE RESTRICT) ENGINE=InnoDB")
    try:
        w.run(f"INSERT INTO {uploads} (uploaded_by) VALUES (%s)", (uploader["id"],))
        w.run(f"INSERT INTO {w.PK} (owner_id, credential_id, public_key, name) "
              f"VALUES (%s, %s, %s, 'laptop')", (uploader["id"], b"cred-fl148", b"key"))
        w.run(f"INSERT INTO {w.RT} (holder_id, token_hash, expires_at) "
              f"VALUES (%s, 'fl148', NOW() + INTERVAL 1 HOUR)", (uploader["id"],))
        c = w.signed_in(admin)
        assert _where(_post(c, admin, _path(users_kit.DELETE_URL, uploader["id"]))) == \
            f"{USERS}?err=not_deleted"
        assert w.row(uploader["id"]) is not None
        assert len(w.all(f"SELECT id FROM {w.PK} WHERE owner_id=%s", (uploader["id"],))) == 1, \
            "the refused delete took the passkey"
        assert len(w.tokens(uploader["id"])) == 1, "the refused delete took the link"
        assert "admin_deleted" not in w.actions()
    finally:
        w.run(f"DROP TABLE {uploads}")


# ── decision 3: the last administrator, and one's own account ────────────────

def test_nobody_deactivates_demotes_or_deletes_their_own_account_here(world):
    """In two tools an administrator could demote themselves."""
    w = world()
    admin, second = w.admin(), w.admin()
    c = w.signed_in(admin)
    own = admin["id"]
    assert _where(_post(c, admin, _path(users_kit.DEACTIVATE_URL, own))) == f"{USERS}?err=own"
    assert _where(_post(c, admin, _path(users_kit.DELETE_URL, own))) == f"{USERS}?err=own"
    assert _where(_post(c, admin, _path(users_kit.EDIT_URL, own), display_name="Me",
                        email=admin["email"], role="educator")) == f"{USERS}?err=own"
    assert _where(c.get(_path(users_kit.EDIT_URL, own))) == f"{USERS}?err=own"
    assert _where(_post(c, admin, users_kit.BULK_URL, action="deactivate",
                        ids=[str(own)])) == f"{USERS}?msg=bulk_deactivated&skipped=1"
    after = w.row(own)
    assert (after["role"], after["is_active"], after["session_epoch"]) == ("admin", 1, 0)
    assert w.audits == [] and second
    page = c.get(USERS).text
    assert f'/backoffice/users/{own}/' not in page, "the page offers an action on one's own account"
    assert "(you)" in page and "Manage account" in page


def test_the_last_active_administrator_stays(world):
    """Only one tool counted administrators. The count is a condition of the
    change itself, so two administrators acting on each other at the same
    moment cannot both go through; here the second of them is a session whose
    account has just lost the role."""
    me = {}
    w = world(current_account=lambda request: me.get("row"))
    last, retired = w.admin(), w.admin(is_active=0)
    me["row"] = {**last, "id": 0, "email": "just-demoted@example.invalid"}
    c, ghost = w.client(), me["row"]

    assert _where(_post(c, ghost, _path(users_kit.DEACTIVATE_URL, last["id"]))) == f"{USERS}?err=last_admin"
    r = _post(c, ghost, _path(users_kit.EDIT_URL, last["id"]), display_name="Kit Person",
              email=last["email"], role="educator")
    assert r.status_code == 400 and "last active administrator" in r.text
    assert _where(_post(c, ghost, _path(users_kit.DELETE_URL, last["id"]))) == f"{USERS}?err=last_admin"
    assert _where(_post(c, ghost, users_kit.BULK_URL, action="deactivate",
                        ids=[str(last["id"])])) == f"{USERS}?msg=bulk_deactivated&skipped=1"
    after = w.row(last["id"])
    assert (after["role"], after["is_active"], after["session_epoch"]) == ("admin", 1, 0)
    assert w.audits == [] and w.mails == []
    page = c.get(USERS).text
    assert f'/backoffice/users/{last["id"]}/deactivate' not in page
    assert f'/backoffice/users/{last["id"]}/delete' not in page

    # A deactivated administrator is not one of the active ones: it can go.
    assert _where(_post(c, ghost, _path(users_kit.DELETE_URL, retired["id"]))) == f"{USERS}?msg=deleted"
    # With a second active administrator each of the three goes through.
    second = w.admin()
    r = _post(c, ghost, _path(users_kit.EDIT_URL, last["id"]), display_name="Kit Person",
              email=last["email"], role="educator")
    assert _where(r) == f"{USERS}?msg=saved_signed_out" and w.row(last["id"])["role"] == "educator"
    assert second


# ── decision 4: a new address or role ends the sessions and is told ──────────

def test_a_new_address_ends_the_sessions_and_tells_the_address_it_had(world):
    """Six tools left the account's sessions open."""
    w = world()
    admin, person = w.admin(), w.educator()
    theirs = w.signed_in(person)
    assert theirs.get("/backoffice/account").status_code == 200
    w.run(f"INSERT INTO {w.RT} (holder_id, token_hash, expires_at) "
          f"VALUES (%s, 'x', NOW() + INTERVAL 1 HOUR)", (person["id"],))
    c = w.signed_in(admin)
    page = c.get(_path(users_kit.EDIT_URL, person["id"]))
    assert page.status_code == 200 and f'value="{person["email"]}"' in page.text

    r = _post(c, admin, _path(users_kit.EDIT_URL, person["id"]), display_name="Kit Person",
              email="moved@example.invalid", role="educator")
    assert _where(r) == f"{USERS}?msg=saved_signed_out"
    after = w.row(person["id"])
    assert (after["email"], after["session_epoch"]) == ("moved@example.invalid", 1)
    assert _where(theirs.get("/backoffice/account")) == "/backoffice/login"
    assert w.tokens(person["id"]) == [(1, 1)], "a link mailed to the old address still opens the account"
    assert w.mails == [("send_account_change_notice", person["email"], "moved@example.invalid", "")]
    assert w.audits == [("admin_edited", admin["id"], str(person["id"]),
                         {"email": "moved@example.invalid", "from": person["email"]},
                         admin["email"])]
    assert "signed out everywhere" in c.get(_where(r)).text


def test_a_new_role_ends_the_sessions_and_a_new_name_does_not(world):
    w = world()
    admin, person = w.admin(), w.educator()
    c = w.signed_in(admin)
    r = _post(c, admin, _path(users_kit.EDIT_URL, person["id"]), display_name="Dr Kit Person",
              email=person["email"], role="educator")
    assert _where(r) == f"{USERS}?msg=saved"
    after = w.row(person["id"])
    assert (after[w.name_col], after["session_epoch"]) == ("Dr Kit Person", 0)
    assert w.mails == [] and w.actions() == ["admin_edited"]

    r = _post(c, admin, _path(users_kit.EDIT_URL, person["id"]), display_name="Dr Kit Person",
              email=person["email"], role="admin")
    assert _where(r) == f"{USERS}?msg=saved_signed_out"
    after = w.row(person["id"])
    assert (after["role"], after["session_epoch"]) == ("admin", 1)
    assert w.mails == [("send_account_change_notice", person["email"], "", "admin")]
    assert w.actions() == ["admin_edited", "admin_edited", "admin_role_changed"]
    assert w.audits[-1][3] == {"email": person["email"], "from": "educator", "to": "admin"}

    # Saving the form unchanged writes nothing and records nothing.
    r = _post(c, admin, _path(users_kit.EDIT_URL, person["id"]), display_name="Dr Kit Person",
              email=person["email"], role="admin")
    assert _where(r) == f"{USERS}?msg=saved" and len(w.audits) == 3


def test_an_edit_cannot_take_another_accounts_address(world):
    w = world()
    admin, person, other = w.admin(), w.educator(), w.educator()
    r = _post(w.signed_in(admin), admin, _path(users_kit.EDIT_URL, person["id"]),
              display_name="Kit Person", email=other["email"], role="educator")
    assert r.status_code == 400 and "already uses that address" in r.text
    assert w.row(person["id"])["email"] == person["email"] and w.audits == [] and w.mails == []


# ── deactivating and activating ──────────────────────────────────────────────

def test_a_deactivated_account_is_out_at_once_and_only_a_change_is_recorded(world):
    """One tool wrote audit rows for actions that had not happened."""
    w = world()
    admin, person = w.admin(), w.educator()
    theirs = w.signed_in(person)
    w.run(f"INSERT INTO {w.RT} (holder_id, token_hash, expires_at) "
          f"VALUES (%s, 'x', NOW() + INTERVAL 1 HOUR)", (person["id"],))
    c = w.signed_in(admin)
    off, on = _path(users_kit.DEACTIVATE_URL, person["id"]), _path(users_kit.ACTIVATE_URL, person["id"])
    assert _where(_post(c, admin, off)) == f"{USERS}?msg=deactivated"
    after = w.row(person["id"])
    assert (after["is_active"], after["session_epoch"]) == (0, 1)
    assert _where(theirs.get("/backoffice/account")) == "/backoffice/login"
    assert w.tokens(person["id"]) == [(1, 1)]
    assert _where(_post(c, admin, off)) == f"{USERS}?msg=deactivated"
    assert w.actions() == ["admin_deactivated"], "a second click was recorded as a second change"

    assert _where(_post(c, admin, on)) == f"{USERS}?msg=activated"
    assert w.row(person["id"])["is_active"] == 1
    assert _where(_post(c, admin, on)) == f"{USERS}?msg=activated"
    assert w.actions() == ["admin_deactivated", "admin_activated"]
    # Coming back does not revive the cookie from before.
    assert _where(theirs.get("/backoffice/account")) == "/backoffice/login"


# ── decision 6: several at once ──────────────────────────────────────────────

def test_a_bulk_send_counts_refused_mails_apart_from_the_skipped(world):
    """FL-148 (b): a mail the server refused was counted among the skipped,
    whose note names other reasons. It is its own count now, in the error box,
    and no link is stored for it."""
    w = world()
    admin, a, b, off = w.admin(), w.educator(), w.educator(), w.educator(is_active=0)
    c = w.signed_in(admin)
    w.mail_ok = False
    r = _post(c, admin, users_kit.BULK_URL, action="send-link",
              ids=[str(x["id"]) for x in (a, b, off)])
    assert _where(r) == f"{USERS}?msg=bulk_links&skipped=1&failed=2"
    page = c.get(_where(r)).text
    assert "The mail could not be sent to 2 of the selected accounts" in page
    assert "1 skipped" in page and "0 link(s) sent." in page
    assert w.tokens(a["id"]) == [] and w.tokens(b["id"]) == []
    assert "admin_password_reset_sent" not in w.actions()


def test_several_at_once_deactivate_or_send_links_and_nothing_else(world):
    w = world()
    admin, a, b, off = w.admin(), w.educator(), w.educator(), w.educator(is_active=0)
    c = w.signed_in(admin)
    ids = [str(x["id"]) for x in (a, b, off, admin)]
    r = _post(c, admin, users_kit.BULK_URL, action="send-link", ids=ids)
    assert _where(r) == f"{USERS}?msg=bulk_links&n=3&skipped=1"
    assert sorted(m[1] for m in w.mails) == sorted([a["email"], b["email"], admin["email"]])
    assert "3 link(s) sent. 1 skipped" in c.get(_where(r)).text

    r = _post(c, admin, users_kit.BULK_URL, action="deactivate", ids=ids)
    assert _where(r) == f"{USERS}?msg=bulk_deactivated&n=2&skipped=2"
    assert [w.row(x["id"])["is_active"] for x in (a, b, admin)] == [0, 0, 1]
    assert w.actions().count("admin_deactivated") == 2

    assert _post(c, admin, users_kit.BULK_URL, action="delete", ids=ids).status_code == 400
    assert all(w.row(x["id"]) for x in (a, b, off, admin)), "several accounts were deleted at once"
    assert _where(_post(c, admin, users_kit.BULK_URL, action="deactivate")) == f"{USERS}?err=nothing"
    page = c.get(USERS).text
    assert 'data-bulk-action="deactivate"' in page and 'data-bulk-action="send-link"' in page
    assert 'data-bulk-action="delete"' not in page


# ── the page ─────────────────────────────────────────────────────────────────

def test_the_page_holds_nothing_secret_and_draws_nothing_from_its_address(world):
    w = world()
    admin = w.admin()
    person = w.educator(totp_enabled=1, totp_secret="JBSWY3DPEHPK3PXP",  # pragma: allowlist secret (test value)
                        totp_backup_codes='["hash-of-a-code"]')
    c = w.signed_in(admin)
    page = c.get(f"{USERS}?msg=%3Cb%3Ehello&err=%3Cb%3Ehello&n=7").text
    assert "hello" not in page
    for secret in (w.row(person["id"])[w.pw_col], "JBSWY3DPEHPK3PXP", "hash-of-a-code"):
        assert secret not in page
    assert person["email"] in page and "Kit Person" in page
    # The lost-phone button is on the list, asks once, and leads back here.
    button = re.search(rf'<form[^>]*action="/backoffice/users/{person["id"]}/reset-two-factor".*?</form>',
                       page, re.S)
    assert button and "data-confirm=" in button.group(0)
    assert "Two-factor login was reset" in c.get(f"{USERS}?msg=two_factor_reset").text
    # Every form posts a token, and to a route that exists.
    served = set(users_kit.PATHS) | set(kit_mod.PATHS)
    for action in set(re.findall(r'<form[^>]*action="([^"]+)"', page)):
        assert re.sub(r"/\d+/", "/{user_id}/", action) in served, action
    assert page.count("<form") == page.count('name="csrf_token"')


def test_a_tool_that_spells_its_roles_in_capitals(world):
    """Four tools store ADMIN and EDUCATOR."""
    w = world(roles=("ADMIN", "EDUCATOR"))
    admin, person = w.admin(), w.educator()
    c = w.signed_in(admin)
    assert c.get(USERS).status_code == 200
    assert c.get(USERS).text.count("role-badge--admin") == 1
    _post(c, admin, users_kit.INVITE_URL, display_name="Eve", email="eve@example.invalid",
          role="admin")
    assert w.by_email("eve@example.invalid")["role"] == "ADMIN"
    _post(c, admin, _path(users_kit.EDIT_URL, person["id"]), display_name="Kit Person",
          email=person["email"], role="admin")
    assert w.row(person["id"])["role"] == "ADMIN"


def test_the_kits_templates_are_the_account_kits(world):
    """They ship in the same folder and are found under the same prefix."""
    names = {p.name for p in kit_mod.TEMPLATE_DIR.glob("user*.html")}
    assert names == {"users.html", "user_edit.html"}


def test_a_button_asks_through_the_script_the_tool_has(world):
    """Moral Mirror has no actions.js: its buttons ask through confirm-submit.js
    and `data-confirm-submit`. A Delete that carried only `data-confirm` there
    would act without asking."""
    plain = world()
    admin, person = plain.admin(), plain.educator()
    page = plain.signed_in(admin).get(USERS).text
    assert "data-confirm=" in page and "data-confirm-submit" not in page
    assert "/static/js/confirm-submit.js" not in page

    mm = world(users_adapter=dict(confirm_attribute="data-confirm-submit",
                                  extra_scripts=("/static/js/confirm-submit.js",)))
    admin, person = mm.admin(), mm.educator()
    page = mm.signed_in(admin).get(USERS).text
    for action in ("deactivate", "delete", "reset-two-factor"):
        if action == "reset-two-factor":
            mm.run(f"UPDATE {mm.T} SET totp_enabled=1 WHERE id=%s", (person["id"],))
            page = mm.signed_in(admin).get(USERS).text
        block = re.search(rf'<form[^>]*/{person["id"]}/{action}".*?</form>', page, re.S).group(0)
        assert 'data-confirm-submit="' in block and ' data-confirm="' not in block, action
    assert '<script src="/static/js/confirm-submit.js" defer></script>' in page


def test_the_adapter_refuses_a_confirm_attribute_or_script_it_does_not_know(world):
    w = world()
    for bad in (dict(confirm_attribute="onclick"), dict(extra_scripts=("https://elsewhere.example/x.js",)),
                dict(extra_scripts=('/static/a.js" onload="x',))):
        with pytest.raises(ValueError):
            users_kit.UsersKit(account=w.kit, session_counts=dict, **bad)
