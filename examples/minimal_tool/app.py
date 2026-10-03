"""The smallest tool that stands on phronon_common: a worked example.

It imports NO other tool's code and copies no shared implementation. Every
line that touches the shared package is the wiring a new tool needs; every
decision about the tool's own pages, data and routes stays here. Read it with
NEW-TOOL.md; tests/test_minimal_tool.py runs it, so it cannot rot.

What it shows, in order:
  1. identity      the tool's entry in phronon_common.registry (and legal_conf)
  2. security      security headers + CSP nonce, trusted Host names, CSRF
  3. legal pages   the shared router: imprint, privacy, cookies, accessibility
  4. assets        content-hashed URLs for the tool's own static files
  5. one form      a page with a CSRF token and a rate-limited POST
  6. audit         the shared audit trail, bound to THIS tool's database

The tool key comes from MINIMAL_TOOL_KEY. A real tool hard-codes its own key
once it is registered; this example borrows a registered one only so the
legal pages and Host list have an entry to read.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from phronon_common import audit as fleet_audit
from phronon_common.assets import asset_url
from phronon_common.csrf import CSRFMiddleware, CSRFProtection, get_csrf_token
from phronon_common.hosts import trusted_hosts
from phronon_common.legal import build_legal_router
from phronon_common.rate_limit import is_allowed
from phronon_common.registry import TOOLS
from phronon_common.request_ip import client_ip
from phronon_common.security_headers import SecurityHeadersMiddleware

BASE_DIR = Path(__file__).resolve().parent

# 1. identity ─────────────────────────────────────────────────────────────────
TOOL_KEY = os.environ.get("MINIMAL_TOOL_KEY", "whiteout")
IDENTITY = TOOLS[TOOL_KEY]                     # KeyError until it is registered
SECRET_KEY = os.environ["APP_SECRET_KEY"]      # never a default: a missing key must stop the boot

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

# 2. security ─────────────────────────────────────────────────────────────────
# Starlette runs the LAST added middleware FIRST. Host check outermost, then
# CSRF, then the headers on whatever comes back.
csrf = CSRFProtection(SECRET_KEY)
app.add_middleware(SecurityHeadersMiddleware, enable_hsts=True,
                   csp="default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
                       "style-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
app.add_middleware(CSRFMiddleware, csrf_protection=csrf, session_cookie=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts(TOOL_KEY))

# 3. legal pages ──────────────────────────────────────────────────────────────
app.include_router(build_legal_router(TOOL_KEY))

# 4. assets ───────────────────────────────────────────────────────────────────
asset = asset_url(BASE_DIR)                    # in Jinja: templates.env.globals["asset"] = asset


# 6. audit ────────────────────────────────────────────────────────────────────
def get_db():
    """THIS tool's connection factory. The shared code never imports a tool's
    database module; it is handed this callable (audit, once, retention
    heartbeat all take it)."""
    raise RuntimeError("the example has no database; a real tool returns a connection")


audit_recorder = fleet_audit.AuditRecorder(get_db)


# 5. one form ─────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return JSONResponse({"ok": True, "tool": IDENTITY.key})


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    token = get_csrf_token(request, csrf)
    nonce = request.state.csp_nonce
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{IDENTITY.display_name}</title></head>
<body>
<h1>{IDENTITY.display_name}</h1>
<form method="post" action="/echo">
  <input type="hidden" name="csrf_token" value="{token}">
  <label>Word <input name="word" maxlength="40"></label>
  <button>Send</button>
</form>
<p><a href="/privacy">Privacy</a> · <a href="/impressum">Impressum</a></p>
<script nonce="{nonce}">document.documentElement.dataset.ready = "1";</script>
</body></html>""")


@app.post("/echo")
def echo(request: Request, word: str = Form("")):
    if not is_allowed(f"echo:{client_ip(request)}", max_requests=20, window_seconds=60):
        return JSONResponse({"error": "Too many requests. Wait a minute."}, status_code=429)
    return JSONResponse({"word": word[:40]})
