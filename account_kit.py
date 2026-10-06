"""The account kit: a tool's account routes, written once (FL-083).

WHAT THIS IS
Every tool carried its own copy of the routes an account holder uses on
themselves: signing in with a password and then the code, signing out, the
password-reset links, setting up and replacing the authenticator app, new
recovery codes, passkeys (add, remove, sign in), and the Manage account page
(name, e-mail change with its mailed confirmation, password change); and of
two things around them: the gate that holds an account with a temporary
password (or an administrator without an authenticator) to the pages it may
use, and the administrator's "reset this account's two-factor" button. The
logic was the same everywhere; local names, table columns, cookie names and a
handful of policies were not. Moral Mirror and Drawbridge mount this router
and gate; the other seven tools keep their own code for now and adopt the kit
one at a time.

    from phronon_common import account_kit
    account_kit.install_templates(templates.env)
    kit = account_kit.AccountKit(...)
    app.include_router(account_kit.build_account_router(kit))
    ...
    app.middleware("http")(account_kit.account_gate(kit))

The routes, form fields, cookies, redirects, audit actions and mails are the
ones the tools already had. Password hashes, TOTP secrets, recovery codes,
passkeys and reset tokens stay in the tool's own tables, read and written as
before, so a credential, a session or a mailed link issued earlier still
works.

THE POLICIES ARE THE FLEET'S (owner's decision, 4 October 2026, FL-083)
Where the two pilot tools differed in policy, Drawbridge's rule is the kit's
rule for every tool, because it was the stricter one each time:
  (a) lockout: phronon_common.lockout (one minute after five failures,
      doubling), for a wrong password, a wrong code and a refused passkey;
  (b) a form re-shown with a validation error answers 400;
  (c) sign-in: five attempts a minute per address, shared by the password
      form and the passkey; a locked account is refused (429) before its
      password is checked; an unknown, wrong or deactivated account hears
      "Invalid email or password.";
  (d) password reset: five requests per five minutes per address; a
      deactivated account gets no link (and is told nothing different); a
      request that is neither "send me a link" nor "set this password" is a
      400; completing a reset does not lift a lockout;
  (e) sign-out needs a session and a token minted for that account.

WHAT A TOOL SUPPLIES — the `AccountKit` adapter
Everything that is the tool's own: its tables (`AccountTables`) and database
functions, its session (who is signed in, how a session or pending-login
cookie is issued, what "signed out" answers), its pages (`render` puts a page
inside the tool's own layout; the sign-in and reset pages are the tool's own
templates, see below), its CSRF check, its audit recorder and its mail module.
Nothing in here branches on a tool's name: where the two pilot tools still
behave differently, the difference is a named field of the adapter, and its
docstring says whether it is deliberate or an accident kept so that adopting
the kit changed nothing.

TEMPLATES
`account_templates/` ships in the package (pyproject package-data) and is
reached as `account_kit/<name>.html` once `install_templates` has added it to
the tool's Jinja environment. Each extends the tool's own
"backoffice/base.html", so the pages render inside the tool's layout and nav.
The sign-in page and the password-reset page are the tool's own
(`backoffice/login.html`, `backoffice/password_reset.html`): they are each
tool's branded entrance. The kit renders them with `error`, `notice` (sign-in)
or `token`, `error`, `success`, `message` (reset), and the `csrf_token` the
tool's `render` supplies.

WHAT STAYS IN THE TOOL
The users list and everything else an administrator does to other accounts
(invite, edit, deactivate, delete, set a password, send a reset link), the
participant side, and the two page templates above.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Optional

import jinja2
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

from . import account as account_mod
from . import lockout
from . import once as _once
from . import passkeys
from . import passwords as pw_policy
from . import twofactor
from .rate_limit import is_allowed

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "account_templates"
#: The name the kit's templates are reached under in a tool's environment.
TEMPLATE_PREFIX = "account_kit"
#: The tool's own pages the kit renders (see TEMPLATES above).
LOGIN_TEMPLATE = "backoffice/login.html"
RESET_TEMPLATE = "backoffice/password_reset.html"

LOGIN_URL = "/backoffice/login"
LOGOUT_URL = "/backoffice/logout"
RESET_URL = "/backoffice/password-reset"
VERIFY_URL = "/backoffice/verify"
DASHBOARD_URL = "/backoffice/dashboard"
ACCOUNT_URL = "/backoffice/account"
TWO_FACTOR_URL = "/backoffice/two-factor"
USERS_URL = "/backoffice/users"
ADMIN_TWO_FACTOR_RESET_URL = "/backoffice/users/{user_id}/reset-two-factor"

#: (b) A form re-shown with a validation error (a wrong code, an invalid name
#: or address, a dead confirmation link) answers 400.
RESHOWN = 400
#: (c) Sign-in attempts per address: (requests, seconds), one budget shared by
#: the password form and the passkey, which nginx's exact-match limit on
#: /backoffice/login does not cover.
SIGN_IN_LIMIT = (5, 60)
#: (d) Password-reset requests per address: (requests, seconds). Each one can
#: send a mail.
RESET_LIMIT = (5, 300)
#: (c) What a failed password sign-in hears, whatever the reason: an unknown
#: address, a wrong password, a deactivated account.
SIGN_IN_REFUSED = "Invalid email or password."
RESET_SENT = "If that email is registered you will receive a reset link shortly."
RESET_DONE = "Password updated. You can now log in."
RESET_DEAD = "Token is invalid or expired."

#: Paths a signed-in account with a temporary password may still reach: the
#: account page carries the password form (and shows nothing else in that
#: state), and the rest is signing in and out. A prefix list, as the tools had
#: it. The tool's legacy password address, and for one tool the enrolment
#: page, are added in `account_gate`.
MUST_CHANGE_OPEN = (ACCOUNT_URL, LOGOUT_URL, LOGIN_URL, RESET_URL, VERIFY_URL)
#: Paths an administrator without an authenticator may still reach. Enrolling
#: is the one thing such an account may do.
ENROLMENT_OPEN = (TWO_FACTOR_URL, LOGOUT_URL, LOGIN_URL, RESET_URL, VERIFY_URL)

def _opens(path: str, open_paths: tuple) -> bool:
    """Is `path` one of `open_paths` or below one? A bare prefix test let any
    future `/backoffice/accounts...` or `/backoffice/login-as` through
    (review, 5 October 2026)."""
    return any(path == p or path.startswith(p + "/") for p in open_paths)


#: Fixed texts, addressed by key. The redirect after a POST carries `?msg=` /
#: `?err=`, and the KEY is looked up here: a page that prints back whatever the
#: query string says is a page that can be sent to somebody saying anything.
#: (Identical in both pilot tools; a tool's sign-in page reads the same table
#: for the `?msg=email_changed` notice.)
ACCOUNT_MESSAGES = {
    "name_saved": "Your name has been updated.",
    "email_sent": ("Almost done: open the link in the mail we just sent to the new "
                   "address. Until you do, this account keeps its current address."),
    "email_changed": "Your e-mail address has been changed. Please sign in again.",
    "passkey_removed": "The passkey has been removed.",
}
ACCOUNT_ERRORS = {
    "password_needed": "Set a new password first — the rest of this page unlocks afterwards.",
    "wrong_password": "That is not your current password.",
    "email_taken": "That address is already in use by another account here.",
    "link_dead": ("That confirmation link has expired or is no longer valid. "
                  "Request the change again."),
    "bad_code": "That code is not valid. New recovery codes were not issued.",
    "too_many": ("Too many address-change requests. Try again in an hour."),
}

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _ident(name: str) -> str:
    """A table or column name, refused unless it is a plain identifier: these
    are interpolated into SQL, so only the tool's own constants may reach here."""
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise ValueError(f"not a plain SQL identifier: {name!r}")
    return name


@dataclass(frozen=True)
class AccountTables:
    """Where the tool keeps its accounts and passkeys, and how to reach them.

    The five functions are the tool's own database helpers, so connections,
    pooling and commits stay exactly as the tool has them. Parameters are
    passed as a tuple.
    """
    #: (sql, params) -> one row as a dict, or None.
    query_one: Callable[[str, tuple], Optional[dict]]
    #: (sql, params) -> list of rows as dicts.
    query_all: Callable[[str, tuple], list]
    #: (sql, params) -> anything; runs one committed statement.
    execute: Callable[[str, tuple], Any]
    #: () -> a DB-API connection. `passkeys.record_sign_in` needs the cursor's
    #: rowcount to decide whether a sign-in won its one use of the challenge.
    get_conn: Callable[[], Any]
    #: [(sql, params), ...] -> None; runs the statements in ONE transaction
    #: (a completed reset changes the password and spends every link at once).
    transaction: Callable[[list], Any]
    accounts: str = "admins"
    passkeys: str = "passkeys"
    #: The passkey table's column naming the account. Moral Mirror's says
    #: `educator_id`, Drawbridge's `admin_id`: a historic naming, not a design.
    passkey_owner: str = "admin_id"
    reset_tokens: str = "password_reset_tokens"
    #: The reset-token table's column naming the account (Moral Mirror
    #: `educator_id`, Drawbridge `admin_id`, as for passkeys).
    reset_token_owner: str = "admin_id"
    #: The column that marks a reset link spent. A name ending in `_at` is a
    #: timestamp, NULL until the link is used; any other name is a TINYINT,
    #: 0 until it is used. Drawbridge's table has `used`. Moral Mirror's live
    #: table has `used_at` (migration 001; its 004 changed nothing, being a
    #: CREATE TABLE IF NOT EXISTS), although its old code asked for `used`
    #: (MM-008).
    reset_token_spent: str = "used"
    #: How the kit stamps a time it writes (`last_login_at` on a completed
    #: sign-in, a reset link's expiry): None writes the database's NOW()
    #: (Moral Mirror, whose pool sets no time zone); a function supplies "now"
    #: instead (Drawbridge: Python's UTC clock). KEPT so each column means
    #: what it meant; the two agree only where the MySQL session clock is UTC.
    #: An expiry is CHECKED against the database's NOW() in both tools.
    clock: Optional[Callable[[], Any]] = None
    #: The account table's password-hash column (Whiteout's is `pw_hash`).
    password_column: str = "password_hash"
    #: The account table's display-name column (Polarity Profiler's is `name`).
    #: The kit's pages read the value as `account.display_name` whatever it is.
    name_column: str = "display_name"

    def __post_init__(self):
        for name in (self.accounts, self.passkeys, self.passkey_owner, self.reset_tokens,
                     self.reset_token_owner, self.reset_token_spent, self.password_column,
                     self.name_column):
            _ident(name)


@dataclass(frozen=True)
class AccountPageLayout:
    """The three ways the two pilot tools' Manage account pages differed.

    All three are presentation, all three look accidental (each tool improved
    its own copy and the other never heard), and all three are kept so that the
    page each tool shows did not change on adoption. Harmonising them is one
    decision for the owner, then one edit here.
    """
    #: Show "← Dashboard" even while a temporary password is in force (Moral
    #: Mirror) — the dashboard then bounces back here. Drawbridge hides it.
    back_link_while_must_change: bool = False
    #: Wrap the sections in `<div class="bo-account">`, which spaces them
    #: (Drawbridge). Moral Mirror's page has no wrapper.
    section_wrapper: bool = True
    #: Show / Generate buttons beside the new-password field, with
    #: users-password.js (Moral Mirror). Drawbridge has a plain field.
    password_tools: bool = False


@dataclass(frozen=True, kw_only=True)
class AccountKit:
    """Everything the account routes need from the tool that mounts them.

    Keyword-only: an adapter names every field it sets."""

    # ── who the tool is ──────────────────────────────────────────────────────
    #: The product name: the authenticator app's account label (TOTP issuer),
    #: the passkey's relying-party name, and the page titles.
    tool_name: str
    #: The tool's signing key (APP_SECRET_KEY): the address-change links, the
    #: passkey challenge cookie and the passkey user handle are signed with it,
    #: exactly as before, so links and passkeys issued earlier stay valid.
    secret_key: str
    #: () -> the absolute base URL mails link to. Called each time, so a test
    #: (or a re-read config) is honoured.
    base_url: Callable[[], str]
    #: () -> the address a passkey is bound to (the tool's own domain).
    passkey_base_url: Callable[[], str]
    #: () -> whether cookies carry Secure.
    secure_cookies: Callable[[], bool]

    # ── its data ─────────────────────────────────────────────────────────────
    tables: AccountTables

    # ── its session ──────────────────────────────────────────────────────────
    #: request -> the signed-in account row (every column), or None. Never
    #: raises for a missing or dead session: the JSON routes answer 401 rather
    #: than redirecting. It returns None for a deactivated account, and it may
    #: raise when the database is down (the sign-in page then shows the form).
    current_account: Callable[[Request], Optional[dict]]
    #: request -> what a page answers when nobody is signed in. May raise
    #: (Drawbridge raises its 302); Moral Mirror returns a 303.
    signed_out: Callable[[Request], Response]
    #: request -> the account whose password was right and whose code is still
    #: owed, or None. The code prompt trusts it: it must return None for an
    #: account that may no longer sign in (deactivated).
    pending_account: Callable[[Request], Optional[dict]]
    #: The pending-login cookie, deleted once the code is accepted.
    pending_cookie: str
    #: (response, account_id) -> mark a sign-in whose password was right and
    #: whose code is still owed (the cookie `pending_account` reads).
    set_pending_cookie: Callable[[Response, int], None]
    #: (response, account_id) -> issue a fresh session cookie.
    set_session_cookie: Callable[[Response, int], None]
    #: The session cookie, deleted on sign-out and when an address change ends
    #: every session.
    session_cookie: str
    #: The cookie carrying a not-yet-confirmed authenticator secret.
    enrolment_cookie: str
    #: (response, secret) -> set it. Kept in the tool so the published cookie
    #: table and the max_age stay where closing_audit.py compares them.
    set_enrolment_cookie: Callable[[Response, str], None]

    # ── its pages ────────────────────────────────────────────────────────────
    #: render(request, template, context, *, status_code, csrf_for, preauth)
    #: -> a response rendering `template` with the tool's own globals.
    #: It must put a CSRF token in the context as `csrf_token`: bound to
    #: `csrf_for` (the signed-in account row) when given, a fresh pre-sign-in
    #: token when `preauth`, otherwise whatever the tool's forms carry. If the
    #: context holds `account`, it is the page's subject — map it to whatever the
    #: tool's base layout reads for its nav.
    render: Callable[..., Response]
    #: (request, submitted_token, account_or_None) -> may this POST proceed?
    #: None means a pre-sign-in form. A tool whose CSRF check already runs
    #: app-wide (Moral Mirror's dependency, 403 before any route) answers True;
    #: its tokens are bound to the session cookie, so a token minted for one
    #: account is refused for another there. A False here is answered the way
    #: Drawbridge answered it: 400 on a page, a JSON error on the passkey calls,
    #: the sign-in page from the code prompt.
    csrf_ok: Callable[[Request, str, Optional[dict]], bool]
    #: request -> what a signed-in account that is not an administrator hears
    #: from the admin "reset two-factor" action. May raise. Moral Mirror
    #: redirects to the dashboard (303), Drawbridge answers 403: ACCIDENTAL,
    #: kept (each tool's other admin routes answer the same way).
    not_an_admin: Callable[[Request], Response]
    #: (request, admin_row) -> what the administrator sees after resetting
    #: another account's two-factor: the tool's own users list. Moral Mirror
    #: renders it with a note saying so; Drawbridge redirects to /backoffice/users
    #: (303) and says nothing. ACCIDENTAL, kept.
    after_two_factor_reset: Callable[[Request, dict], Response]

    # ── its policy ───────────────────────────────────────────────────────────
    #: The tool's phronon_common.audit.AuditRecorder.
    audit: Callable[..., Any]
    #: The bcrypt module (passed in: this package declares no bcrypt).
    bcrypt: Any
    #: request -> the address sign-in and reset requests are rate-limited by.
    #: Moral Mirror's is proxy-aware (phronon_common.rate_limit.client_ip);
    #: Drawbridge's is the connection's own address, as its login had it.
    client_ip: Callable[[Request], str]
    #: How long a mailed reset link lives, in hours (each tool's
    #: RESET_TOKEN_HOURS).
    reset_token_hours: int = 2
    #: The tool's mail module, imported by name at send time (so a test that
    #: replaces one of its functions is honoured): it provides
    #: send_password_reset, send_two_factor_confirmation,
    #: send_two_factor_reset_notice, send_email_change_confirm and
    #: send_email_change_notice.
    mail_module: str = "services.email"
    #: Where "could not send" is logged — the tool's own logger, so the line
    #: lands where it always did.
    logger: logging.Logger = field(default=logger)
    #: An older address the password form also answers at, and whose GET
    #: redirects to the account page (Drawbridge: /backoffice/change-password,
    #: kept for bookmarks and the fleet's probes). Deliberate.
    legacy_password_path: Optional[str] = None
    layout: AccountPageLayout = field(default_factory=AccountPageLayout)

    # ── differences kept as they were ────────────────────────────────────────
    # Each looks ACCIDENTAL (one tool improved its copy and the other never
    # heard) and is kept so that adopting the kit changed nothing a person or
    # a browser can see. Harmonising one is an owner's decision, then one edit
    # here. The defaults are what a tool adopting the kit should normally get.

    #: Where a completed sign-in goes while a temporary password is in force.
    #: Drawbridge still says /backoffice/change-password, which redirects to
    #: the account page; Moral Mirror goes there directly.
    must_change_url: str = ACCOUNT_URL
    #: Password-change fields (other than the CSRF token) a request must carry
    #: or be refused with FastAPI's 422. Moral Mirror declared current and new
    #: password required. Only a hand-made request can tell.
    password_form_required: tuple = ()
    #: Declare the `csrf_token` field required on the sign-in, sign-out,
    #: password-reset and password-change forms, so a request without it is
    #: FastAPI's 422 rather than a refused token (Drawbridge). Moral Mirror's
    #: app-wide CSRF dependency answers such a request with its 403 first.
    #: Only a hand-made request can tell.
    csrf_field_required: bool = False
    #: The redirect status of the sign-in page for a browser already signed in:
    #: Moral Mirror 303, Drawbridge 307 (the framework's default). Both send a
    #: GET to the dashboard.
    signed_in_redirect_status: int = 303
    #: request -> True to delete the session cookie when the sign-in page is
    #: reached with one it does not accept (Drawbridge: when its signature is
    #: good but the session is not current, so a stale cookie cannot loop).
    #: None leaves the cookie alone (Moral Mirror). Never asked when the
    #: session lookup failed, so an outage cannot sign anybody out.
    drop_dead_session_cookie: Optional[Callable[[Request], bool]] = None
    #: The enrolment page stays reachable while a temporary password is in
    #: force (Drawbridge). Moral Mirror sends such an account to the password
    #: form first.
    must_change_allows_two_factor: bool = False
    # ── data the 6 October 2026 adopters hold differently ─────────────────────
    #: (password, stored hash) -> does it match? None: bcrypt (the fleet's
    #: hash). Layoff still holds a few werkzeug pbkdf2 hashes from its Flask
    #: days; its function knows both. New hashes are always bcrypt.
    verify_password: Optional[Callable[[str, str], bool]] = None
    #: Strip surrounding blanks from every password before checking or
    #: hashing it. Controversy Generator stored its hashes that way, so an
    #: account whose password ended in a blank still signs in with it.
    strip_passwords: bool = False
    #: Path prefixes the gate guards (must-change, forced enrolment). Layoff's
    #: administrators also work under /admin.
    gated_prefixes: tuple = ("/backoffice",)

    #: request -> the row the gate judges (needs must_change_password, role,
    #: totp_enabled), or None. None here means `current_account`. Drawbridge's
    #: gate read the session cookie's account id WITHOUT checking the session
    #: epoch, its age or is_active, so a dead session meets the gate's
    #: redirect first and the sign-in page one hop later.
    gate_account: Optional[Callable[[Request], Optional[dict]]] = None


# ── templates ────────────────────────────────────────────────────────────────

def install_templates(env: jinja2.Environment) -> None:
    """Let a tool's Jinja environment find the kit's pages as `account_kit/…`.

    The tool's own loader stays first, so "backoffice/base.html" — which every
    kit page extends — is the tool's. Calling this twice is harmless."""
    if getattr(env, "_account_kit_installed", False):
        return
    kit_loader = jinja2.PrefixLoader(
        {TEMPLATE_PREFIX: jinja2.FileSystemLoader(str(TEMPLATE_DIR))})
    env.loader = jinja2.ChoiceLoader([env.loader, kit_loader]) if env.loader else kit_loader
    env._account_kit_installed = True


def template(name: str) -> str:
    return f"{TEMPLATE_PREFIX}/{name}"


# ── the router ───────────────────────────────────────────────────────────────

def build_account_router(kit: AccountKit) -> APIRouter:
    """The account routes for one tool. Mount with `app.include_router`."""
    router = APIRouter()
    T = kit.tables.accounts
    PK = kit.tables.passkeys
    OWNER = kit.tables.passkey_owner
    RT = kit.tables.reset_tokens
    RT_OWNER = kit.tables.reset_token_owner
    SPENT = kit.tables.reset_token_spent
    # A spent-at timestamp is NULL until the link is used; a flag is 0.
    UNSPENT, SPEND = ((f"{SPENT} IS NULL", f"{SPENT}=NOW()") if SPENT.endswith("_at")
                      else (f"{SPENT}=0", f"{SPENT}=1"))
    q1, qall, run = kit.tables.query_one, kit.tables.query_all, kit.tables.execute
    email_signer = account_mod.email_change_signer(kit.secret_key)
    page_kit = {
        "tool_name": kit.tool_name,
        "back_link_while_must_change": kit.layout.back_link_while_must_change,
        "section_wrapper": kit.layout.section_wrapper,
        "password_tools": kit.layout.password_tools,
    }

    def mail(name: str) -> Callable:
        return getattr(importlib.import_module(kit.mail_module), name)

    def page(request, name, *, status_code=200, csrf_for=None, preauth=False, **context):
        context["account_kit"] = page_kit
        return kit.render(request, template(name), context, status_code=status_code,
                          csrf_for=csrf_for, preauth=preauth)

    def tool_page(request, path, *, status_code=200, **context):
        """One of the tool's own pre-sign-in pages (sign-in, reset)."""
        return kit.render(request, path, context, status_code=status_code, csrf_for=None,
                          preauth=True)

    def csrf_field():
        """The CSRF field, declared required where the tool declared it so."""
        return Form(...) if kit.csrf_field_required else Form("")

    def redirect(url: str) -> RedirectResponse:
        return RedirectResponse(url, status_code=303)

    def bad_csrf() -> HTTPException:
        return HTTPException(400, "Bad CSRF token")

    def json_error(message: str, status: int = 400) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    def two_factor_mail(account: dict, event: str) -> BackgroundTask:
        """The confirmation mail, sent after the response, so a slow mail server
        never delays the one page that shows the recovery codes. The shared
        sender logs a failure and never raises."""
        return BackgroundTask(mail("send_two_factor_confirmation"), account["email"],
                              f"{kit.base_url()}{ACCOUNT_URL}", event)

    dummy: list = []

    def dummy_hash() -> bytes:
        """A bcrypt hash of nothing anybody knows, made once per router."""
        if not dummy:
            dummy.append(kit.bcrypt.hashpw(secrets.token_bytes(16), kit.bcrypt.gensalt()))
        return dummy[0]

    PW, NAME = kit.tables.password_column, kit.tables.name_column

    def clean(password: str) -> str:
        return (password or "").strip() if kit.strip_passwords else (password or "")

    def password_ok(password: str, row) -> bool:
        """The password against the row's hash. No row: a throwaway bcrypt
        check, so an unknown address takes as long as a wrong password."""
        if not row:
            kit.bcrypt.checkpw(clean(password).encode()[:72], dummy_hash())
            return False
        stored = row.get(PW) or ""
        if kit.verify_password is not None:
            return bool(kit.verify_password(clean(password), stored))
        try:
            return kit.bcrypt.checkpw(clean(password).encode()[:72], stored.encode())
        except ValueError:      # not a bcrypt hash: no match, never a 500
            return False

    def new_hash(password: str) -> str:
        return kit.bcrypt.hashpw(clean(password).encode()[:72], kit.bcrypt.gensalt()).decode()

    def named(account: dict) -> dict:
        """The row with its name where the kit's pages read it."""
        if NAME == "display_name" or not account:
            return account
        return {**account, "display_name": account.get(NAME)}

    def later(response, func: Callable, *args):
        """Run func(*args) after the response is sent (FL-083 (e): an answer
        that waits for the mail server tells an observer that the address
        exists). Never raises into the request; failures are logged."""
        def safe():
            try:
                func(*args)
            except Exception:  # noqa: BLE001
                kit.logger.exception("account mail could not be sent")
        task = BackgroundTask(safe)
        if response.background is None:
            response.background = task
        else:
            from starlette.background import BackgroundTasks
            both = BackgroundTasks()
            both.add_task(response.background)
            both.add_task(task)
            response.background = both
        return response

    def backup_hashes(row) -> list:
        raw = (row or {}).get("totp_backup_codes")
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return []

    def count_failure(row: dict) -> None:
        """A wrong code or a refused passkey counts towards the same lockout as
        a wrong password — otherwise the second factor could be guessed
        without limit.

        One atomic increment, then the lock for the count it produced. Read,
        add one and write back (until 5 October 2026) let failures sent in
        parallel all read the same count, so a batch counted as one."""
        run(f"UPDATE {T} SET failed_logins=COALESCE(failed_logins, 0)+1 WHERE id=%s",
            (row["id"],))
        fresh = q1(f"SELECT failed_logins FROM {T} WHERE id=%s", (row["id"],)) or {}
        _fails, until = lockout.register_failure((fresh.get("failed_logins") or 1) - 1)
        if until is not None:
            run(f"UPDATE {T} SET locked_until=%s WHERE id=%s", (until, row["id"]))

    def record_sign_in(row: dict) -> None:
        if kit.tables.clock is None:
            run(f"UPDATE {T} SET failed_logins=0, locked_until=NULL, last_login_at=NOW() "
                f"WHERE id=%s", (row["id"],))
        else:
            run(f"UPDATE {T} SET failed_logins=0, locked_until=NULL, last_login_at=%s "
                f"WHERE id=%s", (kit.tables.clock(), row["id"]))

    def landing(row: dict) -> str:
        return kit.must_change_url if row.get("must_change_password") else DASHBOARD_URL

    def passkeys_of(account_id) -> list:
        if not account_id:
            return []
        return qall(f"SELECT id, name, created_at, last_used_at FROM {PK} "
                    f"WHERE {OWNER}=%s ORDER BY created_at", (account_id,)) or []

    def account_page(request, account: dict, *, error=None, status_code=200):
        if error is None:
            error = ACCOUNT_ERRORS.get(request.query_params.get("err", ""))
        return page(request, "account.html", status_code=status_code, csrf_for=account,
                    account=named(account),
                    must_change=bool(account.get("must_change_password")),
                    totp_enabled=bool(account.get("totp_enabled")),
                    totp_required=twofactor.is_required(account.get("role")),
                    passkeys=passkeys_of(account.get("id")),
                    flash=ACCOUNT_MESSAGES.get(request.query_params.get("msg", "")),
                    error=error,
                    password_hint=pw_policy.PASSWORD_HINT)

    def two_factor_page(request, account, *, status_code=200, **context):
        values = {"enabled": False, "required": twofactor.is_required(account.get("role")),
                  "secret": None, "qr_svg": None, "codes": None, "error": None,
                  "replacing": False, "back_url": ACCOUNT_URL}
        values.update(context)
        return page(request, "two_factor.html", status_code=status_code, csrf_for=account,
                    **values)

    # ── signing in with a password, and signing out ──────────────────────────

    def sign_in_page(request, *, error=None, notice=None, status_code=200):
        return tool_page(request, LOGIN_TEMPLATE, status_code=status_code,
                         error=error, notice=notice)

    @router.get(LOGIN_URL)
    def sign_in_form(request: Request):
        # Signed in already: the form has nothing to offer, so go to the
        # dashboard (fleet entry-address rule, 3 October 2026). Looking the
        # session up needs the database, and this page must still render when
        # it is down: it is the page somebody reaches for when something is
        # wrong. Only this page treats a failed lookup as "signed out".
        lookup_failed = False
        try:
            signed_in = kit.current_account(request)
        except Exception:  # noqa: BLE001 — during an outage the form still renders
            kit.logger.exception("login page: session lookup failed; showing the form")
            signed_in, lookup_failed = None, True
        if signed_in:
            return RedirectResponse(DASHBOARD_URL, status_code=kit.signed_in_redirect_status)
        # A confirmed address change lands here, signed out on purpose (the
        # login itself has just changed). Both texts come from the fixed
        # tables above: the query string carries a key, and only the key is
        # read.
        error = ACCOUNT_ERRORS.get(request.query_params.get("err", ""))
        notice = ACCOUNT_MESSAGES.get(request.query_params.get("msg", ""))
        resp = sign_in_page(request, error=error, notice=notice)
        if (not lookup_failed and request.cookies.get(kit.session_cookie)
                and kit.drop_dead_session_cookie and kit.drop_dead_session_cookie(request)):
            resp.delete_cookie(kit.session_cookie)
        return resp

    @router.post(LOGIN_URL)
    def sign_in(request: Request, csrf_token: str = csrf_field(),
                email: str = Form(...), password: str = Form(...)):
        # (c) the budget first, then the token, then the account.
        if not sign_in_allowed(request):
            raise HTTPException(429, "Too many login attempts")
        if not kit.csrf_ok(request, csrf_token, None):
            raise bad_csrf()
        # (c) A deactivated account is not looked up at all, so it hears what
        # an unknown address hears and nothing is counted against it.
        row = q1(f"SELECT * FROM {T} WHERE email=%s AND is_active=1", (email.strip().lower(),))
        # (c) A locked account is refused before its password is checked, so
        # guessing during the lock learns nothing and does not extend it.
        if row and lockout.is_locked(row.get("locked_until")):
            kit.audit("login_locked", request=request, admin_id=row["id"],
                      admin_email=row["email"])
            return sign_in_page(request, error=lockout.LOCKED_MESSAGE, status_code=429)
        # bcrypt reads only the first 72 bytes and bcrypt >= 4.1 raises on
        # longer input, so every call site truncates (audit item G1). An
        # unknown or deactivated address is checked against a throwaway hash,
        # so its answer takes as long as a wrong password's.
        if not password_ok(password, row):
            if row:
                count_failure(row)                       # (a) the fleet's lockout
                kit.audit("login_failed", request=request, admin_id=row["id"],
                          admin_email=row["email"])
            return sign_in_page(request, error=SIGN_IN_REFUSED)
        # A1: the password was right, but no session is granted yet while a
        # code is owed: a pending cookie that no guarded page accepts. The
        # failure count is NOT cleared here, only by a right code: clearing it
        # on the password let someone holding the password re-enter it
        # between code guesses and never reach the lock (review, 5 October 2026).
        if row.get("totp_enabled"):
            resp = redirect(VERIFY_URL)
            kit.set_pending_cookie(resp, row["id"])
            return resp
        record_sign_in(row)
        kit.audit("login_success", request=request, admin_id=row["id"], admin_email=row["email"])
        resp = redirect(landing(row))
        kit.set_session_cookie(resp, row["id"])
        return resp

    @router.post(LOGOUT_URL)
    def sign_out(request: Request, csrf_token: str = csrf_field()):
        # (e) A session, and a token minted for it: otherwise any page on the
        # web could sign a person out.
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        resp = redirect(LOGIN_URL)
        resp.delete_cookie(kit.session_cookie)
        # The next person at this computer must not inherit a half-finished
        # sign-in or an unconfirmed authenticator secret (the enrolment cookie
        # is not bound to an account; review, 5 October 2026).
        resp.delete_cookie(kit.pending_cookie)
        resp.delete_cookie(kit.enrolment_cookie)
        return resp

    # ── the password-reset links ─────────────────────────────────────────────
    # Tokens are stored hashed; the raw token only ever appears in the mailed
    # link. A tool's own "send a reset link" (an administrator's button) mints
    # tokens of the same shape, which is why `reset_token_hash` is public.

    def reset_page(request, *, token="", error=None, success=False, message=None):
        return tool_page(request, RESET_TEMPLATE, token=token, error=error, success=success,
                         message=message)

    def issue_reset_token(account_id) -> str:
        raw = secrets.token_urlsafe(32)
        if kit.tables.clock is None:
            run(f"INSERT INTO {RT} ({RT_OWNER}, token_hash, expires_at) "
                f"VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL %s HOUR))",
                (account_id, reset_token_hash(raw), kit.reset_token_hours))
        else:
            run(f"INSERT INTO {RT} ({RT_OWNER}, token_hash, expires_at) VALUES (%s, %s, %s)",
                (account_id, reset_token_hash(raw),
                 kit.tables.clock() + timedelta(hours=kit.reset_token_hours)))
        return raw

    @router.get(RESET_URL)
    def password_reset_form(request: Request, token: str = ""):
        return reset_page(request, token=token)

    @router.post(RESET_URL)
    def password_reset(request: Request, csrf_token: str = csrf_field(),
                       email: str = Form(""), token: str = Form(""),
                       new_password: str = Form("")):
        limit, window = RESET_LIMIT                      # (d) each request can send a mail
        if not is_allowed(f"pwreset:{kit.client_ip(request)}", max_requests=limit,
                          window_seconds=window):
            raise HTTPException(429, "Too many requests")
        if not kit.csrf_ok(request, csrf_token, None):
            raise bad_csrf()
        if email and not token:
            # Step 1: send a link. The answer is the same whether or not the
            # address belongs to an account, and (d) a deactivated account
            # gets no link.
            address = email.strip().lower()
            row = q1(f"SELECT id FROM {T} WHERE email=%s AND is_active=1", (address,))
            resp = reset_page(request, success=True, message=RESET_SENT)
            if row:
                raw = issue_reset_token(row["id"])
                # (d) every request for an account is recorded, its mail sent
                # or not, as the administrator's button records it; (e) the
                # mail goes after the answer, which is the same either way.
                kit.audit("password_reset_requested", request=request, admin_email=address)
                later(resp, mail("send_password_reset"), address,
                      f"{kit.base_url()}{RESET_URL}?token={raw}")
            return resp
        if token and new_password:
            # Step 2: set the new password.
            # (d) A link mailed before the account was deactivated sets nothing.
            row = q1(f"SELECT r.{RT_OWNER} FROM {RT} r JOIN {T} a ON a.id = r.{RT_OWNER} "
                     f"WHERE r.token_hash IN (%s, %s) AND r.{UNSPENT} AND r.expires_at > NOW() "
                     f"AND a.is_active=1", reset_token_hashes(token))
            if not row:
                return reset_page(request, token=token, error=RESET_DEAD)
            ok, why = pw_policy.validate_password(new_password)
            if not ok:
                return reset_page(request, token=token, error=why)
            owner = row[RT_OWNER]
            pw_hash = new_hash(new_password)
            # The link is claimed by one conditional UPDATE whose row count
            # decides: two requests with the same link both passed the SELECT
            # above, and only one may set a password (review, 5 October 2026).
            claimed = _once._run(kit.tables.get_conn,
                                 f"UPDATE {RT} SET {SPEND} WHERE token_hash IN (%s, %s) "
                                 f"AND {UNSPENT} AND expires_at > NOW()",
                                 list(reset_token_hashes(token)))
            if claimed != 1:
                return reset_page(request, token=token, error=RESET_DEAD)
            # session_epoch+1: a reset ends every session opened before it (A2).
            # Every outstanding link for the account is spent, this one and any
            # other. (d) A lockout stays: it runs out on its own.
            kit.tables.transaction([
                (f"UPDATE {T} SET {PW}=%s, must_change_password=0, "
                 f"session_epoch=session_epoch+1 WHERE id=%s", (pw_hash, owner)),
                (f"UPDATE {RT} SET {SPEND} WHERE {RT_OWNER}=%s AND {UNSPENT}", (owner,)),
            ])
            kit.audit("password_reset_completed", request=request, admin_id=owner)
            return reset_page(request, success=True, message=RESET_DONE)
        raise HTTPException(400, "Invalid request")      # (d)

    # ── the code prompt after a right password ───────────────────────────────

    def code_prompt_locked(request, row):
        """(a) The lock holds at the code prompt too: a locked account's code is
        not checked, and a right one does not sign it in."""
        kit.audit("login_locked", request=request, admin_id=row["id"],
                  admin_email=row.get("email"), details={"second_factor": True})
        return page(request, "two_factor_verify.html", preauth=True, status_code=429,
                    error=lockout.LOCKED_MESSAGE)

    @router.get("/backoffice/verify")
    def two_factor_verify_page(request: Request):
        row = kit.pending_account(request)
        if not row:
            return redirect(LOGIN_URL)
        if lockout.is_locked(row.get("locked_until")):
            return code_prompt_locked(request, row)
        return page(request, "two_factor_verify.html", preauth=True, error=None)

    @router.post("/backoffice/verify")
    def two_factor_verify_submit(request: Request, code: str = Form(""),
                                 csrf_token: str = Form("")):
        if not kit.csrf_ok(request, csrf_token, None):
            return redirect(LOGIN_URL)
        row = kit.pending_account(request)
        if not row:
            return redirect(LOGIN_URL)
        if lockout.is_locked(row.get("locked_until")):
            return code_prompt_locked(request, row)
        # Guesses per ACCOUNT, so a school's shared address does not spend the
        # budget of the people signing in beside the guesser.
        limit, window = SIGN_IN_LIMIT
        if not is_allowed(f"verify:{row['id']}", max_requests=limit, window_seconds=window):
            raise HTTPException(429, "Too many attempts")
        ok, remaining = twofactor.check_code(row.get("totp_secret"), code,
                                             backup_hashes(row), kit.bcrypt)
        if not ok:
            count_failure(row)
            return page(request, "two_factor_verify.html", preauth=True,
                        status_code=RESHOWN, error="That code is not valid.")
        if remaining is not None:          # a recovery code was spent — persist it
            run(f"UPDATE {T} SET totp_backup_codes=%s WHERE id=%s",
                (json.dumps(remaining), row["id"]))
        record_sign_in(row)
        kit.audit("login_success", request=request, admin_id=row["id"],
                  admin_email=row.get("email"), details={"second_factor": True})
        resp = redirect(landing(row))
        kit.set_session_cookie(resp, row["id"])
        resp.delete_cookie(kit.pending_cookie)
        return resp

    # ── setting up, replacing and switching off the authenticator ────────────

    @router.get("/backoffice/two-factor")
    def two_factor_setup(request: Request, replace: int = 0):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        # `?replace=1` — a new phone. Without it an enrolled account could only
        # re-enrol by switching two-factor OFF first, which admins may not do.
        # Nothing is written until a code from the NEW secret proves the new app
        # has it, so the old one keeps working until the new one takes over.
        if account.get("totp_enabled") and not replace:
            return two_factor_page(request, account, enabled=True)
        # The secret is minted per visit and only stored once a code proves the
        # app has it, so a half-finished setup cannot lock the account out.
        secret = request.cookies.get(kit.enrolment_cookie) or twofactor.generate_secret()
        uri = twofactor.provisioning_uri(secret, account["email"], kit.tool_name)
        resp = two_factor_page(request, account, secret=secret, qr_svg=twofactor.qr_svg(uri),
                               replacing=bool(replace and account.get("totp_enabled")))
        kit.set_enrolment_cookie(resp, secret)
        return resp

    @router.post("/backoffice/two-factor")
    def two_factor_setup_submit(request: Request, action: str = Form("enable"),
                                code: str = Form(""), csrf_token: str = Form("")):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        required = twofactor.is_required(account.get("role"))
        if action == "disable":
            if required:      # admins may not switch it off
                return redirect(TWO_FACTOR_URL)
            run(f"UPDATE {T} SET totp_secret=NULL, totp_enabled=0, totp_backup_codes=NULL "
                f"WHERE id=%s", (account["id"],))
            # Taking the second factor off an account is how a stolen session
            # becomes lasting access.
            kit.audit("two_factor_disabled", request=request, admin_id=account["id"],
                      admin_email=account.get("email"), subject=str(account["id"]))
            return redirect(TWO_FACTOR_URL)
        if action == "regenerate":
            # Ten codes, spent one at a time. A CURRENT code is required, so the
            # request comes from the phone that holds the secret rather than
            # merely from an open session.
            if not (account.get("totp_enabled")
                    and twofactor.verify(account.get("totp_secret") or "", code)):
                return redirect(f"{ACCOUNT_URL}?err=bad_code")
            codes = twofactor.generate_backup_codes()
            run(f"UPDATE {T} SET totp_backup_codes=%s WHERE id=%s",
                (json.dumps(twofactor.hash_backup_codes(codes, kit.bcrypt)), account["id"]))
            kit.audit("two_factor_codes_regenerated", request=request, admin_id=account["id"],
                      admin_email=account.get("email"), subject=str(account["id"]))
            resp = two_factor_page(request, account, enabled=True, codes=codes)
            resp.background = two_factor_mail(account, "codes_regenerated")
            return resp
        replacing = bool(account.get("totp_enabled"))
        secret = request.cookies.get(kit.enrolment_cookie)
        if not secret or not twofactor.verify(secret, code):
            uri = twofactor.provisioning_uri(secret or "", account["email"], kit.tool_name)
            return two_factor_page(request, account, status_code=RESHOWN,
                                   secret=secret, qr_svg=twofactor.qr_svg(uri),
                                   replacing=replacing,
                                   error="That code did not match — check the app and try again.")
        codes = twofactor.generate_backup_codes()
        run(f"UPDATE {T} SET totp_secret=%s, totp_enabled=1, totp_backup_codes=%s WHERE id=%s",
            (secret, json.dumps(twofactor.hash_backup_codes(codes, kit.bcrypt)), account["id"]))
        # Never the secret or the codes — that it happened, not how to repeat it.
        kit.audit("two_factor_replaced" if replacing else "two_factor_enabled", request=request,
                  admin_id=account["id"], admin_email=account.get("email"),
                  subject=str(account["id"]))
        # Shown once, in clear, and never again — only hashes are stored.
        resp = two_factor_page(request, account, enabled=True, codes=codes)
        resp.delete_cookie(kit.enrolment_cookie)
        resp.background = two_factor_mail(account, "replaced" if replacing else "enabled")
        return resp

    # ── passkeys (FL-065) ────────────────────────────────────────────────────
    # The ceremonies and the challenge cookie are phronon_common.passkeys. A
    # passkey sign-in ends in exactly the session the password (+ code) path
    # ends in, without asking for a code: a passkey is both factors (owner's
    # decision, 2 October 2026).

    def pk_secure() -> dict:
        return passkeys.cookie_kwargs(secure=kit.secure_cookies())

    @router.post("/backoffice/passkeys/options")
    def passkey_register_options(request: Request, csrf_token: str = Form("")):
        account = kit.current_account(request)
        if not account:
            return json_error("Please sign in again.", 401)
        if not kit.csrf_ok(request, csrf_token, account):
            return json_error("Please reload the page and try again.")
        if account.get("must_change_password"):
            return json_error("Set a new password first.", 403)
        existing = qall(f"SELECT credential_id FROM {PK} WHERE {OWNER}=%s",
                        (account["id"],)) or []
        if len(existing) >= passkeys.MAX_PER_ACCOUNT:
            return json_error("This account already has the most passkeys it may hold. "
                              "Remove one first.")
        options, challenge = passkeys.registration_options(
            base_url=kit.passkey_base_url(), tool_name=kit.tool_name,
            user_handle=passkeys.user_handle_for(kit.secret_key, account["id"]),
            user_name=account["email"], existing=[bytes(e["credential_id"]) for e in existing])
        resp = Response(options, media_type="application/json")
        resp.set_cookie(value=passkeys.seal_challenge(kit.secret_key, challenge,
                                                      f"register:{account['id']}"),
                        **pk_secure())
        return resp

    @router.post("/backoffice/passkeys")
    def passkey_register(request: Request, csrf_token: str = Form(""),
                         credential: str = Form(""), name: str = Form("")):
        account = kit.current_account(request)
        if not account:
            return json_error("Please sign in again.", 401)
        if not kit.csrf_ok(request, csrf_token, account):
            return json_error("Please reload the page and try again.")
        if account.get("must_change_password"):
            return json_error("Set a new password first.", 403)
        challenge = passkeys.open_challenge(kit.secret_key,
                                            request.cookies.get(passkeys.CHALLENGE_COOKIE),
                                            f"register:{account['id']}")
        if not challenge:
            return json_error("That took too long. Please try again.")
        try:
            new = passkeys.verify_registration(credential_json=credential, challenge=challenge,
                                               base_url=kit.passkey_base_url())
        except passkeys.PasskeyError as e:
            return json_error(str(e))
        count = q1(f"SELECT COUNT(*) AS n FROM {PK} WHERE {OWNER}=%s", (account["id"],))
        if count and count["n"] >= passkeys.MAX_PER_ACCOUNT:
            return json_error("This account already has the most passkeys it may hold.")
        if q1(f"SELECT id FROM {PK} WHERE credential_id=%s", (new.credential_id,)):
            return json_error("This passkey is already registered.")
        label = passkeys.clean_name(name, f"Passkey {count['n'] + 1 if count else 1}")
        run(f"INSERT INTO {PK} ({OWNER}, credential_id, public_key, sign_count, name) "
            f"VALUES (%s, %s, %s, %s, %s)",
            (account["id"], new.credential_id, new.public_key, new.sign_count, label))
        kit.audit("passkey_added", request=request, admin_id=account["id"],
                  admin_email=account.get("email"), subject=str(account["id"]),
                  details={"name": label})
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(passkeys.CHALLENGE_COOKIE, path="/")
        resp.background = two_factor_mail(account, "passkey_added")
        return resp

    @router.post("/backoffice/passkeys/{pid}/delete")
    def passkey_delete(request: Request, pid: int, csrf_token: str = Form("")):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        gone = q1(f"SELECT id, name FROM {PK} WHERE id=%s AND {OWNER}=%s",
                  (pid, account["id"]))
        if not gone:   # someone else's, or already removed: say nothing about which
            return redirect(ACCOUNT_URL)
        run(f"DELETE FROM {PK} WHERE id=%s AND {OWNER}=%s", (pid, account["id"]))
        kit.audit("passkey_removed", request=request, admin_id=account["id"],
                  admin_email=account.get("email"), subject=str(account["id"]),
                  details={"name": gone["name"]})
        resp = redirect(f"{ACCOUNT_URL}?msg=passkey_removed")
        resp.background = two_factor_mail(account, "passkey_removed")
        return resp

    def sign_in_allowed(request) -> bool:
        """(c) One budget per address for the password form and the passkey."""
        limit, window = SIGN_IN_LIMIT
        return is_allowed(f"login:{kit.client_ip(request)}", max_requests=limit,
                          window_seconds=window)

    @router.post("/backoffice/login/passkey/options")
    def passkey_login_options(request: Request, csrf_token: str = Form("")):
        # The password form is throttled by nginx (an EXACT match on
        # /backoffice/login that does not cover these paths), so it is done here.
        if not sign_in_allowed(request):
            return json_error("Too many sign-in attempts. Wait a minute.", 429)
        if not kit.csrf_ok(request, csrf_token, None):
            return json_error("Please reload the page and try again.")
        options, challenge = passkeys.authentication_options(base_url=kit.passkey_base_url())
        resp = Response(options, media_type="application/json")
        resp.set_cookie(value=passkeys.seal_challenge(kit.secret_key, challenge, "login"),
                        **pk_secure())
        return resp

    @router.post("/backoffice/login/passkey")
    def passkey_login(request: Request, csrf_token: str = Form(""), credential: str = Form("")):
        if not sign_in_allowed(request):
            return json_error("Too many sign-in attempts. Wait a minute.", 429)
        if not kit.csrf_ok(request, csrf_token, None):
            return json_error("Please reload the page and try again.")
        sealed = passkeys.open_sealed_challenge(
            kit.secret_key, request.cookies.get(passkeys.CHALLENGE_COOKIE), "login")
        if not sealed:
            return json_error("That took too long. Please try again.")
        refused = "That passkey was not accepted. Sign in with your password instead."
        try:
            cred_id = passkeys.credential_id_of(credential)
        except passkeys.PasskeyError as e:
            return json_error(str(e))
        key = q1(f"SELECT * FROM {PK} WHERE credential_id=%s", (cred_id,))
        row = q1(f"SELECT * FROM {T} WHERE id=%s", (key[OWNER],)) if key else None
        if not key or not row or not row.get("is_active", True):
            return json_error(refused)
        if lockout.is_locked(row.get("locked_until")):
            kit.audit("login_locked", request=request, admin_id=row["id"],
                      admin_email=row["email"])
            return json_error(lockout.LOCKED_MESSAGE, 429)
        try:
            count = passkeys.verify_authentication(
                credential_json=credential, challenge=sealed.value,
                base_url=kit.passkey_base_url(),
                public_key=bytes(key["public_key"]), sign_count=key["sign_count"])
        except passkeys.PasskeyError:
            count_failure(row)
            kit.audit("login_failed", request=request, admin_id=row["id"],
                      admin_email=row["email"], details={"passkey": True})
            return json_error(refused)
        if not passkeys.record_sign_in(kit.tables.get_conn, key["id"], count, sealed.issued_at,
                                       table=PK):
            # This challenge was already spent: a replay, or the same request
            # sent twice. Refused, and not counted towards the lockout.
            kit.audit("login_failed", request=request, admin_id=row["id"],
                      admin_email=row["email"],
                      details={"passkey": True, "challenge_used": True})
            return json_error(refused)
        record_sign_in(row)
        kit.audit("login_success", request=request, admin_id=row["id"],
                  admin_email=row["email"], details={"passkey": True})
        resp = JSONResponse({"redirect": landing(row)})
        kit.set_session_cookie(resp, row["id"])
        resp.delete_cookie(passkeys.CHALLENGE_COOKIE, path="/")
        resp.delete_cookie(kit.pending_cookie)
        return resp

    # ── the Manage account page ──────────────────────────────────────────────
    # One page for the four things an account holder owns: their name, their
    # sign-in address, their password and their second factor. While a
    # temporary password is in force it shows the password form and nothing
    # else, and the name and address handlers refuse outright.

    @router.get("/backoffice/account")
    def account_get(request: Request):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        return account_page(request, account)

    @router.post("/backoffice/account/name")
    def account_name(request: Request, csrf_token: str = Form(""),
                     display_name: str = Form("")):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        if account.get("must_change_password"):
            return redirect(f"{ACCOUNT_URL}?err=password_needed")
        cleaned, error = account_mod.validate_name(display_name)
        if error:
            return account_page(request, account, error=error, status_code=RESHOWN)
        if cleaned != (account.get(NAME) or ""):
            run(f"UPDATE {T} SET {NAME}=%s WHERE id=%s", (cleaned, account["id"]))
            kit.audit("account_name_changed", request=request, admin_id=account["id"],
                      admin_email=account.get("email"), subject=str(account["id"]))
        return redirect(f"{ACCOUNT_URL}?msg=name_saved")

    @router.post("/backoffice/account/email")
    def account_email(request: Request, csrf_token: str = Form(""),
                      new_email: str = Form(""), current_password: str = Form("")):
        """Ask for an address change. Writes nothing — see phronon_common.account."""
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        if account.get("must_change_password"):
            return redirect(f"{ACCOUNT_URL}?err=password_needed")
        # An address change SENDS MAIL, twice, to addresses this request names.
        # The password below stops it being anonymous; this stops a signed-in
        # account using it as a mailer. Three an hour is far above a real change
        # of address, and far below anything worth doing with it.
        if not is_allowed(f"emailchange:{account['id']}", max_requests=3, window_seconds=3600):
            return redirect(f"{ACCOUNT_URL}?err=too_many")
        # The password, every time: a borrowed session would otherwise be enough
        # to point somebody else's account at your own mailbox and then reset the
        # password to match.
        if not password_ok(current_password, account):
            kit.audit("email_change_refused", request=request, admin_id=account["id"],
                      admin_email=account.get("email"), subject=str(account["id"]),
                      details={"reason": "wrong_password"})
            return redirect(f"{ACCOUNT_URL}?err=wrong_password")
        email, error = account_mod.validate_email(new_email, current=account.get("email"))
        if error:
            return account_page(request, account, error=error, status_code=RESHOWN)
        # The UNIQUE key would catch a duplicate at write time — two hours later,
        # in a route nobody is watching, after the person was told to check mail.
        if q1(f"SELECT id FROM {T} WHERE email=%s AND id!=%s", (email, account["id"])):
            return redirect(f"{ACCOUNT_URL}?err=email_taken")
        token = account_mod.make_email_change_token(
            email_signer, admin_id=account["id"], old_email=account["email"],
            new_email=email, session_epoch=account.get("session_epoch") or 0)
        confirm_url = f"{kit.base_url()}/backoffice/account/email/confirm?token={token}"
        kit.audit("email_change_requested", request=request, admin_id=account["id"],
                  admin_email=account.get("email"), subject=str(account["id"]),
                  details={"new_email": email})
        resp = redirect(f"{ACCOUNT_URL}?msg=email_sent")
        later(resp, mail("send_email_change_confirm"), email, confirm_url)
        # ...and the current address hears about it now, while the link is
        # still unused. If this was not them, that is when they can act.
        later(resp, mail("send_email_change_notice"), account["email"], email)
        return resp

    def read_email_change(token: str):
        """(payload, row, error) for a confirmation link, checked against the row."""
        payload = email_signer.loads(token)
        row = (q1(f"SELECT * FROM {T} WHERE id=%s", (payload["id"],))
               if isinstance(payload, dict) and payload.get("id") is not None else None)
        payload, error = account_mod.read_email_change_token(email_signer, token, row=row)
        return payload, row, error

    @router.get("/backoffice/account/email/confirm")
    def account_email_confirm_page(request: Request, token: str = ""):
        """Show what the link would do. READ-ONLY — opening it writes nothing.

        NO LOGIN IS REQUIRED: the link proves the new mailbox is reachable and is
        routinely opened on the phone that holds it. The token is the credential,
        re-checked against the live row every time. The change waits behind a
        button because mail scanners fetch every URL they see."""
        payload, _row, error = read_email_change(token)
        return page(request, "account_confirm_email.html", preauth=True,
                    status_code=RESHOWN if error else 200,
                    error=error, payload=payload, token="" if error else token)

    @router.post("/backoffice/account/email/confirm")
    def account_email_confirm(request: Request, csrf_token: str = Form(""),
                              token: str = Form("")):
        # A pre-sign-in form: whoever opens this link is not signed in.
        if not kit.csrf_ok(request, csrf_token, None):
            raise bad_csrf()
        payload, row, error = read_email_change(token)
        if error:
            return page(request, "account_confirm_email.html", status_code=RESHOWN,
                        error=error, payload=None, token="")
        # The epoch bump is not bookkeeping: the address IS the login, so every
        # session opened under the old one ends here, on every device.
        # One conditional UPDATE decides: the link names the OLD address, so a
        # second click (or a second tab) finds it changed and is refused like a
        # spent link instead of answering 500 (Polarity Profiler's guard).
        try:
            changed = _once._run(kit.tables.get_conn,
                                 f"UPDATE {T} SET email=%s, session_epoch=session_epoch+1 "
                                 f"WHERE id=%s AND email=%s", [payload["new"], row["id"], payload["old"]])
        except Exception:  # noqa: BLE001 — e.g. the address was taken meanwhile
            kit.logger.exception("e-mail change could not be applied")
            changed = 0
        if changed != 1:
            return page(request, "account_confirm_email.html", status_code=RESHOWN,
                        error="That link has expired or has already been used. Request the change again.",
                        payload=None, token="")
        kit.audit("email_changed", request=request, admin_id=row["id"],
                  admin_email=payload["new"], subject=str(row["id"]),
                  details={"from": payload["old"]})
        gone = redirect(f"{LOGIN_URL}?msg=email_changed")
        gone.delete_cookie(kit.session_cookie)
        return gone

    def form_field(name: str):
        """Form(...) where the tool declared this field required, else Form("")."""
        return Form(...) if name in kit.password_form_required else Form("")

    @router.post("/backoffice/account/password")
    def account_password(request: Request,
                         csrf_token: str = csrf_field(),
                         current_password: str = form_field("current_password"),
                         new_password: str = form_field("new_password"),
                         confirm_password: str = form_field("confirm_password")):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        if not password_ok(current_password, account):
            return account_page(request, account, error="Current password is incorrect.")
        ok, why = pw_policy.validate_password(new_password)
        if not ok:
            return account_page(request, account, error=why)
        if new_password != confirm_password:
            return account_page(request, account, error="New passwords do not match.")
        if password_ok(new_password, account):
            return account_page(request, account,
                                error="The new password must differ from the current one.")
        pw_hash = new_hash(new_password)
        # session_epoch+1: a password change must end every session that was
        # already open elsewhere — that is the point of changing it (A2).
        run(f"UPDATE {T} SET {PW}=%s, must_change_password=0, "
            f"session_epoch=session_epoch+1 WHERE id=%s", (pw_hash, account["id"]))
        kit.audit("password_changed", request=request, admin_id=account["id"],
                  admin_email=account.get("email"))
        # A fresh cookie (the bump above ended this session too), and straight
        # to the dashboard rather than a success note on this page.
        resp = redirect(DASHBOARD_URL)
        kit.set_session_cookie(resp, account["id"])
        return resp

    # ── an administrator resets another account's two-factor ─────────────────

    # The path spelled out (it is ADMIN_TWO_FACTOR_RESET_URL): the fleet's
    # account-page contract finds this handler by its decorator.
    @router.post("/backoffice/users/{user_id}/reset-two-factor")
    def reset_two_factor_by_admin(request: Request, user_id: int, csrf_token: str = Form("")):
        """Clear another account's second factor, so it can enrol again.

        The lost-phone case: recovery codes are the first line, but somebody
        who lost the phone AND the codes had nowhere to go but a database edit.
        It adds no power an administrator lacks (they can already send that
        account a password reset, i.e. become it). What it adds is a record and
        a mail, because "an admin reset my second factor" and "somebody took my
        account" look identical from the inside.
        """
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        # Any case (FL-083 (f)): four adopters spell the role ADMIN.
        if str(account.get("role") or "").lower() != "admin":
            return kit.not_an_admin(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        target = q1(f"SELECT * FROM {T} WHERE id=%s", (user_id,))
        if not target or not target.get("totp_enabled"):
            return redirect(USERS_URL)
        # The epoch bump ends the target's open sessions: if this is used to
        # recover a compromised account, leaving the intruder signed in undoes it.
        run(f"UPDATE {T} SET totp_secret=NULL, totp_enabled=0, totp_backup_codes=NULL, "
            f"session_epoch=session_epoch+1 WHERE id=%s", (user_id,))
        kit.audit("two_factor_reset_by_admin", request=request, admin_id=account["id"],
                  admin_email=account.get("email"), subject=str(user_id),
                  details={"email": target.get("email")})
        return later(kit.after_two_factor_reset(request, account),
                     mail("send_two_factor_reset_notice"), target["email"],
                     f"{kit.base_url()}{ACCOUNT_URL}")

    if kit.legacy_password_path:
        def legacy_password_page():
            """The old address. Kept as a redirect: bookmarks, and the fleet's probes."""
            return redirect(ACCOUNT_URL)

        router.add_api_route(kit.legacy_password_path, legacy_password_page, methods=["GET"])
        router.add_api_route(kit.legacy_password_path, account_password, methods=["POST"])

    # Every GET answers HEAD, as it did in the tools. Mail scanners and proxies
    # (SafeLinks, Zscaler) probe a link with HEAD first, and the e-mail-change
    # confirmation is a mailed link; a 405 there reads as a broken link. The
    # tools add HEAD in a loop over app.routes, which on FastAPI 0.139 never
    # reaches the routes of an included router, so the kit adds it here.
    for route in router.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods:
            route.methods.add("HEAD")
    return router


#: Every path the router answers, for a tool's gates and tests. The legacy
#: password path is added by the tool's own adapter when it has one.
PATHS = (
    LOGIN_URL,
    LOGOUT_URL,
    RESET_URL,
    "/backoffice/verify",
    TWO_FACTOR_URL,
    "/backoffice/passkeys/options",
    "/backoffice/passkeys",
    "/backoffice/passkeys/{pid}/delete",
    "/backoffice/login/passkey/options",
    "/backoffice/login/passkey",
    ACCOUNT_URL,
    "/backoffice/account/name",
    "/backoffice/account/email",
    "/backoffice/account/email/confirm",
    "/backoffice/account/password",
    ADMIN_TWO_FACTOR_RESET_URL,
)
#: The paths that answer GET (and HEAD) as well.
GET_PATHS = (LOGIN_URL, RESET_URL, "/backoffice/verify", TWO_FACTOR_URL, ACCOUNT_URL,
             "/backoffice/account/email/confirm")


def reset_token_hash(raw: str) -> str:
    """How a reset token is stored: the first 32 hex digits of its SHA-256.
    Both pilot tools, and their administrators' "send a reset link" buttons,
    store exactly this, so links already mailed keep working."""
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def reset_token_hashes(raw: str) -> tuple:
    """Both shapes a stored reset token can have: the kit's 32 digits, and
    the full SHA-256 that Layoff, Polarity Profiler and Controversy
    Generator stored before adopting the kit, so their links mailed before
    the switch still work for the two hours they live."""
    full = hashlib.sha256(raw.encode()).hexdigest()
    return full[:32], full


# ── the gate ─────────────────────────────────────────────────────────────────

def account_gate(kit: AccountKit):
    """The middleware that holds two kinds of signed-in account to the pages
    they may use. Install it where the tool's own gate was, so the middleware
    order does not change:

        app.middleware("http")(account_kit.account_gate(kit))

    A temporary password in force: everything under /backoffice except the
    must-change paths redirects to the password form (`must_change_url`).
    Without this, the redirect issued at sign-in is defeated by typing any
    other address.

    An administrator without an authenticator (A1: two-factor is required for
    admins, offered to educators): everything but `ENROLMENT_OPEN` redirects
    to the enrolment page, the account page included. Educators are never
    forced; they may enrol from the same page. An administrator who has both
    a temporary password and no authenticator changes the password first,
    then enrols.

    A failed lookup lets the request through (fail OPEN): a database hiccup
    must not lock the whole backoffice out, and every page checks the session
    again itself.
    """
    must_change_open = MUST_CHANGE_OPEN
    if kit.legacy_password_path:
        must_change_open += (kit.legacy_password_path,)
    if kit.must_change_allows_two_factor:
        must_change_open += (TWO_FACTOR_URL,)
    who = kit.gate_account or kit.current_account

    async def gate(request: Request, call_next):
        path = request.url.path
        if path.startswith(kit.gated_prefixes):
            try:
                row = who(request)
            except Exception:  # noqa: BLE001 — fail open, see above
                row = None
            if row and row.get("must_change_password"):
                if not _opens(path, must_change_open):
                    return RedirectResponse(kit.must_change_url, status_code=303)
            # Asked of every other path, the account page included: until
            # 4 October 2026 the account page's place on the must-change list
            # exempted it here too, and an administrator without an
            # authenticator could change their name and sign-in address
            # (MM-007, DB-007). The password form is that page's only use
            # during a temporary password, so that state is decided above.
            elif (row and twofactor.is_required(row.get("role")) and not row.get("totp_enabled")
                    and not _opens(path, ENROLMENT_OPEN)):
                return RedirectResponse(TWO_FACTOR_URL, status_code=303)
        return await call_next(request)

    return gate
