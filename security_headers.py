"""Security headers middleware (shared; identical to the LSR/Drawbridge version).

Per-request CSP nonce: every response mints a nonce, exposed as
`request.state.csp_nonce` for templates to stamp on inline <script> blocks. If a
custom `csp` string contains the literal token `{nonce}`, it is replaced with
that request's nonce — this is how a tool moves to `script-src 'self'
'nonce-{nonce}'` and drops `'unsafe-inline'`. A `csp` without the token is
returned unchanged (backward compatible).
"""

import re
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


# ── What may be cached ───────────────────────────────────────────────────────
# The fleet's public surface, and it is short: a landing page, the way in, the
# legal set, the machine-facing files, and static assets. Everything else a
# Phronon tool serves is somebody's answers.
#
# WHY THIS IS AN ALLOWLIST. It began as the opposite — name the private area,
# default everything else cacheable — and that default was wrong twice over. It
# assumed the only pages worth protecting are the administrator's, which is
# untrue of every tool here: participant pages carry e-mail addresses, personal
# rankings, and in Whiteout's third round private material dealt to one person.
# And a named-private list rots: Layoff's said `/admin` while its backoffice had
# moved to `/backoffice`, so for two days the pages listing participants'
# addresses served no cache header at all, and nothing noticed because the list
# was still "correct" about a path that still resolved.
#
# Inverted, a new route is private until somebody deliberately makes it public.
# That is the right default for software whose whole job is holding answers.
PUBLIC_EXACT = frozenset({
    "/", "/join", "/robots.txt", "/llms.txt", "/favicon.ico", "/health",
})
PUBLIC_PREFIXES = (
    "/static/", "/legal", "/privacy", "/cookies", "/terms", "/impressum",
    "/legal-notice", "/imprint", "/accessibility", "/about",
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    def __init__(self, app, enable_hsts: bool = False, frame_options: str = "SAMEORIGIN",
                 private_path_prefix="/backoffice", csp: str = None,
                 public_paths=None, locales=()):
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
        # Inverted mode: when `public_paths` is given, EVERYTHING is no-store
        # except the allowlist. Pass `DEFAULT_PUBLIC` for the fleet's set.
        self.public_exact, self.public_prefixes = (None, None)
        if public_paths is not None:
            exact, prefixes = public_paths
            self.public_exact = frozenset(exact)
            self.public_prefixes = tuple(prefixes)
        # Locales are named, never guessed. Stripping any two-letter first
        # segment would read Whiteout's `/go` as locale `go` and leave the
        # phase-gate page public — the tool has real two-letter routes.
        self.locale_re = (
            re.compile(r"^/(?:%s)(?=/|$)" % "|".join(re.escape(l) for l in locales))
            if locales else None
        )
        self.csp = csp

    def _is_private(self, path: str) -> bool:
        if self.public_exact is None:
            return path.startswith(self.private_path_prefix)
        # /de/privacy is the same page as /privacy for this purpose.
        if self.locale_re:
            path = self.locale_re.sub("", path) or "/"
        if path in self.public_exact:
            return False
        return not path.startswith(self.public_prefixes)

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
        # A credential in the current URL must not reappear as the same-origin
        # Referer of a CSS/JS request. `strict-origin-when-cross-origin` keeps the
        # full path and query on same-origin requests, including password-reset,
        # withdrawal, report and recruitment credentials.
        query_names = {name.lower() for name in request.query_params.keys()}
        credential_query = bool(
            query_names & {"token", "prolific_pid", "study_id", "session_id"}
        )
        credential_path = any(marker in request.url.path.lower() for marker in (
            "/password-reset", "/reset-password", "/reset_password",
            "/withdraw", "/resume", "/report/", "/results/", "/postpone",
        ))
        response.headers["Referrer-Policy"] = (
            "no-referrer" if credential_query or credential_path
            else "strict-origin-when-cross-origin"
        )
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # "Public" is a property of a PAGE, and only GET/HEAD serve pages.
        # The path allowlist used to apply to every method, so the response to
        # POST /join — which can carry the e-mail address the person just
        # typed, echoed back on the consent step — went out without a
        # no-store header (external review, 25 August 2026). No response to a
        # state-changing method is ever cacheable here: they are all
        # per-person by construction.
        if request.method not in ("GET", "HEAD") or self._is_private(request.url.path):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        if "server" in response.headers:
            del response.headers["server"]

        return response


# Passed as `public_paths=DEFAULT_PUBLIC` to switch a tool to the allowlist.
DEFAULT_PUBLIC = (PUBLIC_EXACT, PUBLIC_PREFIXES)
