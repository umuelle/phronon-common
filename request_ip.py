"""Whose address is this request really from: the one answer, fleet-wide.

`client_ip` and `default_trusted_proxies` lived in rate_limit.py until
3 October 2026, and audit.py imported them from there, so writing an audit row
pulled FastAPI and Starlette's middleware into a retention job or a script
that never serves a request. They live here now, with no web framework import
at all (a request is anything with `.client.host` and `.headers.get`).
`rate_limit` and `audit` re-export the same objects, so every existing import
keeps working and `audit.client_ip is rate_limit.client_ip` still holds.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:  # pragma: no cover
    from starlette.requests import Request


def default_trusted_proxies() -> list[str]:
    """Proxies whose `X-Forwarded-For` may be believed (from TRUSTED_PROXIES)."""
    raw = os.getenv("TRUSTED_PROXIES", "127.0.0.1")
    return [h.strip() for h in raw.split(",") if h.strip()]


def client_ip(request: "Request", trusted_proxies: Optional[Sequence[str]] = None) -> str:
    """The caller's IP, trusting `X-Forwarded-For` only behind a known proxy.

    An EMPTY list falls back to the default rather than meaning "trust nobody".
    Every app in this fleet sits behind nginx on localhost, so refusing the
    header would make every visitor look like 127.0.0.1 — one shared rate-limit
    bucket for the whole internet, where a single participant could throttle an
    entire class. That is a silent failure, and it was live: two tools' `.env`
    left TRUSTED_PROXIES unset/empty while their limiter defaulted to trusting
    localhost, so app-level and module-level defaults disagreed. If an app is
    ever exposed directly, pass an explicit sentinel host instead.

    WHICH ENTRY (6 October 2026). nginx sends `$proxy_add_x_forwarded_for`:
    whatever X-Forwarded-For the client sent, then the address nginx saw. Only
    that last entry is nginx's word; everything left of it is the client's. This
    took the FIRST entry until 1.78.1, so any client could choose its own
    rate-limit bucket (and its audit address) by sending the header itself. The
    walk goes right to left past trusted proxies, so a chain of our own proxies
    still ends at the address the outermost one saw.
    """
    proxies = default_trusted_proxies() if not trusted_proxies else trusted_proxies
    direct = request.client.host if request.client else "unknown"
    if direct in proxies:
        forwarded = request.headers.get("x-forwarded-for")
        hops = [h.strip() for h in (forwarded or "").split(",") if h.strip()]
        for hop in reversed(hops):
            if hop not in proxies:
                return hop
        if hops:
            return hops[0]
    return direct
