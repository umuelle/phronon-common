"""CSRF token generation and validation (shared; from the Polarity Profiler/Drawbridge version).

The session cookie name used to bind tokens is configurable so each tool can keep
its own cookie name while sharing this code.
"""

from __future__ import annotations

import time
import hmac
import hashlib
import secrets
import logging
from typing import TYPE_CHECKING, Callable, Iterable, Optional
from urllib.parse import parse_qs
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse, JSONResponse

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.responses import Response
    from starlette.types import ASGIApp, Message

logger = logging.getLogger(__name__)


class CSRFProtection:
    """Generate and validate CSRF tokens using HMAC-SHA256."""

    def __init__(self, secret_key: str | bytes, token_expiry: int = 3600):
        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")
        self.secret_key = secret_key
        self.token_expiry = token_expiry

    def generate_token(self, session_id: Optional[str] = None) -> str:
        random_part = secrets.token_urlsafe(32)
        timestamp = str(int(time.time()))
        data_to_sign = f"{random_part}:{timestamp}"
        if session_id:
            data_to_sign += f":{session_id}"
        signature = hmac.new(
            self.secret_key, data_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{random_part}:{timestamp}:{signature}"

    def validate_token(self, token: Optional[str], session_id: Optional[str] = None) -> bool:
        if not token:
            return False
        try:
            parts = token.split(":")
            if len(parts) != 3:
                return False
            random_part, timestamp_str, provided_sig = parts
            timestamp = int(timestamp_str)
            if int(time.time()) - timestamp > self.token_expiry:
                return False
            data_to_sign = f"{random_part}:{timestamp_str}"
            if session_id:
                data_to_sign += f":{session_id}"
            expected_sig = hmac.new(
                self.secret_key, data_to_sign.encode("utf-8"), hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(provided_sig, expected_sig)
        except (ValueError, IndexError):
            return False


class CSRFMiddleware(BaseHTTPMiddleware):
    """Validate CSRF tokens on state-changing requests.

    Exemptions come in two flavours, and the difference matters:

    ``exempt_paths``
        PREFIX matches (``path.startswith(entry)``). Good for whole subtrees
        such as ``/static/`` or ``/withdraw/``.

    ``exempt_exact``
        EXACT matches (``path == entry``). This is the only safe way to exempt
        a bare ``"/"`` — a tool whose participant flow POSTs to the site root.

    Putting ``"/"`` in ``exempt_paths`` prefixes every URL on the site and turns
    CSRF off everywhere, backoffice included. That is not hypothetical: it
    shipped in two tools and went unnoticed for months, because nothing fails
    visibly — every request simply sails through. The constructor now refuses
    it outright, so the mistake cannot be made again anywhere in the fleet.

    On failure the middleware RETURNS a response; it never raises. User
    middleware sits outside Starlette's ExceptionMiddleware, so an
    ``HTTPException`` raised here would bypass the app's 403 handler and
    surface as a 500. Content negotiation keeps AJAX callers getting JSON.
    """

    PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    #: Entries that would match every path on the site.
    _CATCH_ALL = ("", "/")

    def __init__(self, app: ASGIApp, csrf_protection: CSRFProtection,
                 session_cookie: Optional[str] = "backoffice",
                 exempt_paths: Optional[Iterable[str]] = None,
                 exempt_exact: Optional[Iterable[str]] = None,
                 session_id_of: Optional[Callable[[Request], Optional[str]]] = None):
        """
        Args:
            session_cookie: Cookie whose value tokens are bound to. Pass ``None``
                to disable session binding — correct for tools that refresh the
                cookie on every response (a rolling value would never match).
            exempt_paths: Path PREFIXES exempt from CSRF. Never ``"/"``.
            exempt_exact: Exact paths exempt from CSRF. Use this for ``"/"``.
            session_id_of: ``callable(request) -> str | None`` naming the
                session a token is bound to, for a tool whose session cookie
                rolls: it returns the cookie's stable part (the account and its
                session epoch, say), or ``None`` for a visitor. When given, it
                is used instead of ``session_cookie`` (1.93.0, TO DO FL-090 (b)).
        """
        super().__init__(app)
        self.csrf = csrf_protection
        self.session_cookie = session_cookie
        self.session_id_of = session_id_of
        self.EXEMPT_PATHS = ["/static/"] + list(exempt_paths or [])
        self.EXEMPT_EXACT = frozenset(exempt_exact or ())

        catch_all = [p for p in self.EXEMPT_PATHS if p in self._CATCH_ALL]
        if catch_all:
            raise ValueError(
                f"CSRFMiddleware: exempt_paths entry {catch_all!r} is a prefix of "
                f"every URL, which disables CSRF for the whole app. If the site "
                f"root really does accept a POST, pass exempt_exact={{'/'}} instead."
            )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method not in self.PROTECTED_METHODS:
            return await call_next(request)

        path = request.url.path
        if path in self.EXEMPT_EXACT:
            return await call_next(request)
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return await call_next(request)

        # Read the RAW body and put it back.
        #
        # BaseHTTPMiddleware hands the route handler the same receive stream this
        # middleware reads from, so consuming the body here (via request.form())
        # leaves nothing for the handler: every field arrives as None and FastAPI
        # answers 422 "Field required". It stayed invisible while a catch-all "/"
        # exemption meant the middleware returned before ever touching the body.
        # Re-injecting a fresh stream containing the cached bytes is what makes
        # the handler see the form again.
        csrf_token = None
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

            content_type = request.headers.get("content-type", "")
            if content_type.startswith("application/x-www-form-urlencoded"):
                try:
                    values = parse_qs(body.decode("utf-8", errors="replace")).get("csrf_token", [])
                    if values:
                        csrf_token = values[0]
                except ValueError:
                    pass  # an unparsable body carries no form token; the header may still
            # Deliberately not parsing multipart here: it would need an extra
            # dependency and a full parse of an upload just to find one field.
            # Multipart callers send the token as the X-CSRF-Token header.

            sent = False

            async def receive_with_cached_body() -> Message:
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            request._receive = receive_with_cached_body

        if not csrf_token:
            csrf_token = request.headers.get("X-CSRF-Token")

        session_id = _session_id(request, self.session_cookie, self.session_id_of)
        if not csrf_token or not self.csrf.validate_token(csrf_token, session_id):
            logger.warning(f"CSRF validation failed for {request.method} {path}")
            if "application/json" in request.headers.get("accept", ""):
                return JSONResponse(
                    {"success": False, "error": "CSRF validation failed",
                     "detail": "Please refresh the page and try again."},
                    status_code=403,
                )
            return HTMLResponse(
                content="<h1>403 Forbidden</h1><p>CSRF validation failed. Please go back and try again.</p>",
                status_code=403,
            )
        return await call_next(request)


def _session_id(request: Request, session_cookie: Optional[str],
                session_id_of: Optional[Callable[[Request], Optional[str]]]) -> Optional[str]:
    """What a token is bound to: ``session_id_of(request)`` when a tool gives
    one, else the ``session_cookie`` value, else nothing."""
    if session_id_of is not None:
        return session_id_of(request) or None
    return request.cookies.get(session_cookie) if session_cookie else None


def get_csrf_token(request: Request, csrf_protection: CSRFProtection,
                   session_cookie: Optional[str] = None,
                   session_id_of: Optional[Callable[[Request], Optional[str]]] = None) -> str:
    """Token for use in templates.

    Pass the same ``session_cookie`` (or ``session_id_of``) the middleware was
    given, or neither when the middleware runs unbound — the two must agree or
    every token fails validation.
    """
    return csrf_protection.generate_token(_session_id(request, session_cookie, session_id_of))
