"""Security headers middleware (shared; identical to the LSR/Drawbridge version)."""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    def __init__(self, app, enable_hsts: bool = False, frame_options: str = "SAMEORIGIN",
                 private_path_prefix: str = "/backoffice", csp: str = None):
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.frame_options = frame_options
        self.private_path_prefix = private_path_prefix
        self.csp = csp

    def _build_csp(self) -> str:
        if self.csp:
            return self.csp
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
        response = await call_next(request)

        response.headers["Content-Security-Policy"] = self._build_csp()
        response.headers["X-Frame-Options"] = self.frame_options
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        if request.url.path.startswith(self.private_path_prefix):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        if "server" in response.headers:
            del response.headers["server"]

        return response
