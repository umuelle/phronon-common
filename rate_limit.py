"""In-app sliding-window rate limiting — one implementation for the fleet.

This is the SECOND line of defence. The first is nginx (`conf.d/10-ratelimit*`),
which sits in front of all nine sites and survives restarts; these in-app limits
are per-process and reset on deploy, so they are defence in depth and per-route
shaping — never the primary brake.

HISTORY (harmonization, 2026-07-29). Five private copies existed. This module
was the smallest of them and NOT the strictest, so adopting it as written would
have *weakened* four tools. Two things had to be brought over first:

  * **Trusted proxies.** It believed `X-Forwarded-For` from anyone, so a client
    could spoof its IP and walk past the limit — which makes IP-keyed limiting
    meaningless. The header is now honoured only when the direct peer is a
    configured proxy (the rule the audit already applied elsewhere).
  * **Exact-match rules.** With prefix matching only, a strict rule for the
    login path `/backoffice` also covers every `/backoffice/...` page, so either
    the login limit leaks onto ordinary admin browsing or the admin limit
    loosens the login. The tools that needed the distinction used exact matches.

Two shapes, because the tools genuinely need both:

  1. `RateLimitMiddleware` — declarative per-path rules, first match wins.
  2. `is_allowed(key, ...)` — a bare sliding window for call sites that limit
     something other than a path (a class code, a mailbox), used inside routes.
"""
from __future__ import annotations

import inspect
import logging
import threading
import time
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Callable, Iterable, Optional, Sequence, cast

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint
    from starlette.responses import Response
    from starlette.types import ASGIApp

# Defined in request_ip (no web framework needed to answer it); re-exported
# here because every tool imports them from rate_limit.
from .request_ip import client_ip, default_trusted_proxies  # noqa: F401

logger = logging.getLogger(__name__)

#: Methods NOT rate limited by default (safe/idempotent reads).
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class SlidingWindow:
    """Thread-safe sliding-window counter, keyed by an arbitrary string."""

    def __init__(self, cleanup_interval: int = 60):
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()

    def check(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int, int]:
        """Record a hit. Returns (allowed, count_in_window, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= max_requests:
                retry_after = max(1, int(window_seconds - (now - q[0])))
                return False, len(q), retry_after
            q.append(now)
            count = len(q)
        self._maybe_cleanup(now, window_seconds)
        return True, count, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def _maybe_cleanup(self, now: float, window_seconds: int) -> None:
        """Drop stale keys occasionally so the map cannot grow without bound."""
        if now - self._last_cleanup < self._cleanup_interval:
            return
        with self._lock:
            self._last_cleanup = now
            for key in list(self._hits):
                q = self._hits[key]
                while q and now - q[0] > window_seconds:
                    q.popleft()
                if not q:
                    del self._hits[key]


#: Process-wide window backing the `is_allowed` helper.
_shared_window = SlidingWindow()


def is_allowed(key: str, max_requests: int = 10, window_seconds: int = 60) -> bool:
    """True if this key may proceed; records the attempt. For in-route limits."""
    allowed, _, _ = _shared_window.check(key, max_requests, window_seconds)
    return allowed


class RateLimitConfig:
    """Ordered per-path rules: (pattern, max_requests, window_seconds, exact).

    FIRST MATCH WINS, so specific rules must precede general ones — an exact
    `/backoffice` login rule before the `/backoffice/` prefix rule.
    `default_rule` applies to everything unmatched; None means "unlimited".
    """

    def __init__(self, rules: Iterable[tuple], default_rule: Optional[tuple[int, int]] = None):
        # 3-tuples (prefix, max, window) are accepted as prefix rules, which is
        # the shape Layoff has passed since this module's first version.
        self.rules: list[tuple[str, int, int, bool]] = [
            (r[0], r[1], r[2], bool(r[3]) if len(r) > 3 else False) for r in rules
        ]
        self.default_rule = default_rule

    def get_rule(self, path: str) -> Optional[tuple[int, int]]:
        for pattern, max_requests, window_seconds, exact in self.rules:
            if (path == pattern) if exact else path.startswith(pattern):
                return max_requests, window_seconds
        return self.default_rule


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply rate limits per client IP and path.

    Accepts either `config=RateLimitConfig(...)` or the original
    `rules=[(prefix, max, window), ...]` shorthand.

    `limited_methods=None` (default) limits every method except GET/HEAD/
    OPTIONS. Pass an explicit set to limit reads too.

    `limited_response(request, retry_after)` builds the answer to a refused
    request, so a participant sees the tool's own page in their language
    instead of a line of JSON (TO DO FL-104, 26 October 2026: Inequality's
    /join and Layoff's participant steps answered bare JSON). It may be a
    coroutine function. The answer always leaves with status 429 and
    Retry-After, whatever the page set. Without it, or when it raises (logged),
    the JSON answer below goes out as before.
    """

    def __init__(self, app: ASGIApp, config: Optional[RateLimitConfig] = None,
                 rules: Optional[Iterable[tuple]] = None,
                 window: Optional[SlidingWindow] = None,
                 trusted_proxies: Optional[Sequence[str]] = None,
                 limited_methods: Optional[Iterable[str]] = None,
                 limited_response: Optional[Callable] = None) -> None:
        super().__init__(app)
        if config is None:
            if rules is None:
                raise ValueError("RateLimitMiddleware needs config= or rules=")
            config = RateLimitConfig(rules)
        self.config = config
        self.window = window or SlidingWindow()
        # Empty means "unset", not "trust nobody" — see client_ip().
        self.trusted_proxies = (list(trusted_proxies) if trusted_proxies
                                else default_trusted_proxies())
        self.limited_methods = frozenset(limited_methods) if limited_methods else None
        self.limited_response = limited_response

    def _applies(self, method: str) -> bool:
        if self.limited_methods is not None:
            return method in self.limited_methods
        return method not in SAFE_METHODS

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._applies(request.method):
            return await call_next(request)

        rule = self.config.get_rule(request.url.path)
        if rule is None:
            return await call_next(request)

        max_requests, window_seconds = rule
        ip = client_ip(request, self.trusted_proxies)
        key = f"{ip}::{request.url.path}"
        allowed, count, retry_after = self.window.check(key, max_requests, window_seconds)
        if not allowed:
            logger.warning("Rate limited: %s on %s (%s/%s)",
                           ip, request.url.path, count, max_requests)
            # RETURN, never raise: user middleware sits outside Starlette's
            # ExceptionMiddleware, so a raised HTTPException surfaces as a 500
            # instead of the app's own error page — the trap the CSRF module
            # documents and which this fleet has already been bitten by.
            if self.limited_response is not None:
                try:
                    page = self.limited_response(request, retry_after)
                    if inspect.isawaitable(page):
                        page = await page
                    page.status_code = 429
                    page.headers["Retry-After"] = str(retry_after)
                    return cast("Response", page)
                except Exception:  # noqa: BLE001 - logged with the traceback; the JSON answer still goes out
                    logger.exception("Rate limited on %s: the tool's own page failed",
                                     request.url.path)
            return JSONResponse(
                {"detail": "Too many requests. Please try again later."},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
