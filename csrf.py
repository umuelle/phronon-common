"""CSRF token generation and validation (shared; from the LSR/Drawbridge version).

The session cookie name used to bind tokens is configurable so each tool can keep
its own cookie name while sharing this code.
"""

import time
import hmac
import hashlib
import secrets
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import HTMLResponse

logger = logging.getLogger(__name__)


class CSRFProtection:
    """Generate and validate CSRF tokens using HMAC-SHA256."""

    def __init__(self, secret_key: bytes, token_expiry: int = 3600):
        if isinstance(secret_key, str):
            secret_key = secret_key.encode("utf-8")
        self.secret_key = secret_key
        self.token_expiry = token_expiry

    def generate_token(self, session_id: str = None) -> str:
        random_part = secrets.token_urlsafe(32)
        timestamp = str(int(time.time()))
        data_to_sign = f"{random_part}:{timestamp}"
        if session_id:
            data_to_sign += f":{session_id}"
        signature = hmac.new(
            self.secret_key, data_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        return f"{random_part}:{timestamp}:{signature}"

    def validate_token(self, token: str, session_id: str = None) -> bool:
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
    """Validate CSRF tokens on state-changing requests."""

    PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    def __init__(self, app, csrf_protection: CSRFProtection,
                 session_cookie: str = "backoffice", exempt_paths: list = None):
        super().__init__(app)
        self.csrf = csrf_protection
        self.session_cookie = session_cookie
        self.EXEMPT_PATHS = ["/static/"] + (exempt_paths or [])

    async def dispatch(self, request: Request, call_next):
        if request.method not in self.PROTECTED_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(exempt) for exempt in self.EXEMPT_PATHS):
            return await call_next(request)

        csrf_token = None
        if request.method == "POST":
            try:
                form = await request.form()
                csrf_token = form.get("csrf_token")
            except Exception:
                pass
        if not csrf_token:
            csrf_token = request.headers.get("X-CSRF-Token")

        session_id = request.cookies.get(self.session_cookie)
        if not csrf_token or not self.csrf.validate_token(csrf_token, session_id):
            logger.warning(f"CSRF validation failed for {request.method} {path}")
            return HTMLResponse(
                content="<h1>403 Forbidden</h1><p>CSRF validation failed. Please go back and try again.</p>",
                status_code=403,
            )
        return await call_next(request)
