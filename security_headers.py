"""Security headers middleware (shared; identical to the LSR/Drawbridge version).

Per-request CSP nonce: every response mints a nonce, exposed as
`request.state.csp_nonce` for templates to stamp on inline <script> blocks. If a
custom `csp` string contains the literal token `{nonce}`, it is replaced with
that request's nonce — this is how a tool moves to `script-src 'self'
'nonce-{nonce}'` and drops `'unsafe-inline'`. A `csp` without the token is
returned unchanged (backward compatible).
"""

import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    def __init__(self, app, enable_hsts: bool = False, frame_options: str = "SAMEORIGIN",
                 private_path_prefix="/backoffice", csp: str = None):
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.frame_options = frame_options
        # One prefix or several. It was a single string, which quietly assumed
        # that the only pages worth keeping out of a cache are the admin's —
        # untrue for any tool whose PARTICIPANT pages carry an e-mail address,
        # a personal ranking, or private round material (Whiteout, 9 August
        # 2026). Accepting a sequence lets a tool name every private area
        # instead of picking the most important one.
        #
        # str.startswith() already accepts a tuple, so the only work is
        # normalising — and a plain string must keep working, because eight
        # tools pass one.
        self.private_path_prefix = (
            (private_path_prefix,) if isinstance(private_path_prefix, str)
            else tuple(private_path_prefix)
        )
        self.csp = csp

    def _build_csp(self, nonce: str) -> str:
        if self.csp:
            return self.csp.replace("{nonce}", nonce)
        # CDN-free default: since 2026-06-11 all Phronon tools self-host their
        # JS/CSS/fonts in static/vendor (corporate proxies block CDN hosts).
        directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "font-src 'self'",
            "connect-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'self'",
            "base-uri 'self'",
            "object-src 'none'",
        ]
        return "; ".join(directives)

    async def dispatch(self, request: Request, call_next):
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)

        response.headers["Content-Security-Policy"] = self._build_csp(nonce)
        response.headers["X-Frame-Options"] = self.frame_options
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Tuple-aware: startswith() takes a tuple natively, so one call covers
        # every private area the tool declared.
        if request.url.path.startswith(self.private_path_prefix):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        if "server" in response.headers:
            del response.headers["server"]

        return response
