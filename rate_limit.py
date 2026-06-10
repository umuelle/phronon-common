"""Compact in-memory sliding-window rate limiter (shared).

Per-IP, per-path-prefix limits. In-process only (fine for a single Gunicorn worker
or low-traffic classroom tool); swap for Redis if the suite ever scales out.
"""
from __future__ import annotations

import time
import threading
import logging
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Limit requests per client IP for matching path prefixes.

    rules: list of (path_prefix, max_requests, window_seconds).
    The first matching rule applies; unmatched paths are unlimited.
    """

    def __init__(self, app, rules: list[tuple[str, int, int]]):
        super().__init__(app)
        self.rules = rules
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _client_ip(request: Request) -> str:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _match(self, path: str):
        for prefix, limit, window in self.rules:
            if path.startswith(prefix):
                return limit, window
        return None

    async def dispatch(self, request: Request, call_next):
        rule = self._match(request.url.path)
        if rule is None:
            return await call_next(request)
        limit, window = rule
        key = f"{self._client_ip(request)}::{request.url.path}"
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                logger.warning("Rate limit hit for %s", key)
                return JSONResponse({"error": "Too many requests"}, status_code=429)
            q.append(now)
        return await call_next(request)
