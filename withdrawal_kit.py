"""A participant's self-service withdrawal, one flow for the fleet (FL-089 follow-up).

Seven tools let a participant delete what they gave: `/withdraw` with the
deletion link (the token, stored hashed: participant.py), and where the tool
holds an address, `/withdrawal-link` to have a fresh link mailed (recovery by
rotation). Each tool wrote both by hand. By 6 October 2026 the copies
disagreed on almost everything a person or a log can see: which check came
first, which confirmation words counted, how a refusal looked, whether the
deletion was one transaction, and they shared two defects: a link mail that
failed had already killed the old link, and the answer to "mail me my link"
came back slower when the address matched, telling an observer what the page
was careful not to say.

The owner chose ONE fleet behaviour, the strictest of the seven:

  * GET /withdraw never writes. With a token it shows what would go; without
    one it asks for the link (`ask`); an unknown token is `not_found`.
  * POST /withdraw: the typed word first, and a wrong word deletes nothing
    (every locale's word counts: participant.WITHDRAW_CONFIRM_WORDS); then the
    lookup; then the tool's `delete`, which is ONE transaction.
  * 10 requests per 5 minutes per client address, POSTs and GETs carrying a
    token, answered with the tool's page and 429.
  * POST /withdrawal-link answers at once with the same page whatever the
    address; the mail goes out after the answer, and each matching row's new
    token is stored only once its mail was sent, so a failed send leaves the
    old link working. 5 requests per 15 minutes per client address.
  * One log line, the kind of row only: never an id, a session or an address.

What stays the tool's is data: how a token finds its row and what a row is
called (`lookup`, `kind`, `describe`), what is deleted (`delete`), which
browser cookie names the participant (`forget_browser`), how a recovery
request finds rows and mails a link (`link_rows`, `link_url`, `send_link`,
`store_token`), and the pages: each tool keeps its own templates, which
server-ops/closing_audit.py compares with its notice, and renders them its own
way (`render`). README §11 "participant mechanism" holds the rules.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from starlette.background import BackgroundTask

from . import participant as _participant

logger = logging.getLogger(__name__)

#: Requests, seconds: the deletion route (participant.WITHDRAW_RATE_LIMIT).
WITHDRAW_LIMIT = _participant.WITHDRAW_RATE_LIMIT
#: Requests, seconds: "mail me my link".
LINK_LIMIT = (5, 900)
#: At most this many rows get a fresh link per request (one person, one code).
LINK_ROWS_MAX = 5

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PAGES = {
    "withdraw": "withdraw.html",
    "withdraw_done": "withdraw_done.html",
    "withdrawal_link": "withdrawal_link.html",
    "withdrawal_link_sent": "withdrawal_link_sent.html",
}


@dataclass(frozen=True, kw_only=True)
class WithdrawalKit:
    """Everything the two routes need from the tool that mounts them."""

    # ── finding and deleting ────────────────────────────────────────────────
    #: token hash -> the row the link names, or None.
    lookup: Callable[[str], Optional[dict]]
    #: row -> what kind of record it is ("submission", "research", ...): the
    #: page's wording and the log line. The only thing ever logged.
    kind: Callable[[dict], str]
    #: row -> how many rows went, in ONE transaction; 0 when the row was
    #: already gone (a double post). Re-read the row under a lock inside.
    delete: Callable[[dict], int]
    #: (request, response, row) -> clear the participant cookie on `response`
    #: when it names this row's participant. None: the tool sets none.
    forget_browser: Optional[Callable[[Any, Any, dict], None]] = None
    #: row -> extra page context for it (the session's title, ...).
    describe: Callable[[dict], dict] = lambda row: {}

    # ── recovery by rotation (tools that hold an address) ───────────────────
    #: (CODE, email) -> the rows to mail a fresh link for. None: the tool
    #: holds no address and serves no /withdrawal-link.
    link_rows: Optional[Callable[[str, str], list]] = None
    #: (row, new token hash) -> store it. Called only after the mail went out.
    store_token: Optional[Callable[[dict, str], None]] = None
    #: (raw token, lang) -> the absolute link the mail carries.
    link_url: Optional[Callable[[str, str], str]] = None
    #: (row, address, url, lang) -> True when the mail was handed to the mail
    #: server. The tool's own mail (subject, wording, deadline, language).
    send_link: Optional[Callable[[dict, str, str, str], bool]] = None

    # ── pages ───────────────────────────────────────────────────────────────
    #: (request, template, context, lang, status_code) -> the response, rendered
    #: as the tool renders its participant pages (with its CSRF field).
    render: Callable[..., Any]
    #: lang -> the word the page asks for ("DELETE", "LÖSCHEN", ...). Any word
    #: in participant.WITHDRAW_CONFIRM_WORDS is accepted whatever is shown.
    confirm_word: Callable[[str], str] = lambda lang: "DELETE"
    pages: dict = field(default_factory=lambda: dict(PAGES))
    #: lang -> the URL prefix ('' for the canonical language): routing.lang_prefix.
    prefix: Callable[[str], str] = lambda lang: ""

    # ── policy ──────────────────────────────────────────────────────────────
    #: (request, submitted token) -> may this POST proceed? A tool whose CSRF
    #: check already runs before any route (middleware, app dependency)
    #: answers True; its own check has refused a bad token by then.
    csrf_ok: Callable[[Any, str], bool] = lambda request, token: True
    #: request -> the address the rate limits are keyed on.
    client_ip: Optional[Callable[[Any], str]] = None
    #: The tool's logger, so the line lands where its other lines do.
    logger: logging.Logger = field(default=logger)

    def __post_init__(self):
        recovery = (self.link_rows, self.store_token, self.link_url, self.send_link)
        if any(recovery) and not all(recovery):
            raise ValueError("withdrawal kit: link_rows, store_token, link_url and send_link "
                             "go together (recovery by rotation needs all four)")


def _ip(kit: WithdrawalKit, request) -> str:
    from .request_ip import client_ip
    return (kit.client_ip or client_ip)(request)


def _allowed(kit: WithdrawalKit, request, name: str, limit) -> bool:
    from .rate_limit import is_allowed
    return is_allowed(f"{name}:{_ip(kit, request)}", max_requests=limit[0], window_seconds=limit[1])


def _context(kit: WithdrawalKit, lang: str, **extra) -> dict:
    p = kit.prefix(lang)
    return {"lang": lang, "confirm_word": kit.confirm_word(lang),
            "withdraw_url": f"{p}/withdraw",
            "withdrawal_link_url": f"{p}/withdrawal-link" if kit.link_rows else None,
            **extra}


def _withdraw_page(kit, request, lang, state, *, token="", row=None, error=None, status=200):
    ctx = _context(kit, lang, state=state, token=token, error=error,
                   kind=kit.kind(row) if row else None, **(kit.describe(row) if row else {}))
    return kit.render(request, kit.pages["withdraw"], ctx, lang, status)


def token_from(value: str) -> str:
    """The token itself, also out of a pasted link (`.../withdraw?token=...`):
    the ask page invites pasting the link from the mail."""
    value = (value or "").strip()
    if "token=" in value:
        from urllib.parse import parse_qs, urlsplit
        query = urlsplit(value).query or value.split("?", 1)[-1]
        found = parse_qs(query).get("token")
        if found:
            return found[0].strip()
    return value


def _find(kit: WithdrawalKit, token: str) -> Optional[dict]:
    if not _participant.plausible_token(token):
        return None
    return kit.lookup(_participant.hash_token(token))


def build_withdrawal_router(kit: WithdrawalKit):
    """The routes: GET/POST /withdraw, and GET/POST /withdrawal-link when the
    tool holds an address. Each takes `lang` as a query parameter, so the
    tool's language twins (routing.add_language_twins) answer with them."""
    router = APIRouter()

    @router.get("/withdraw", response_class=HTMLResponse)
    def withdraw_page(request: Request, token: str = "", lang: str = "en"):
        token = token_from(token)
        if not token:
            return _withdraw_page(kit, request, lang, "ask")
        if not _allowed(kit, request, "withdraw", WITHDRAW_LIMIT):
            return _withdraw_page(kit, request, lang, "rate_limited", status=429)
        row = _find(kit, token)
        if row is None:
            return _withdraw_page(kit, request, lang, "not_found", token=token)
        return _withdraw_page(kit, request, lang, "confirm", token=token, row=row)

    @router.post("/withdraw", response_class=HTMLResponse)
    async def withdraw_submit(request: Request, lang: str = "en"):
        form = await request.form()
        token = token_from(form.get("token") or "")
        if not kit.csrf_ok(request, form.get("csrf_token") or ""):
            return _withdraw_page(kit, request, lang, "csrf", token=token, status=400)
        if not _allowed(kit, request, "withdraw", WITHDRAW_LIMIT):
            return _withdraw_page(kit, request, lang, "rate_limited", status=429)
        if not _participant.confirm_word_ok(form.get("confirm")):
            row = _find(kit, token)
            if row is None:
                return _withdraw_page(kit, request, lang, "not_found", token=token)
            return _withdraw_page(kit, request, lang, "confirm", token=token, row=row, error="confirm")
        row = _find(kit, token)
        if row is None:
            return _withdraw_page(kit, request, lang, "not_found", token=token)
        what = kit.kind(row)
        removed = kit.delete(row)
        kit.logger.info("participant withdrawal: %s %s", what, "deleted" if removed else "already gone")
        ctx = _context(kit, lang, kind=what, removed=bool(removed), **kit.describe(row))
        response = kit.render(request, kit.pages["withdraw_done"], ctx, lang, 200)
        if kit.forget_browser is not None:
            kit.forget_browser(request, response, row)
        return response

    if kit.link_rows is None:
        return router

    def link_form(request, lang, *, code="", email="", error=None, status=200):
        ctx = _context(kit, lang, prefill_code=code, prefill_email=email, error=error)
        return kit.render(request, kit.pages["withdrawal_link"], ctx, lang, status)

    @router.get("/withdrawal-link", response_class=HTMLResponse)
    def withdrawal_link_page(request: Request, code: str = "", lang: str = "en"):
        return link_form(request, lang, code=code.strip().upper())

    @router.post("/withdrawal-link", response_class=HTMLResponse)
    async def withdrawal_link_submit(request: Request, lang: str = "en"):
        form = await request.form()
        code = (form.get("code") or "").strip().upper()
        email = (form.get("email") or "").strip().lower()
        if not kit.csrf_ok(request, form.get("csrf_token") or ""):
            return link_form(request, lang, code=code, email=email, error="csrf", status=400)
        if not _allowed(kit, request, "withdrawal-link", LINK_LIMIT):
            return link_form(request, lang, code=code, email=email, error="rate_limited", status=429)
        if not code or not _EMAIL.match(email):
            return link_form(request, lang, code=code, email=email, error="fields")
        response = kit.render(request, kit.pages["withdrawal_link_sent"], _context(kit, lang), lang, 200)
        response.background = BackgroundTask(send_fresh_links, kit, code, email, lang)
        return response

    return router


def send_fresh_links(kit: WithdrawalKit, code: str, email: str, lang: str) -> int:
    """Mail a fresh link for each row `code` and `email` name; store each new
    token only once its mail went out. Runs after the answer. Returns the
    number of links sent."""
    from .emails import recipient_domain

    sent = 0
    try:
        rows = list(kit.link_rows(code, email))[:LINK_ROWS_MAX]
    except Exception:  # noqa: BLE001 - the answer is already out; say why here
        kit.logger.exception("withdrawal link: looking up the rows failed")
        return 0
    for row in rows:
        raw, digest = _participant.new_token()
        try:
            ok = kit.send_link(row, email, kit.link_url(raw, lang), lang)
        except Exception:  # noqa: BLE001
            ok = False
            kit.logger.exception("withdrawal link to %s failed", recipient_domain(email))
        if not ok:
            kit.logger.warning("withdrawal link to %s not sent; the old link still works",
                               recipient_domain(email))
            continue
        try:
            kit.store_token(row, digest)
            sent += 1
        except Exception:  # noqa: BLE001
            kit.logger.exception("withdrawal link to %s sent but not stored; the old link "
                                 "still works, the mailed one does not", recipient_domain(email))
    return sent
