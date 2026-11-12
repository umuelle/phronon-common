"""The users kit: the page on which an administrator manages the other accounts (FL-133).

WHAT THIS IS
Eight tools each carried their own Users page: a list, "add user", edit,
deactivate, delete, "set a password", "send a reset link". The fleet review of
11 November 2026 compared them and found that they differed where it matters:
three deleted an account's sessions, with their participants' data, along with
the account; one counted administrators before removing one and seven did not;
all eight had the administrator type a first password, which then travelled by
some second channel. This module is the one page, built on the account kit:

    from phronon_common import account_kit, users_kit
    kit = account_kit.AccountKit(...)
    users = users_kit.UsersKit(account=kit, session_counts=...)
    app.include_router(users_kit.build_users_router(users))

Its templates ship beside the account kit's (`account_kit/users.html`,
`account_kit/user_edit.html`) and render inside the tool's own
`backoffice/base.html`.

THE RULES ARE THE OWNER'S (12 November 2026, README §11, "The Users page")
  1. A new account is made with a name, an address and a role. The tool mails
     a link on which the person sets a password (72 hours, can be sent again).
     Nobody types a password for somebody else.
  2. Only an account that owns no sessions can be deleted. One that does is
     deactivated: nobody can sign in with it, and its sessions stay.
  3. The last active administrator cannot be deactivated, demoted or deleted,
     and nobody changes their own role, deactivates or deletes their own
     account here.
  4. Changing somebody's address or role is allowed. It ends that account's
     sessions at once, spends its outstanding links, and the address the
     account had until then is told by mail.
  5. There is no "set a password". The page sends a link; a deactivated
     account gets none.
  6. Several accounts at once: deactivate, or send links. No delete.

WHAT A TOOL SUPPLIES — the `UsersKit` adapter
Its `AccountKit` (tables, session, pages, CSRF check, audit, mail module), how
many sessions each account owns, and how it spells its two roles. Its mail
module also provides `send_account_invitation` and `send_account_change_notice`.

EVERY ROUTE IS AN ADMINISTRATOR'S. Each handler checks the role itself, before
it reads anything: hiding a button withholds nothing (adminroutes.py).

A page is never drawn from a successful POST: the answer is a redirect to the
list with a message code, so a reload repeats nothing. A form sent back with a
mistake is re-shown with the mistake named and answers 400.
"""
from __future__ import annotations

import importlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable, Optional, cast
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.routing import APIRoute
from starlette.background import BackgroundTask

from . import account as account_mod
from . import account_kit
from . import once as _once
from .account_kit import AccountKit

USERS_URL = account_kit.USERS_URL
INVITE_URL = "/backoffice/users/invite"
BULK_URL = "/backoffice/users/bulk"
EDIT_URL = "/backoffice/users/{user_id}/edit"
SEND_LINK_URL = "/backoffice/users/{user_id}/send-link"
DEACTIVATE_URL = "/backoffice/users/{user_id}/deactivate"
ACTIVATE_URL = "/backoffice/users/{user_id}/activate"
DELETE_URL = "/backoffice/users/{user_id}/delete"

#: Every path the router answers, for a tool's gates and tests.
PATHS = (USERS_URL, INVITE_URL, BULK_URL, EDIT_URL, SEND_LINK_URL, DEACTIVATE_URL,
         ACTIVATE_URL, DELETE_URL)
#: The paths that answer GET (and HEAD) as well.
GET_PATHS = (USERS_URL, EDIT_URL)

#: How long the link in an invitation lives (decision 1).
INVITE_HOURS = 72

#: What the list says after an action, by the code in its address. A code the
#: page does not know is ignored, so nothing is ever rendered from the URL.
MESSAGES = {
    "invited": "The account was created. A link to set a password is on its way; it is valid for {hours} hours.",
    "invited_unsent": ("The account was created, but the mail with the link could not be sent. "
                       "Use “Send link” in the list to try again."),
    "saved": "The changes were saved.",
    "saved_signed_out": ("The changes were saved. The account was signed out everywhere, "
                         "and the address it had is told by e-mail."),
    "link_sent": "A link to set a password was sent.",
    "deactivated": "The account was deactivated. Nobody can sign in with it; its sessions stay.",
    "activated": "The account was activated.",
    "deleted": "The account was deleted.",
    "two_factor_reset": "Two-factor login was reset for that account. It is told by e-mail.",
    "bulk_deactivated": "{n} account(s) deactivated.",
    "bulk_links": "{n} link(s) sent.",
}
ERRORS = {
    "missing": "That account does not exist.",
    "own": ("This is your own account. You cannot change your role, deactivate or delete it "
            "here; use “Manage account” for your name, address and password."),
    "last_admin": ("This is the last active administrator. Make another account an "
                   "administrator first."),
    "has_sessions": ("This account owns sessions, so it cannot be deleted. Deactivate it "
                     "instead: nobody can sign in with it, and its sessions stay."),
    "inactive": "This account is deactivated and gets no link. Activate it first.",
    "taken": "Another account already uses that address.",
    "role": "Choose a role: educator or administrator.",
    "mail": "The mail could not be sent, so no link was issued. Try again in a moment.",
    "not_deleted": "The account could not be deleted. Deactivate it instead.",
    "not_created": "The account could not be created. Nothing was stored; try again.",
    "not_saved": ("The changes could not be saved; the address may have been taken a moment "
                  "ago. Nothing was changed."),
    "nothing": "No account was selected.",
}
SKIPPED_NOTE = " {skipped} skipped (your own account, a deactivated one or the last administrator)."


@dataclass(frozen=True, kw_only=True)
class UsersKit:
    """Everything the Users page needs from the tool that mounts it."""

    #: The tool's account kit: its tables, session, pages, CSRF check, audit
    #: recorder and mail module are this page's too.
    account: AccountKit
    #: () -> {account id: how many sessions it owns}. An account missing from
    #: the answer owns none. Decides whether an account may be deleted
    #: (decision 2), and is the list's "Sessions" column.
    session_counts: Callable[[], dict]
    #: How the tool's table spells its two roles ("ADMIN" in four tools). The
    #: page and its forms always say "admin" and "educator".
    admin_role: str = "admin"
    educator_role: str = "educator"
    #: How long an invitation's link lives.
    invite_hours: int = INVITE_HOURS


def build_users_router(users: UsersKit) -> APIRouter:
    """The Users page's routes for one tool. Mount with `app.include_router`."""
    kit = users.account
    router = APIRouter()
    T = kit.tables.accounts
    PK, OWNER = kit.tables.passkeys, kit.tables.passkey_owner
    RT, RT_OWNER, SPENT = (kit.tables.reset_tokens, kit.tables.reset_token_owner,
                           kit.tables.reset_token_spent)
    UNSPENT, SPEND = ((f"{SPENT} IS NULL", f"{SPENT}=NOW()") if SPENT.endswith("_at")
                      else (f"{SPENT}=0", f"{SPENT}=1"))
    PW, NAME = kit.tables.password_column, kit.tables.name_column
    q1, qall, run = kit.tables.query_one, kit.tables.query_all, kit.tables.execute
    ADMIN, EDUCATOR = users.admin_role, users.educator_role
    # "At least one OTHER active administrator exists", as one condition of the
    # UPDATE or DELETE itself, so two administrators acting on each other at
    # the same moment cannot both pass a check made beforehand (decision 3).
    # The inner SELECT is wrapped once more because MySQL refuses a statement
    # that reads the table it is changing in a plain subquery.
    ANOTHER_ADMIN = (f"(SELECT n FROM (SELECT COUNT(*) AS n FROM {T} WHERE LOWER(role)=%s "
                     f"AND is_active=1 AND id<>%s) AS others) > 0")

    def mail(name: str) -> Callable[..., Any]:
        sender: Callable[..., Any] = getattr(importlib.import_module(kit.mail_module), name)
        return sender

    def later(response: Response, func: Callable[..., Any], *args: Any) -> Response:
        """Run func(*args) after the response is sent; a failure is logged."""
        def safe() -> None:
            try:
                func(*args)
            except Exception:  # noqa: BLE001
                kit.logger.exception("account notice could not be sent")
        response.background = BackgroundTask(safe)
        return response

    def role_of(row: dict) -> str:
        """"admin" or "educator", however the tool's table spells it."""
        return "admin" if str(row.get("role") or "").lower() == ADMIN.lower() else "educator"

    def stored_role(role: str) -> str:
        return ADMIN if role == "admin" else EDUCATOR

    def shown(row: dict, counts: dict, me: dict, admins: int) -> dict:
        """What the page may know about an account: never a hash, a secret or
        a recovery code, whatever the row holds."""
        role = role_of(row)
        return {
            "id": row["id"], "email": row.get("email") or "",
            "display_name": row.get(NAME) or "",
            "role": role, "is_active": bool(row.get("is_active")),
            "last_login_at": row.get("last_login_at"),
            "two_factor": bool(row.get("totp_enabled")),
            "sessions": int(counts.get(row["id"], 0) or 0),
            "is_self": row["id"] == me["id"],
            "last_admin": role == "admin" and bool(row.get("is_active")) and admins <= 1,
        }

    def everyone(me: dict) -> list[dict]:
        rows = qall(f"SELECT * FROM {T} ORDER BY is_active DESC, {NAME}, email", ())
        counts = users.session_counts() or {}
        admins = sum(1 for r in rows if role_of(r) == "admin" and r.get("is_active"))
        return [shown(r, counts, me, admins) for r in rows]

    def one(user_id: int, me: dict) -> Optional[dict]:
        return next((u for u in everyone(me) if u["id"] == user_id), None)

    def back(msg: str = "", err: str = "", **numbers: int) -> RedirectResponse:
        query = {k: v for k, v in (("msg", msg), ("err", err)) if v}
        query.update({k: str(v) for k, v in numbers.items() if v})
        return RedirectResponse(USERS_URL + ("?" + urlencode(query) if query else ""),
                                status_code=303)

    def page(request: Request, name: str, me: dict, *, status_code: int = 200,
             **context: Any) -> Response:
        context.update(account=me, users_kit={
            "tool_name": kit.tool_name, "invite_hours": users.invite_hours,
            "reset_hours": kit.reset_token_hours})
        return kit.render(request, account_kit.template(name), context,
                          status_code=status_code, csrf_for=me, preauth=False)

    def list_page(request: Request, me: dict, *, status_code: int = 200,
                  flash: Optional[str] = None, error: Optional[str] = None,
                  form: Optional[dict] = None) -> Response:
        return page(request, "users.html", me, status_code=status_code, people=everyone(me),
                    flash=flash, error=error, form=form or {})

    def number(request: Request, name: str) -> int:
        raw = request.query_params.get(name, "")
        return int(raw) if raw.isdigit() and len(raw) < 6 else 0

    def store_link(account_id: int, raw: str, hours: int) -> None:
        """A reset token of the shape the kit's reset page reads."""
        if kit.tables.clock is None:
            run(f"INSERT INTO {RT} ({RT_OWNER}, token_hash, expires_at) "
                f"VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))",
                (account_id, account_kit.reset_token_hash(raw), hours))
        else:
            run(f"INSERT INTO {RT} ({RT_OWNER}, token_hash, expires_at) VALUES (%s, %s, %s)",
                (account_id, account_kit.reset_token_hash(raw),
                 kit.tables.clock() + timedelta(hours=hours)))

    def send_link(row: dict) -> bool:
        """Mail the account a link on which its holder sets a password: the
        invitation while it has never signed in (72 hours), the ordinary reset
        afterwards. The link is stored only once the mail server has taken the
        mail, so a failed send leaves no live credential behind. True when it
        went."""
        raw = secrets.token_urlsafe(32)
        url = f"{kit.base_url()}{account_kit.RESET_URL}?token={raw}"
        invited = row.get("last_login_at") is None
        try:
            if invited:
                sent = mail("send_account_invitation")(row["email"], url, users.invite_hours)
            else:
                sent = mail("send_password_reset")(row["email"], url)
        except Exception:  # noqa: BLE001
            kit.logger.exception("the link to set a password could not be sent")
            return False
        if not sent:
            return False
        store_link(row["id"], raw, users.invite_hours if invited else kit.reset_token_hours)
        return True

    def deactivate(row: dict) -> bool:
        """Switch the account off, end its sessions and spend its links. False
        when it is the last active administrator (the UPDATE itself decides)."""
        changed = _once._run(
            kit.tables.get_conn,
            f"UPDATE {T} SET is_active=0, session_epoch=session_epoch+1 WHERE id=%s "
            f"AND is_active=1 AND (LOWER(role)<>%s OR {ANOTHER_ADMIN})",
            [row["id"], ADMIN.lower(), ADMIN.lower(), row["id"]])
        if changed == 1:
            run(f"UPDATE {RT} SET {SPEND} WHERE {RT_OWNER}=%s AND {UNSPENT}", (row["id"],))
        return changed == 1

    # ── the list ─────────────────────────────────────────────────────────────

    @router.get(USERS_URL)
    def users_list(request: Request) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        code = request.query_params.get("msg", "")
        msg = MESSAGES.get(code)
        err = ERRORS.get(request.query_params.get("err", ""))
        if msg:
            msg = msg.format(n=number(request, "n"), hours=users.invite_hours)
            skipped = number(request, "skipped")
            if skipped and code.startswith("bulk_"):
                msg += SKIPPED_NOTE.format(skipped=skipped)
        return list_page(request, signed_in, flash=msg, error=err)

    # ── a new account (decision 1) ───────────────────────────────────────────

    @router.post(INVITE_URL)
    def users_invite(request: Request, csrf_token: str = Form(""),
                     display_name: str = Form(""), email: str = Form(""),
                     role: str = Form("educator")) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        form = {"display_name": display_name.strip(), "email": email.strip(), "role": role}

        def again(error: str) -> Response:
            return list_page(request, signed_in, status_code=account_kit.RESHOWN,
                             error=error, form=form)
        name, error = account_mod.validate_name(display_name)
        if error:
            return again(error)
        address, error = account_mod.validate_email(email, current=None)
        if error:
            return again(error)
        if role not in ("admin", "educator"):
            return again(ERRORS["role"])
        if q1(f"SELECT id FROM {T} WHERE email=%s", (address,)):
            return again(ERRORS["taken"])
        # A password nobody knows: the account exists, and the only way in is
        # the mailed link (or a later one).
        unusable = kit.bcrypt.hashpw(secrets.token_bytes(32), kit.bcrypt.gensalt()).decode()
        try:
            run(f"INSERT INTO {T} (email, {PW}, role, {NAME}, is_active, must_change_password) "
                f"VALUES (%s, %s, %s, %s, 1, 0)", (address, unusable, stored_role(role), name))
        except Exception:  # noqa: BLE001 — e.g. the address was taken a moment ago
            kit.logger.exception("the new account could not be stored")
            return again(ERRORS["not_created"])
        row = q1(f"SELECT * FROM {T} WHERE email=%s", (address,))
        assert row is not None      # stored one statement ago
        sent = send_link(row)
        kit.audit("admin_created", request=request, admin_id=signed_in["id"],
                  admin_email=signed_in.get("email"), subject=str(row["id"]),
                  details={"email": address, "role": role, "invitation_sent": sent})
        return back(msg="invited" if sent else "invited_unsent")

    # ── one account ──────────────────────────────────────────────────────────

    @router.get(EDIT_URL)
    def users_edit_page(request: Request, user_id: int) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        person = one(user_id, signed_in)
        if not person:
            return back(err="missing")
        if person["is_self"]:
            return back(err="own")
        return page(request, "user_edit.html", signed_in, person=person, error=None)

    @router.post(EDIT_URL)
    def users_edit(request: Request, user_id: int, csrf_token: str = Form(""),
                   display_name: str = Form(""), email: str = Form(""),
                   role: str = Form("")) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        person = one(user_id, signed_in)
        if not person:
            return back(err="missing")
        if person["is_self"]:
            return back(err="own")

        def again(error: str) -> Response:
            typed = {**person, "display_name": display_name.strip(), "email": email.strip(),
                     "role": role if role in ("admin", "educator") else person["role"]}
            return page(request, "user_edit.html", signed_in, status_code=account_kit.RESHOWN,
                        person=typed, error=error)
        name, error = account_mod.validate_name(display_name)
        if error:
            return again(error)
        address, error = account_mod.validate_email(email, current=None)
        if error:
            return again(error)
        if role not in ("admin", "educator"):
            return again(ERRORS["role"])
        if q1(f"SELECT id FROM {T} WHERE email=%s AND id<>%s", (address, user_id)):
            return again(ERRORS["taken"])
        new_address = address != person["email"]
        new_role = role != person["role"]
        if not (new_address or new_role or name != person["display_name"]):
            return back(msg="saved")
        # Decision 4: a new address or role ends every session of the account.
        epoch = ", session_epoch=session_epoch+1" if new_address or new_role else ""
        sql = f"UPDATE {T} SET email=%s, {NAME}=%s, role=%s{epoch} WHERE id=%s"
        params: list = [address, name, stored_role(role), user_id]
        demoted = new_role and person["role"] == "admin" and person["is_active"]
        if demoted:                                             # decision 3
            sql += f" AND {ANOTHER_ADMIN}"
            params += [ADMIN.lower(), user_id]
        try:
            changed = _once._run(kit.tables.get_conn, sql, params)
        except Exception:  # noqa: BLE001 — e.g. the address was taken a moment ago
            kit.logger.exception("the account could not be changed")
            return again(ERRORS["not_saved"])
        if demoted and changed != 1:
            return again(ERRORS["last_admin"])
        details: dict = {"email": address}
        if new_address:
            details["from"] = person["email"]
            # A link mailed to the address the account no longer has must not
            # open the account.
            run(f"UPDATE {RT} SET {SPEND} WHERE {RT_OWNER}=%s AND {UNSPENT}", (user_id,))
        kit.audit("admin_edited", request=request, admin_id=signed_in["id"],
                  admin_email=signed_in.get("email"), subject=str(user_id), details=details)
        if new_role:
            kit.audit("admin_role_changed", request=request, admin_id=signed_in["id"],
                      admin_email=signed_in.get("email"), subject=str(user_id),
                      details={"email": address, "from": person["role"], "to": role})
        if not (new_address or new_role):
            return back(msg="saved")
        # The address the account HAD hears about it: if this was not agreed,
        # that is where somebody can still notice.
        return later(back(msg="saved_signed_out"), mail("send_account_change_notice"),
                     person["email"], address if new_address else "",
                     role if new_role else "")

    @router.post(SEND_LINK_URL)
    def users_send_link(request: Request, user_id: int,
                        csrf_token: str = Form("")) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        row = q1(f"SELECT * FROM {T} WHERE id=%s", (user_id,))
        if not row:
            return back(err="missing")
        if not row.get("is_active"):
            return back(err="inactive")                         # decision 5
        if not send_link(row):
            return back(err="mail")
        kit.audit("admin_password_reset_sent", request=request, admin_id=signed_in["id"],
                  admin_email=signed_in.get("email"), subject=str(user_id),
                  details={"email": row.get("email")})
        return back(msg="link_sent")

    @router.post(DEACTIVATE_URL)
    def users_deactivate(request: Request, user_id: int,
                         csrf_token: str = Form("")) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        row = q1(f"SELECT * FROM {T} WHERE id=%s", (user_id,))
        if not row:
            return back(err="missing")
        if row["id"] == signed_in["id"]:
            return back(err="own")
        if not row.get("is_active"):
            return back(msg="deactivated")
        if not deactivate(row):
            return back(err="last_admin")
        kit.audit("admin_deactivated", request=request, admin_id=signed_in["id"],
                  admin_email=signed_in.get("email"), subject=str(user_id),
                  details={"email": row.get("email")})
        return back(msg="deactivated")

    @router.post(ACTIVATE_URL)
    def users_activate(request: Request, user_id: int,
                       csrf_token: str = Form("")) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        row = q1(f"SELECT * FROM {T} WHERE id=%s", (user_id,))
        if not row:
            return back(err="missing")
        if not row.get("is_active"):
            run(f"UPDATE {T} SET is_active=1 WHERE id=%s", (user_id,))
            kit.audit("admin_activated", request=request, admin_id=signed_in["id"],
                      admin_email=signed_in.get("email"), subject=str(user_id),
                      details={"email": row.get("email")})
        return back(msg="activated")

    @router.post(DELETE_URL)
    def users_delete(request: Request, user_id: int,
                     csrf_token: str = Form("")) -> Response:
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        row = q1(f"SELECT * FROM {T} WHERE id=%s", (user_id,))
        if not row:
            return back(err="missing")
        if row["id"] == signed_in["id"]:
            return back(err="own")
        if int((users.session_counts() or {}).get(user_id, 0) or 0) > 0:
            return back(err="has_sessions")                     # decision 2
        try:
            # The account's own passkeys and links first, so the delete works
            # where the tool's tables have no cascade; an administrator goes
            # only while another active one exists (decision 3).
            run(f"DELETE FROM {PK} WHERE {OWNER}=%s", (user_id,))
            run(f"DELETE FROM {RT} WHERE {RT_OWNER}=%s", (user_id,))
            gone = _once._run(
                kit.tables.get_conn,
                f"DELETE FROM {T} WHERE id=%s AND (LOWER(role)<>%s OR is_active=0 "
                f"OR {ANOTHER_ADMIN})",
                [user_id, ADMIN.lower(), ADMIN.lower(), user_id])
        except Exception:  # noqa: BLE001 — something of the tool's still refers to the account
            kit.logger.exception("the account could not be deleted")
            return back(err="not_deleted")
        if gone != 1:
            return back(err="last_admin")
        kit.audit("admin_deleted", request=request, admin_id=signed_in["id"],
                  admin_email=signed_in.get("email"), subject=str(user_id),
                  details={"email": row.get("email")})
        return back(msg="deleted")

    # ── several at once (decision 6) ─────────────────────────────────────────

    @router.post(BULK_URL)
    def users_bulk(request: Request, csrf_token: str = Form(""), action: str = Form(""),
                   ids: list[int] = Form(default=[])) -> Response:  # noqa: B006 — FastAPI's form default
        signed_in = kit.current_account(request)
        if not signed_in:
            return kit.signed_out(request)
        account = {**signed_in, "role": role_of(signed_in)}
        if account.get("role") != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, signed_in):
            raise HTTPException(400, "Bad CSRF token")
        if action not in ("deactivate", "send-link"):
            raise HTTPException(400, "Invalid request")
        chosen = sorted(set(ids))[:200]
        if not chosen:
            return back(err="nothing")
        done = skipped = 0
        for user_id in chosen:
            row = q1(f"SELECT * FROM {T} WHERE id=%s", (user_id,))
            if not row or not row.get("is_active"):
                skipped += 1
            elif action == "deactivate":
                if row["id"] != signed_in["id"] and deactivate(row):
                    done += 1
                    kit.audit("admin_deactivated", request=request, admin_id=signed_in["id"],
                              admin_email=signed_in.get("email"), subject=str(user_id),
                              details={"email": row.get("email"), "bulk": True})
                else:
                    skipped += 1
            elif send_link(row):
                done += 1
                kit.audit("admin_password_reset_sent", request=request,
                          admin_id=signed_in["id"], admin_email=signed_in.get("email"),
                          subject=str(user_id), details={"email": row.get("email"), "bulk": True})
            else:
                skipped += 1
        return back(msg="bulk_deactivated" if action == "deactivate" else "bulk_links",
                    n=done, skipped=skipped)

    # Every GET answers HEAD (see the account kit: mail scanners and proxies).
    for route in router.routes:
        if isinstance(route, APIRoute) and "GET" in cast("set[str]", route.methods):
            cast("set[str]", route.methods).add("HEAD")
    return router
