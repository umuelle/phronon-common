"""The account kit (FL-083): its routes, driven, and its templates, read.

Two halves.

STATIC (no database, cannot skip): the router answers exactly the paths it
promises, its templates parse and keep the fleet's password-form, CSRF and
recovery-code rules (they used to be checked in each tool's own templates/,
which no longer carry these pages), and the kit's code names no tool.

DRIVEN (a real MySQL, `test_db`; required on CI): a FastAPI app mounts the kit
from an adapter whose tables and columns are named like no real tool's
(`kit_accounts_*`, `owner_id`), with a stand-in session, CSRF scheme, mail
module and audit recorder. Every route is executed and what a person gets is
asserted: pages, redirects, cookies, rows, audit actions and mails — and that
each adapter field actually changes what it says it changes.
"""
from __future__ import annotations

import ast
import json
import re
import secrets
import sys
import types
from pathlib import Path

import bcrypt
import jinja2
import pytest

from phronon_common import account_kit as kit_mod
from phronon_common import lockout, twofactor
from phronon_common.passwords import MIN_LENGTH
from phronon_common.testing import (assert_form_asks_for_the_shared_hint,
                                    assert_form_does_not_restate_the_rule,
                                    assert_minlength_matches_the_policy)

PKG = Path(kit_mod.__file__).resolve().parent
TEMPLATES = sorted(kit_mod.TEMPLATE_DIR.glob("*.html"))
BASE = "https://testserver"
SECRET = "kit-test-secret-" + "0" * 32
PASSWORD = "Kit-test-passphrase-2026"


# ── static ───────────────────────────────────────────────────────────────────

def test_there_are_templates_to_check():
    assert {p.name for p in TEMPLATES} == {
        "account.html", "account_confirm_email.html", "two_factor.html",
        "two_factor_verify.html"}


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda p: p.name)
def test_every_template_parses(tpl):
    jinja2.Environment().parse(tpl.read_text(encoding="utf-8"))


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda p: p.name)
def test_every_template_renders_inside_the_tools_own_layout(tpl):
    assert '{% extends "backoffice/base.html" %}' in tpl.read_text(encoding="utf-8")


def test_the_password_form_states_the_shared_policy():
    page = kit_mod.TEMPLATE_DIR / "account.html"
    assert_form_asks_for_the_shared_hint(page, PKG)
    assert_form_does_not_restate_the_rule(page, PKG)
    assert_minlength_matches_the_policy(page, PKG)
    assert f'minlength="{MIN_LENGTH}"' in page.read_text(encoding="utf-8")


@pytest.mark.parametrize("tpl", TEMPLATES, ids=lambda p: p.name)
def test_every_post_form_carries_its_csrf_token(tpl):
    html = tpl.read_text(encoding="utf-8")
    for body in re.findall(r"<form[^>]*method=\"post\"[^>]*>(.*?)</form>", html, re.S | re.I):
        assert 'name="csrf_token"' in body


def test_recovery_codes_only_appear_behind_the_download_lock():
    html = (kit_mod.TEMPLATE_DIR / "two_factor.html").read_text(encoding="utf-8")
    assert "{% for c in codes %}" in html
    assert "data-recovery-codes" in html and "data-recovery-done" in html
    assert "/static/js/recovery-codes.js" in html


def _code_strings(path: Path) -> list[str]:
    """Every string literal in a module except docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def test_the_kit_names_no_tool():
    """Where tools differ, the adapter says so. A tool's name in the kit's code
    would be the first branch on it."""
    from phronon_common.registry import TOOLS
    names = set()
    for key, tool in TOOLS.items():
        if key == "phronon":    # the fleet's own name ("your other Phronon tools"), not a tool to branch on
            continue
        names |= {key.lower(), tool.display_name.lower(), tool.short_name.lower()}
    names |= {"drawbridge", "decision room", "mm_pending", "db_pending"}

    def named(text):
        return sorted(n for n in names if re.search(r"\b%s\b" % re.escape(n), text.lower()))

    assert not named(" ".join(_code_strings(PKG / "account_kit.py"))), "the kit's code names a tool"
    for tpl in TEMPLATES:
        assert not named(tpl.read_text(encoding="utf-8")), tpl.name


def test_tables_refuse_anything_but_a_plain_identifier():
    def nothing(*a):
        return None
    for bad in ("admins; DROP TABLE x", "a b", "", "1col", "admins\n"):
        with pytest.raises(ValueError):
            kit_mod.AccountTables(nothing, nothing, nothing, nothing, accounts=bad)
        with pytest.raises(ValueError):
            kit_mod.AccountTables(nothing, nothing, nothing, nothing, passkey_owner=bad)


def test_install_templates_keeps_the_tools_loader_first_and_runs_once(tmp_path):
    (tmp_path / "backoffice").mkdir()
    (tmp_path / "backoffice" / "base.html").write_text("TOOL BASE {% block content %}{% endblock %}")
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(tmp_path)))
    kit_mod.install_templates(env)
    kit_mod.install_templates(env)
    assert isinstance(env.loader, jinja2.ChoiceLoader) and len(env.loader.loaders) == 2
    assert env.get_template("backoffice/base.html").filename.startswith(str(tmp_path))
    assert env.get_template("account_kit/two_factor_verify.html")


# ── driven ───────────────────────────────────────────────────────────────────

class World:
    """The app, its tables and what it recorded. Built per test."""

    def __init__(self, get_db, tmp_path, last_login_at=None, **adapter):
        from fastapi import FastAPI
        from fastapi.responses import RedirectResponse
        from fastapi.templating import Jinja2Templates
        from fastapi.testclient import TestClient

        self.get_db = get_db
        tag = secrets.token_hex(4)
        self.T, self.PK = f"kit_accounts_{tag}", f"kit_passkeys_{tag}"
        self.run(f"""CREATE TABLE {self.T} (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(255) DEFAULT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'educator',
            is_active TINYINT(1) NOT NULL DEFAULT 1, failed_logins INT NOT NULL DEFAULT 0,
            locked_until DATETIME NULL DEFAULT NULL, last_login_at DATETIME NULL DEFAULT NULL,
            must_change_password TINYINT(1) NOT NULL DEFAULT 0,
            session_epoch INT NOT NULL DEFAULT 0, totp_secret VARCHAR(64) DEFAULT NULL,
            totp_enabled TINYINT(1) NOT NULL DEFAULT 0, totp_backup_codes TEXT)
            AUTO_INCREMENT={secrets.randbelow(10 ** 9) + 10 ** 6}""")
        self.run(f"""CREATE TABLE {self.PK} (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, owner_id INT NOT NULL,
            credential_id VARBINARY(1023) NOT NULL UNIQUE, public_key VARBINARY(2048) NOT NULL,
            sign_count BIGINT UNSIGNED NOT NULL DEFAULT 0, name VARCHAR(60) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_used_at DATETIME DEFAULT NULL)""")

        (tmp_path / "backoffice").mkdir(parents=True, exist_ok=True)
        (tmp_path / "backoffice" / "base.html").write_text(
            "<title>{% block title %}{% endblock %}</title>"
            "<nav>{% if nav_account %}NAV {{ nav_account.email }}{% endif %}</nav>"
            "<main>{% block content %}{% endblock %}</main>{% block scripts %}{% endblock %}")
        templates = Jinja2Templates(directory=str(tmp_path))
        templates.env.globals["asset"] = lambda path: path
        kit_mod.install_templates(templates.env)

        self.mails, self.audits, self.renders = [], [], []
        self.csrf_refuses = False
        mail = types.ModuleType(f"kit_test_mail_{tag}")
        for fn in ("send_two_factor_confirmation", "send_email_change_confirm",
                   "send_email_change_notice"):
            setattr(mail, fn, (lambda name: lambda *a: self.mails.append((name, *a)))(fn))
        sys.modules[mail.__name__] = mail
        self._mail_name = mail.__name__

        def current(request):
            raw = request.cookies.get("kit_session", "")
            if ":" not in raw:
                return None
            aid, ep = raw.split(":", 1)
            row = self.row(int(aid))
            return row if row and str(row["session_epoch"]) == ep else None

        def set_session(resp, aid):
            resp.set_cookie("kit_session", f"{aid}:{self.row(aid)['session_epoch']}")

        def pending(request):
            raw = request.cookies.get("kit_pending")
            return self.row(int(raw)) if raw else None

        def render(request, name, context, *, status_code=200, csrf_for=None, preauth=False):
            self.renders.append((name, csrf_for["id"] if csrf_for else None, preauth))
            ctx = {"request": request, **context,
                   "csrf_token": (f"acct-{csrf_for['id']}" if csrf_for
                                  else "pre" if preauth else ""),
                   "nav_account": context.get("account")}
            return templates.TemplateResponse(request, name, ctx, status_code=status_code)

        def csrf_ok(request, token, account):
            if self.csrf_refuses:
                return False
            return token == (f"acct-{account['id']}" if account else "pre")

        def audit(action, **kw):
            self.audits.append((action, kw.get("admin_id"), kw.get("subject"),
                                kw.get("details"), kw.get("admin_email")))

        settings = dict(
            tool_name="Kit Test Tool", secret_key=SECRET,
            base_url=lambda: "https://kit.example", passkey_base_url=lambda: BASE,
            secure_cookies=lambda: True,
            tables=kit_mod.AccountTables(self.one, self.all, self.run, get_db,
                                         accounts=self.T, passkeys=self.PK,
                                         passkey_owner="owner_id",
                                         last_login_at=last_login_at),
            current_account=current,
            signed_out=lambda request: RedirectResponse("/backoffice/login", status_code=303),
            pending_account=pending, pending_cookie="kit_pending",
            set_session_cookie=set_session, session_cookie="kit_session",
            enrolment_cookie="kit_pending_totp",
            set_enrolment_cookie=lambda resp, s: resp.set_cookie("kit_pending_totp", s,
                                                                 max_age=900),
            render=render, csrf_ok=csrf_ok, audit=audit, bcrypt=bcrypt,
            register_failure=lockout.register_failure,
            client_ip=lambda request: "kit-test-client", login_rate_limit=(10, 60),
            mail_module=mail.__name__)
        settings.update(adapter)
        self.kit = kit_mod.AccountKit(**settings)
        app = FastAPI()
        self.router = kit_mod.build_account_router(self.kit)
        app.include_router(self.router)
        self.app = app
        self.client = lambda: TestClient(app, base_url=BASE, follow_redirects=False)
        from phronon_common.rate_limit import _shared_window
        _shared_window.reset("login:kit-test-client")

    # the adapter's database functions, and the test's
    def _cursor_call(self, sql, params, how):
        conn = self.get_db()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            if how == "one":
                return cur.fetchone()
            if how == "all":
                return cur.fetchall()
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def one(self, sql, params=()):
        return self._cursor_call(sql, params, "one")

    def all(self, sql, params=()):
        return self._cursor_call(sql, params, "all")

    def run(self, sql, params=()):
        return self._cursor_call(sql, params, "run")

    def row(self, aid):
        return self.one(f"SELECT * FROM {self.T} WHERE id=%s", (aid,))

    def account(self, role="educator", **cols):
        email = f"kit-{secrets.token_hex(4)}@example.invalid"
        aid = self.run(f"INSERT INTO {self.T} (email, password_hash, role, display_name) "
                       f"VALUES (%s, %s, %s, 'Kit Person')",
                       (email, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(4)).decode(), role))
        for k, v in cols.items():
            self.run(f"UPDATE {self.T} SET {k}=%s WHERE id=%s", (v, aid))
        return self.row(aid)

    def signed_in(self, acc):
        c = self.client()
        c.cookies.set("kit_session", f"{acc['id']}:{self.row(acc['id'])['session_epoch']}")
        return c

    def actions(self, aid=None):
        return [a[0] for a in self.audits if aid is None or a[1] == aid]

    def drop(self):
        self.run(f"DROP TABLE {self.PK}")
        self.run(f"DROP TABLE {self.T}")
        sys.modules.pop(self._mail_name, None)


@pytest.fixture
def world(test_db, tmp_path):
    made = []

    def build(**adapter):
        w = World(test_db, tmp_path / f"t{len(made)}", **adapter)
        made.append(w)
        return w
    yield build
    for w in made:
        w.drop()


def _tok(acc):
    return f"acct-{acc['id']}"


# the router's shape

def test_the_router_answers_exactly_its_paths(world):
    w = world()
    got = sorted((r.path, m) for r in w.router.routes for m in r.methods)
    expected = sorted(
        [(p, m) for p in ("/backoffice/verify", "/backoffice/two-factor",
                          "/backoffice/account", "/backoffice/account/email/confirm")
         for m in ("GET", "HEAD")]
        + [(p, "POST") for p in kit_mod.PATHS if p != "/backoffice/account"])
    assert got == expected
    legacy = world(legacy_password_path="/backoffice/change-password")
    paths = [(r.path, sorted(r.methods)) for r in legacy.router.routes
             if r.path == "/backoffice/change-password"]
    assert sorted(paths) == [("/backoffice/change-password", ["GET", "HEAD"]),
                             ("/backoffice/change-password", ["POST"])]


def test_every_page_answers_head_as_it_answers_get(world):
    """Mail scanners probe a link with HEAD before a person may open it, and
    the address-change confirmation is a mailed link. The tools' own HEAD loop
    runs over app.routes, which on FastAPI 0.139 never reaches an included
    router's routes: before the kit added HEAD itself, each of these was 405."""
    w = world(legacy_password_path="/backoffice/change-password")
    c = w.client()
    for path in ("/backoffice/verify", "/backoffice/two-factor", "/backoffice/account",
                 "/backoffice/account/email/confirm?token=x", "/backoffice/change-password"):
        get, head = c.get(path), c.head(path)
        assert head.status_code != 405, f"HEAD {path} is refused"
        assert head.status_code == get.status_code, (path, get.status_code, head.status_code)
        assert head.content == b""


# the code prompt

SECRET32 = "JBSWY3DPEHPK3PXP"


def _pending_client(w, acc):
    c = w.client()
    c.cookies.set("kit_pending", str(acc["id"]))
    return c


def test_the_code_prompt_needs_a_pending_login(world):
    w = world()
    c = w.client()
    for r in (c.get("/backoffice/verify"),
              c.post("/backoffice/verify", data={"csrf_token": "pre", "code": "1"})):
        assert r.status_code == 303 and r.headers["location"] == "/backoffice/login"


def test_a_right_code_completes_the_sign_in(world):
    w = world()
    acc = w.account(totp_enabled=1, totp_secret=SECRET32, failed_logins=3)
    c = _pending_client(w, acc)
    page = c.get("/backoffice/verify")
    assert page.status_code == 200 and "Kit Test Tool" in page.text
    assert w.renders[-1] == ("account_kit/two_factor_verify.html", None, True)
    r = c.post("/backoffice/verify",
               data={"csrf_token": "pre", "code": twofactor.current_code(SECRET32)})
    assert r.status_code == 303 and r.headers["location"] == "/backoffice/dashboard"
    assert "kit_session" in r.headers["set-cookie"] and 'kit_pending=""' in r.headers["set-cookie"]
    row = w.row(acc["id"])
    assert row["failed_logins"] == 0 and row["last_login_at"] is not None
    assert w.audits[-1][0] == "login_success" and w.audits[-1][3] == {"second_factor": True}


def test_a_wrong_code_counts_towards_the_lockout(world):
    w = world(error_status=400)
    acc = w.account(totp_enabled=1, totp_secret=SECRET32, failed_logins=lockout.MAX_ATTEMPTS - 1)
    r = _pending_client(w, acc).post("/backoffice/verify",
                                     data={"csrf_token": "pre", "code": "000000"})
    assert r.status_code == 400 and "That code is not valid." in r.text
    row = w.row(acc["id"])
    assert row["failed_logins"] == lockout.MAX_ATTEMPTS and row["locked_until"] is not None
    assert "login_success" not in w.actions()


def test_a_recovery_code_works_once(world):
    w = world()
    codes = twofactor.generate_backup_codes()
    acc = w.account(totp_enabled=1, totp_secret=SECRET32,
                    totp_backup_codes=json.dumps(twofactor.hash_backup_codes(codes, bcrypt)))
    r = _pending_client(w, acc).post("/backoffice/verify",
                                     data={"csrf_token": "pre", "code": codes[0].lower()})
    assert r.status_code == 303
    assert len(json.loads(w.row(acc["id"])["totp_backup_codes"])) == 9
    r = _pending_client(w, acc).post("/backoffice/verify",
                                     data={"csrf_token": "pre", "code": codes[0]})
    assert r.status_code == 200 and "not valid" in r.text


def test_a_temporary_password_lands_where_the_tool_says(world):
    w = world(must_change_url="/backoffice/change-password")
    acc = w.account(totp_enabled=1, totp_secret=SECRET32, must_change_password=1)
    r = _pending_client(w, acc).post(
        "/backoffice/verify", data={"csrf_token": "pre", "code": twofactor.current_code(SECRET32)})
    assert r.headers["location"] == "/backoffice/change-password"


def test_the_sign_in_stamp_can_come_from_the_tool(world):
    from datetime import datetime
    stamp = datetime(2001, 2, 3, 4, 5, 6)
    w = world(last_login_at=lambda: stamp)
    acc = w.account(totp_enabled=1, totp_secret=SECRET32)
    _pending_client(w, acc).post("/backoffice/verify", data={
        "csrf_token": "pre", "code": twofactor.current_code(SECRET32)})
    assert w.row(acc["id"])["last_login_at"] == stamp


# CSRF: a refusing hook stops every POST before it writes anything

def test_every_post_refuses_when_the_tools_csrf_check_says_no(world):
    w = world(legacy_password_path="/backoffice/change-password")
    acc = w.account(totp_enabled=1, totp_secret=SECRET32)
    w.csrf_refuses = True
    before = w.row(acc["id"])
    c = w.signed_in(acc)
    c.cookies.set("kit_pending", str(acc["id"]))
    expect = {
        "/backoffice/verify": (303, None),
        "/backoffice/two-factor": (400, None),
        "/backoffice/passkeys/options": (400, "Please reload the page and try again."),
        "/backoffice/passkeys": (400, "Please reload the page and try again."),
        "/backoffice/passkeys/1/delete": (400, None),
        "/backoffice/login/passkey/options": (400, "Please reload the page and try again."),
        "/backoffice/login/passkey": (400, "Please reload the page and try again."),
        "/backoffice/account/name": (400, None),
        "/backoffice/account/email": (400, None),
        "/backoffice/account/email/confirm": (400, None),
        "/backoffice/account/password": (400, None),
        "/backoffice/change-password": (400, None),
    }
    for path, (status, message) in expect.items():
        r = c.post(path, data={"csrf_token": "x", "code": twofactor.current_code(SECRET32),
                               "action": "disable", "display_name": "Changed",
                               "current_password": PASSWORD, "new_password": "N" * 20,
                               "confirm_password": "N" * 20, "new_email": "x@example.org"})
        assert r.status_code == status, path
        if message:
            assert r.json() == {"error": message}, path
        if path == "/backoffice/verify":
            assert r.headers["location"] == "/backoffice/login"
    assert w.row(acc["id"]) == before
    assert w.audits == [] and w.mails == []


# setting up the authenticator

def _enrol(w, c, acc, replace=False):
    page = c.get("/backoffice/two-factor" + ("?replace=1" if replace else ""))
    secret = c.cookies.get("kit_pending_totp")
    assert secret
    return page, c.post("/backoffice/two-factor", data={
        "csrf_token": _tok(acc), "action": "enable", "code": twofactor.current_code(secret)})


def test_switching_two_factor_on_replacing_it_and_new_codes(world):
    w = world()
    acc = w.account()
    c = w.signed_in(acc)
    page, r = _enrol(w, c, acc)
    assert "max-age=900" in page.headers["set-cookie"].lower()
    assert r.status_code == 200 and r.text.count("<li>") == 10
    assert "data-recovery-codes" in r.text and 'data-recovery-tool="Kit Test Tool"' in r.text
    row = w.row(acc["id"])
    assert row["totp_enabled"] == 1 and len(json.loads(row["totp_backup_codes"])) == 10
    secret = row["totp_secret"]
    r = c.post("/backoffice/two-factor", data={"csrf_token": _tok(acc), "action": "regenerate",
                                               "code": "000000"})
    assert r.status_code == 303 and r.headers["location"] == "/backoffice/account?err=bad_code"
    r = c.post("/backoffice/two-factor", data={"csrf_token": _tok(acc), "action": "regenerate",
                                               "code": twofactor.current_code(secret)})
    assert r.status_code == 200 and r.text.count("<li>") == 10
    _page, r = _enrol(w, c, acc, replace=True)
    assert r.status_code == 200
    assert [m[0] for m in w.mails] == ["send_two_factor_confirmation"] * 3
    assert [m[3] for m in w.mails] == ["enabled", "codes_regenerated", "replaced"]
    assert all(m[1] == acc["email"] and m[2] == "https://kit.example/backoffice/account"
               for m in w.mails)
    assert w.actions(acc["id"]) == ["two_factor_enabled", "two_factor_codes_regenerated",
                                    "two_factor_replaced"]


def test_a_wrong_enrolment_code_writes_nothing(world):
    for status in (200, 400):
        w = world(error_status=status)
        acc = w.account()
        c = w.signed_in(acc)
        c.get("/backoffice/two-factor")
        r = c.post("/backoffice/two-factor", data={"csrf_token": _tok(acc), "action": "enable",
                                                   "code": "000000"})
        assert r.status_code == status and "did not match" in r.text
        assert w.row(acc["id"])["totp_enabled"] == 0 and w.mails == []


def test_only_an_educator_may_switch_it_off(world):
    w = world()
    for role, stays in (("educator", 0), ("admin", 1)):
        acc = w.account(role=role, totp_enabled=1, totp_secret=SECRET32)
        r = w.signed_in(acc).post("/backoffice/two-factor",
                                  data={"csrf_token": _tok(acc), "action": "disable"})
        assert r.status_code == 303 and r.headers["location"] == "/backoffice/two-factor"
        assert w.row(acc["id"])["totp_enabled"] == stays, role


def test_pages_for_nobody_answer_what_the_tool_says(world):
    w = world()
    c = w.client()
    for method, path in (("get", "/backoffice/two-factor"), ("get", "/backoffice/account"),
                         ("post", "/backoffice/two-factor"), ("post", "/backoffice/account/name"),
                         ("post", "/backoffice/account/email"),
                         ("post", "/backoffice/account/password"),
                         ("post", "/backoffice/passkeys/1/delete")):
        r = getattr(c, method)(path)
        assert r.status_code == 303 and r.headers["location"] == "/backoffice/login", path
    for path in ("/backoffice/passkeys/options", "/backoffice/passkeys"):
        r = c.post(path)
        assert r.status_code == 401 and r.json() == {"error": "Please sign in again."}


# passkeys

def _add_passkey(w, c, acc, auth, name="Laptop"):
    opts = c.post("/backoffice/passkeys/options", data={"csrf_token": _tok(acc)})
    assert opts.status_code == 200, opts.text
    return c.post("/backoffice/passkeys", data={"csrf_token": _tok(acc),
                                                "credential": auth.create(opts.text),
                                                "name": name})


def _passkey_login(w, auth, replay=None, **kw):
    c = w.client()
    opts = c.post("/backoffice/login/passkey/options", data={"csrf_token": "pre"})
    assert opts.status_code == 200, opts.text
    if replay is None:
        c.sent = (c.cookies.get("passkey_challenge"), auth.get(opts.text, **kw))
    else:
        domain = next(k.domain for k in c.cookies.jar if k.name == "passkey_challenge")
        c.cookies.set("passkey_challenge", replay.sent[0], domain=domain, path="/")
        c.sent = replay.sent
    return c, c.post("/backoffice/login/passkey", data={"csrf_token": "pre",
                                                         "credential": c.sent[1]})


def test_a_passkey_is_added_signs_in_alone_and_works_once(world):
    from phronon_common.testing.soft_authenticator import SoftAuthenticator
    w = world()
    acc = w.account(totp_enabled=1, totp_secret=SECRET32)
    auth = SoftAuthenticator(origin=BASE, counts_signatures=False)
    r = _add_passkey(w, w.signed_in(acc), acc, auth)
    assert r.status_code == 200 and r.json() == {"ok": True}
    rows = w.all(f"SELECT name, owner_id FROM {w.PK}")
    assert rows == [{"name": "Laptop", "owner_id": acc["id"]}]
    assert w.mails[-1][3] == "passkey_added"
    first, r = _passkey_login(w, auth)
    assert r.status_code == 200 and r.json() == {"redirect": "/backoffice/dashboard"}
    assert "kit_session" in r.headers["set-cookie"]
    assert w.audits[-1][0] == "login_success" and w.audits[-1][3] == {"passkey": True}
    # the one-use rule: the same challenge and answer, sent again
    _c, r = _passkey_login(w, auth, replay=first)
    assert r.status_code == 400 and "redirect" not in r.json()
    assert w.audits[-1][3] == {"passkey": True, "challenge_used": True}
    assert w.row(acc["id"])["failed_logins"] == 0      # a replay is not a guess


def test_a_refused_passkey_counts_and_a_locked_account_is_refused(world):
    from phronon_common.testing.soft_authenticator import SoftAuthenticator
    w = world()
    acc = w.account()
    auth = SoftAuthenticator(origin=BASE)
    _add_passkey(w, w.signed_in(acc), acc, auth)
    _c, r = _passkey_login(w, auth, tamper=True)
    assert r.status_code == 400 and w.row(acc["id"])["failed_logins"] == 1
    w.run(f"UPDATE {w.T} SET locked_until=DATE_ADD(UTC_TIMESTAMP(), INTERVAL 5 MINUTE) "
          f"WHERE id=%s", (acc["id"],))
    _c, r = _passkey_login(w, auth)
    assert r.status_code == 429 and r.json() == {"error": lockout.LOCKED_MESSAGE}
    assert w.audits[-1][0] == "login_locked"


def test_passkey_sign_in_is_rate_limited_by_the_tools_numbers(world):
    w = world(login_rate_limit=(3, 60))
    c = w.client()
    codes = [c.post("/backoffice/login/passkey/options", data={"csrf_token": "pre"}).status_code
             for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_a_passkey_is_removed_by_its_owner_only(world):
    from phronon_common.testing.soft_authenticator import SoftAuthenticator
    w = world()
    owner, other = w.account(), w.account()
    _add_passkey(w, w.signed_in(owner), owner, SoftAuthenticator(origin=BASE))
    pid = w.one(f"SELECT id FROM {w.PK}")["id"]
    r = w.signed_in(other).post(f"/backoffice/passkeys/{pid}/delete",
                                data={"csrf_token": _tok(other)})
    assert r.headers["location"] == "/backoffice/account" and w.one(f"SELECT id FROM {w.PK}")
    r = w.signed_in(owner).post(f"/backoffice/passkeys/{pid}/delete",
                                data={"csrf_token": _tok(owner)})
    assert r.headers["location"] == "/backoffice/account?msg=passkey_removed"
    assert not w.one(f"SELECT id FROM {w.PK}")
    assert w.actions(owner["id"])[-1] == "passkey_removed"


# the Manage account page

def test_the_page_renders_the_row_and_only_keyed_texts(world):
    w = world()
    acc = w.account()
    c = w.signed_in(acc)
    r = c.get("/backoffice/account?msg=name_saved&err=<b>x</b>")
    assert r.status_code == 200 and f"NAV {acc['email']}" in r.text
    assert "Your name has been updated." in r.text and "<b>x</b>" not in r.text
    assert w.renders[-1] == ("account_kit/account.html", acc["id"], False)
    assert 'name="new_email"' in r.text and "/backoffice/two-factor" in r.text


def test_a_temporary_password_hides_the_rest_and_the_handlers_refuse(world):
    w = world()
    acc = w.account(must_change_password=1)
    c = w.signed_in(acc)
    page = c.get("/backoffice/account").text
    assert 'name="new_email"' not in page and 'name="new_password"' in page
    for path in ("/backoffice/account/name", "/backoffice/account/email"):
        r = c.post(path, data={"csrf_token": _tok(acc), "display_name": "x",
                               "current_password": PASSWORD, "new_email": "a@b.cd"})
        assert r.headers["location"] == "/backoffice/account?err=password_needed"
    for path in ("/backoffice/passkeys/options", "/backoffice/passkeys"):
        r = c.post(path, data={"csrf_token": _tok(acc)})
        assert r.status_code == 403 and r.json() == {"error": "Set a new password first."}


@pytest.mark.parametrize("layout", [
    kit_mod.AccountPageLayout(back_link_while_must_change=True, section_wrapper=False,
                              password_tools=True),
    kit_mod.AccountPageLayout(back_link_while_must_change=False, section_wrapper=True,
                              password_tools=False)], ids=["mm-like", "db-like"])
def test_each_layout_choice_changes_what_it_names(world, layout):
    w = world(layout=layout)
    page = w.signed_in(w.account(must_change_password=1)).get("/backoffice/account").text
    assert ("← Dashboard" in page) is layout.back_link_while_must_change
    assert ('<div class="bo-account">' in page) is layout.section_wrapper
    assert ("pw-generate" in page) is layout.password_tools
    assert ("users-password.js" in page) is layout.password_tools
    plain = w.signed_in(w.account()).get("/backoffice/account").text
    assert "← Dashboard" in plain


def test_changing_the_name(world):
    for status in (200, 400):
        w = world(error_status=status)
        acc = w.account()
        c = w.signed_in(acc)
        r = c.post("/backoffice/account/name", data={"csrf_token": _tok(acc), "display_name": " "})
        assert r.status_code == status and "Enter a name." in r.text
        r = c.post("/backoffice/account/name", data={"csrf_token": _tok(acc),
                                                     "display_name": "New\nName\x07"})
        assert r.headers["location"] == "/backoffice/account?msg=name_saved"
        assert w.row(acc["id"])["display_name"] == "NewName"
        assert w.actions(acc["id"]) == ["account_name_changed"]


def test_an_address_change_is_proved_by_the_new_mailbox(world):
    w = world(error_status=400)
    acc, other = w.account(), w.account()
    c = w.signed_in(acc)

    def ask(new, password=PASSWORD):
        return c.post("/backoffice/account/email", data={
            "csrf_token": _tok(acc), "new_email": new, "current_password": password})

    r = ask("new@example.org", password="wrong")
    assert r.headers["location"] == "/backoffice/account?err=wrong_password"
    assert w.audits[-1][0] == "email_change_refused"
    r = ask("not an address")
    assert r.status_code == 400 and "does not look like" in r.text
    w2 = world()
    acc2 = w2.account()
    other2 = w2.account()
    c2 = w2.signed_in(acc2)
    r = c2.post("/backoffice/account/email", data={
        "csrf_token": _tok(acc2), "new_email": other2["email"], "current_password": PASSWORD})
    assert r.headers["location"] == "/backoffice/account?err=email_taken"
    new = f"moved-{secrets.token_hex(3)}@example.invalid"
    r = c2.post("/backoffice/account/email", data={
        "csrf_token": _tok(acc2), "new_email": new.upper(), "current_password": PASSWORD})
    assert r.headers["location"] == "/backoffice/account?msg=email_sent"
    assert w2.row(acc2["id"])["email"] == acc2["email"]           # nothing written yet
    confirm, notice = w2.mails
    assert confirm[0] == "send_email_change_confirm" and confirm[1] == new
    assert confirm[2].startswith("https://kit.example/backoffice/account/email/confirm?token=")
    assert notice == ("send_email_change_notice", acc2["email"], new)
    token = confirm[2].split("token=", 1)[1]
    anon = w2.client()
    page = anon.get(f"/backoffice/account/email/confirm?token={token}")
    assert page.status_code == 200 and new in page.text and acc2["email"] in page.text
    assert w2.renders[-1] == ("account_kit/account_confirm_email.html", None, True)
    assert w2.row(acc2["id"])["email"] == acc2["email"]           # opening writes nothing
    r = anon.post("/backoffice/account/email/confirm", data={"csrf_token": "pre", "token": token})
    assert r.status_code == 303 and r.headers["location"] == "/backoffice/login?msg=email_changed"
    assert 'kit_session=""' in r.headers["set-cookie"]
    row = w2.row(acc2["id"])
    assert row["email"] == new and row["session_epoch"] == acc2["session_epoch"] + 1
    assert w2.audits[-1][0] == "email_changed" and w2.audits[-1][3] == {"from": acc2["email"]}
    r = anon.post("/backoffice/account/email/confirm", data={"csrf_token": "pre", "token": token})
    assert r.status_code == 200 and "expired" in r.text            # the link is spent
    assert w.row(other["id"])["email"] == other["email"]


def test_address_change_requests_are_limited_per_account(world):
    w = world()
    acc = w.account()
    c = w.signed_in(acc)
    statuses = [c.post("/backoffice/account/email", data={
        "csrf_token": _tok(acc), "new_email": f"x{i}@example.org",
        "current_password": PASSWORD}).headers["location"] for i in range(4)]
    assert statuses[:3] == ["/backoffice/account?msg=email_sent"] * 3
    assert statuses[3] == "/backoffice/account?err=too_many"


def test_changing_the_password(world):
    for checks in (True, False):
        w = world(password_change_checks_confirmation=checks)
        acc = w.account(must_change_password=1)
        c = w.signed_in(acc)

        def change(current, new, confirm):
            return c.post("/backoffice/account/password", data={
                "csrf_token": _tok(acc), "current_password": current,
                "new_password": new, "confirm_password": confirm})

        r = change("wrong", "N" * 20, "N" * 20)
        assert r.status_code == 200 and "Current password is incorrect." in r.text
        r = change(PASSWORD, "short", "short")
        assert r.status_code == 200 and "at least" in r.text
        r = change(PASSWORD, "N" * 20, "M" * 20)
        if checks:
            assert "New passwords do not match." in r.text
            r = change(PASSWORD, PASSWORD, PASSWORD)
            assert "must differ" in r.text
            assert w.row(acc["id"])["session_epoch"] == 0
            r = change(PASSWORD, "N" * 20, "N" * 20)
        assert r.status_code == 303 and r.headers["location"] == "/backoffice/dashboard"
        row = w.row(acc["id"])
        assert row["must_change_password"] == 0 and row["session_epoch"] == 1
        assert bcrypt.checkpw(b"N" * 20, row["password_hash"].encode())
        assert f"kit_session={acc['id']}:1" in r.headers["set-cookie"]
        assert w.actions(acc["id"]) == ["password_changed"]


def test_required_password_fields_are_the_tools_choice(world):
    w = world(password_form_required=("current_password", "new_password"))
    acc = w.account()
    r = w.signed_in(acc).post("/backoffice/account/password", data={"csrf_token": _tok(acc)})
    assert r.status_code == 422
    assert [e["loc"][-1] for e in r.json()["detail"]] == ["current_password", "new_password"]
    w = world()
    acc = w.account()
    r = w.signed_in(acc).post("/backoffice/account/password", data={"csrf_token": _tok(acc)})
    assert r.status_code == 200 and "Current password is incorrect." in r.text


def test_the_old_password_address_still_answers(world):
    w = world(legacy_password_path="/backoffice/change-password")
    acc = w.account()
    c = w.signed_in(acc)
    r = c.get("/backoffice/change-password")
    assert r.status_code == 303 and r.headers["location"] == "/backoffice/account"
    r = c.post("/backoffice/change-password", data={
        "csrf_token": _tok(acc), "current_password": PASSWORD,
        "new_password": "N" * 20, "confirm_password": "N" * 20})
    assert r.status_code == 303 and w.row(acc["id"])["session_epoch"] == 1
