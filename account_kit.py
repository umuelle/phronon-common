"""The account kit: a tool's signed-in account routes, written once (FL-083 pilot).

WHAT THIS IS
Every tool carried its own copy of the routes an account holder uses on
themselves: the code prompt after the password, setting up and replacing the
authenticator app, new recovery codes, passkeys (add, remove, sign in), and
the Manage account page (name, e-mail change with its mailed confirmation,
password change). The logic was the same everywhere; local names, table
columns, cookie names and a handful of policies were not. Two tools (Moral
Mirror and Drawbridge) mount this router instead, as a pilot; the other seven
keep their own code for now.

    from phronon_common import account_kit
    account_kit.install_templates(templates.env)
    app.include_router(account_kit.build_account_router(account_kit.AccountKit(...)))

The routes, form fields, cookies, redirects, messages, audit actions and mails
are the ones both tools already had, so nothing a user, a browser or a stored
credential sees changes. Password hashes, TOTP secrets, recovery codes and
passkeys stay in the tool's own tables, read and written exactly as before.

WHAT A TOOL SUPPLIES — the `AccountKit` adapter
Everything that is the tool's own: its tables (`AccountTables`) and database
functions, its session (who is signed in, how a session cookie is issued and
what "signed out" answers), its pages (`render` puts a kit template inside the
tool's own backoffice layout), its CSRF check, its audit recorder, its mail
module, its lockout policy. Nothing in here branches on a tool's name: where
the two pilot tools behave differently, the difference is a named field of the
adapter, and its docstring says whether it is a decision or an accident kept
so that adopting the kit changed nothing.

WHAT STAYS IN THE TOOL (for now)
The password sign-in itself (/backoffice/login, which issues the pending
cookie this module's code prompt reads), sign-out, the password-reset links,
the must-change / forced-enrolment middleware, and the administrator's
"reset this account's two-factor" button. They carry most of the remaining
per-tool differences (lockout policy, rate limits, messages, which accounts
count as active), which want an owner's decision before they move (TO DO
FL-083).

TEMPLATES
`account_templates/` ships in the package (pyproject package-data) and is
reached as `account_kit/<name>.html` once `install_templates` has added it to
the tool's Jinja environment. Each extends the tool's own
"backoffice/base.html", so the pages render inside the tool's layout and nav.
"""
from __future__ import annotations

import importlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import jinja2
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

from . import account as account_mod
from . import lockout
from . import passkeys
from . import passwords as pw_policy
from . import twofactor
from .rate_limit import is_allowed

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent / "account_templates"
#: The name the kit's templates are reached under in a tool's environment.
TEMPLATE_PREFIX = "account_kit"

LOGIN_URL = "/backoffice/login"
DASHBOARD_URL = "/backoffice/dashboard"
ACCOUNT_URL = "/backoffice/account"
TWO_FACTOR_URL = "/backoffice/two-factor"

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

    The four functions are the tool's own database helpers, so connections,
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
    accounts: str = "admins"
    passkeys: str = "passkeys"
    #: The passkey table's column naming the account. Moral Mirror's says
    #: `educator_id`, Drawbridge's `admin_id`: a historic naming, not a design.
    passkey_owner: str = "admin_id"
    #: How `last_login_at` is stamped on a completed sign-in: None writes the
    #: database's NOW() (Moral Mirror, whose pool sets no time zone); a function
    #: supplies the value instead (Drawbridge: Python's UTC clock). KEPT so the
    #: column means what it meant; both are "now", but they agree only where
    #: the MySQL session clock is UTC.
    last_login_at: Optional[Callable[[], Any]] = None

    def __post_init__(self):
        for name in (self.accounts, self.passkeys, self.passkey_owner):
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


@dataclass(frozen=True)
class AccountKit:
    """Everything the account routes need from the tool that mounts them."""

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
    #: raises: the JSON routes answer 401 rather than redirecting.
    current_account: Callable[[Request], Optional[dict]]
    #: request -> what a page answers when nobody is signed in. May raise
    #: (Drawbridge raises its 302); Moral Mirror returns a 303.
    signed_out: Callable[[Request], Response]
    #: request -> the account whose password was right and whose code is still
    #: owed (the tool's login sets that cookie), or None.
    pending_account: Callable[[Request], Optional[dict]]
    #: The pending-login cookie, deleted once the code is accepted.
    pending_cookie: str
    #: (response, account_id) -> issue a fresh session cookie.
    set_session_cookie: Callable[[Response, int], None]
    #: The session cookie, deleted when an address change ends every session.
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
    #: app-wide (Moral Mirror's dependency, 403 before any route) answers True.
    #: A False here is answered the way Drawbridge answered it: 400 on a page,
    #: a JSON error on the passkey calls, the sign-in page from the code prompt.
    csrf_ok: Callable[[Request, str, Optional[dict]], bool]

    # ── its policy ───────────────────────────────────────────────────────────
    #: The tool's phronon_common.audit.AuditRecorder.
    audit: Callable[..., Any]
    #: The bcrypt module (passed in: this package declares no bcrypt).
    bcrypt: Any
    #: failed_logins_before -> (failed_logins, locked_until_or_None). A wrong
    #: code or a refused passkey counts like a wrong password, so this must be
    #: the rule the tool's own password sign-in applies: one lockout per tool.
    #: Drawbridge passes phronon_common.lockout.register_failure (one minute,
    #: doubling, the fleet policy since 24 July 2026). Moral Mirror locks for a
    #: fixed 15 minutes after five, in its login too: ACCIDENTAL (it never
    #: adopted the shared policy); kept, and to be changed in both places at once.
    register_failure: Callable[[int], tuple]
    #: request -> the address the passkey sign-in is rate-limited by.
    client_ip: Callable[[Request], str]
    #: (requests, seconds) for the passkey sign-in, which nginx's exact-match
    #: limit on /backoffice/login does not cover. Moral Mirror 10/60, keyed by
    #: the proxy-aware address; Drawbridge 5/60, the bucket its password form
    #: shares.
    login_rate_limit: tuple = (10, 60)
    #: Where a completed sign-in goes while a temporary password is in force.
    #: Drawbridge still says /backoffice/change-password, which redirects to
    #: the account page; Moral Mirror goes there directly.
    must_change_url: str = ACCOUNT_URL
    #: The tool's mail module, imported by name at send time (so a test that
    #: replaces one of its functions is honoured): it provides
    #: send_two_factor_confirmation, send_email_change_confirm and
    #: send_email_change_notice.
    mail_module: str = "services.email"
    #: Where "could not send" is logged — the tool's own logger, so the line
    #: lands where it always did.
    logger: logging.Logger = field(default=logger)
    #: The status of a page re-shown with a validation error (a wrong code, an
    #: invalid name or address, a dead confirmation link). Moral Mirror 200,
    #: Drawbridge 400. ACCIDENTAL; kept.
    error_status: int = 200
    #: Refuse a password change whose confirmation differs, or whose new
    #: password is the current one. Drawbridge does; Moral Mirror's form has
    #: the confirmation field but its server never read it. ACCIDENTAL (a gap
    #: in Moral Mirror); kept until the owner says otherwise.
    password_change_checks_confirmation: bool = True
    #: Password-change fields a request must carry or be refused with FastAPI's
    #: 422. Moral Mirror declared current/new password required, Drawbridge the
    #: CSRF token. Only a hand-made request can tell; kept so it cannot.
    password_form_required: tuple = ()
    #: An older address the password form also answers at, and whose GET
    #: redirects to the account page (Drawbridge: /backoffice/change-password,
    #: kept for bookmarks and the fleet's probes).
    legacy_password_path: Optional[str] = None
    layout: AccountPageLayout = field(default_factory=AccountPageLayout)


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
        without limit."""
        fails, until = kit.register_failure(row.get("failed_logins") or 0)
        run(f"UPDATE {T} SET failed_logins=%s, locked_until=%s WHERE id=%s",
            (fails, until, row["id"]))

    def record_sign_in(row: dict) -> None:
        if kit.tables.last_login_at is None:
            run(f"UPDATE {T} SET failed_logins=0, locked_until=NULL, last_login_at=NOW() "
                f"WHERE id=%s", (row["id"],))
        else:
            run(f"UPDATE {T} SET failed_logins=0, locked_until=NULL, last_login_at=%s "
                f"WHERE id=%s", (kit.tables.last_login_at(), row["id"]))

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
                    account=account,
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

    # ── the code prompt after a right password ───────────────────────────────

    @router.get("/backoffice/verify")
    def two_factor_verify_page(request: Request):
        if not kit.pending_account(request):
            return redirect(LOGIN_URL)
        return page(request, "two_factor_verify.html", preauth=True, error=None)

    @router.post("/backoffice/verify")
    def two_factor_verify_submit(request: Request, code: str = Form(""),
                                 csrf_token: str = Form("")):
        if not kit.csrf_ok(request, csrf_token, None):
            return redirect(LOGIN_URL)
        row = kit.pending_account(request)
        if not row:
            return redirect(LOGIN_URL)
        ok, remaining = twofactor.check_code(row.get("totp_secret"), code,
                                             backup_hashes(row), kit.bcrypt)
        if not ok:
            count_failure(row)
            return page(request, "two_factor_verify.html", preauth=True,
                        status_code=kit.error_status, error="That code is not valid.")
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
            return two_factor_page(request, account, status_code=kit.error_status,
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
        limit, window = kit.login_rate_limit
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
            return account_page(request, account, error=error, status_code=kit.error_status)
        if cleaned != (account.get("display_name") or ""):
            run(f"UPDATE {T} SET display_name=%s WHERE id=%s", (cleaned, account["id"]))
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
        if not kit.bcrypt.checkpw(current_password.encode()[:72],
                                  account["password_hash"].encode()):
            kit.audit("email_change_refused", request=request, admin_id=account["id"],
                      admin_email=account.get("email"), subject=str(account["id"]),
                      details={"reason": "wrong_password"})
            return redirect(f"{ACCOUNT_URL}?err=wrong_password")
        email, error = account_mod.validate_email(new_email, current=account.get("email"))
        if error:
            return account_page(request, account, error=error, status_code=kit.error_status)
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
        try:
            mail("send_email_change_confirm")(email, confirm_url)
            # ...and the current address hears about it now, while the link is
            # still unused. If this was not them, that is when they can act.
            mail("send_email_change_notice")(account["email"], email)
        except Exception:  # noqa: BLE001 — a mail outage must not eat the request
            kit.logger.exception("e-mail change mails could not be sent")
        return redirect(f"{ACCOUNT_URL}?msg=email_sent")

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
                    status_code=kit.error_status if error else 200,
                    error=error, payload=payload, token="" if error else token)

    @router.post("/backoffice/account/email/confirm")
    def account_email_confirm(request: Request, csrf_token: str = Form(""),
                              token: str = Form("")):
        # A pre-sign-in form: whoever opens this link is not signed in.
        if not kit.csrf_ok(request, csrf_token, None):
            raise bad_csrf()
        payload, row, error = read_email_change(token)
        if error:
            return page(request, "account_confirm_email.html", status_code=kit.error_status,
                        error=error, payload=None, token="")
        # The epoch bump is not bookkeeping: the address IS the login, so every
        # session opened under the old one ends here, on every device.
        run(f"UPDATE {T} SET email=%s, session_epoch=session_epoch+1 WHERE id=%s",
            (payload["new"], row["id"]))
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
                         csrf_token: str = form_field("csrf_token"),
                         current_password: str = form_field("current_password"),
                         new_password: str = form_field("new_password"),
                         confirm_password: str = form_field("confirm_password")):
        account = kit.current_account(request)
        if not account:
            return kit.signed_out(request)
        if not kit.csrf_ok(request, csrf_token, account):
            raise bad_csrf()
        if not kit.bcrypt.checkpw(current_password.encode()[:72],
                                  account["password_hash"].encode()):
            return account_page(request, account, error="Current password is incorrect.")
        ok, why = pw_policy.validate_password(new_password)
        if not ok:
            return account_page(request, account, error=why)
        if kit.password_change_checks_confirmation:
            if new_password != confirm_password:
                return account_page(request, account, error="New passwords do not match.")
            if kit.bcrypt.checkpw(new_password.encode()[:72], account["password_hash"].encode()):
                return account_page(request, account,
                                    error="The new password must differ from the current one.")
        pw_hash = kit.bcrypt.hashpw(new_password.encode()[:72], kit.bcrypt.gensalt()).decode()
        # session_epoch+1: a password change must end every session that was
        # already open elsewhere — that is the point of changing it (A2).
        run(f"UPDATE {T} SET password_hash=%s, must_change_password=0, "
            f"session_epoch=session_epoch+1 WHERE id=%s", (pw_hash, account["id"]))
        kit.audit("password_changed", request=request, admin_id=account["id"],
                  admin_email=account.get("email"))
        # A fresh cookie (the bump above ended this session too), and straight
        # to the dashboard rather than a success note on this page.
        resp = redirect(DASHBOARD_URL)
        kit.set_session_cookie(resp, account["id"])
        return resp

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
)
