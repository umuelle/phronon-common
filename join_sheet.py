"""The join sheet: the public page an educator shows a room (FL-089 follow-up).

Every tool serves GET /share/{code}: the session's code, the address to type
and a QR code of it, noindex, no sign-in (server-ops README §3, "The join sheet
is a participant page"). Eight copies of that page drifted: six drew the QR
inline, two served a PNG from a route at a lower error-correction level; one
answered an unknown code with a 200 error page, the others with 404; one
refused a lower-case code; two rate-limited the page in the app, at different
rates. Since 6 October 2026 the body is this module and the behaviour is one:

  * a code is looked up upper-cased (`session_code`; codes are upper case);
  * a code that names no session the tool shows a sheet for is a 404;
  * the QR is inline SVG, error correction M (what six tools drew);
  * every answer says `X-Robots-Tag: noindex, nofollow` (the meta tag stays);
  * 20 requests a minute per client address (Drawbridge's limit), on top of
    nginx's limit for every /share/ address.

What stays the tool's is data: which sessions get a sheet (`find`: Controversy
Generator's open sessions, Drawbridge's unarchived ones and its signed-token
links), the address the code joins (`join_url`), what the card shows
(`context` and the tool's own template), and how the tool renders (`render`).

Each tool keeps its own decorated `@router.get("/share/...")` route in its own
routes_participant.py: server-ops/fleet_share_page_check.py (deploy gate) reads
it there. The route's body is one call to `render_join_sheet`.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

#: Per client address, per tool process (phronon_common.rate_limit's window).
RATE_LIMIT = (20, 60)

def session_code(value: str) -> str:
    """A typed session code as the tools store it: stripped, upper case."""
    return (value or "").strip().upper()


def qr_svg(url: str) -> str:
    """The QR code of `url` as inline SVG (error correction M, box 10, border 4).

    The call chain is the one six tools used, byte for byte, and qrcode is
    imported here so a test that replaces the module in sys.modules reaches it.
    Raises on failure: a sheet without its QR is not a sheet (unlike the
    authenticator enrolment page, whose qr_svg has a typed fallback)."""
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(image_factory=qrcode.image.svg.SvgPathImage).save(buf)
    return buf.getvalue().decode("utf-8")


@dataclass(frozen=True)
class JoinSheet:
    """What one tool's join sheet needs from the tool."""

    #: (request, value) -> the session row, or None for no sheet (404). The
    #: value is the path segment, stripped: `find` normalises it (a code with
    #: `session_code`; Drawbridge's signed token as it is) and applies the
    #: tool's filters.
    find: Callable[[Any, str], Optional[Mapping]]
    #: (request, row) -> the address the code joins; the QR encodes it.
    join_url: Callable[[Any, Mapping], str]
    #: (request, row, join_url, qr_svg) -> the tool's template context.
    context: Callable[[Any, Mapping, str, str], dict]
    #: (request, template, context, lang) -> the response, rendered the way
    #: the tool renders its participant pages.
    render: Callable[[Any, str, dict, str], Any]
    #: (request) -> the client address the rate limit is keyed on.
    client_ip: Optional[Callable[[Any], str]] = None
    template: str = "share_card.html"


def render_join_sheet(request, code: str, sheet: JoinSheet, lang: str = "en"):
    """The join sheet for `code`. Synchronous: call it from the tool's route,
    `def` or `async def`, as the route already is."""
    from fastapi import HTTPException

    from .rate_limit import is_allowed
    from .request_ip import client_ip

    who = (sheet.client_ip or client_ip)(request)
    if not is_allowed(f"share:{who}", max_requests=RATE_LIMIT[0], window_seconds=RATE_LIMIT[1]):
        raise HTTPException(status_code=429, detail="Too many requests")
    wanted = (code or "").strip()
    row = sheet.find(request, wanted) if wanted else None
    if row is None:
        raise HTTPException(status_code=404)
    url = sheet.join_url(request, row)
    response = sheet.render(request, sheet.template, sheet.context(request, row, url, qr_svg(url)), lang)
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response
