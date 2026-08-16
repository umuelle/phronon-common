import asyncio

from starlette.requests import Request
from starlette.responses import PlainTextResponse

from phronon_common.access_log import RedactingAccessFilter
from phronon_common.security_headers import SecurityHeadersMiddleware


def _request(path: str, query: bytes = b"") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": path,
        "query_string": query, "headers": [], "scheme": "https",
        "server": ("example.org", 443), "client": ("127.0.0.1", 1),
    })


def test_query_credentials_and_prolific_identifiers_are_redacted():
    flt = RedactingAccessFilter([])
    path = ("/prolific?PROLIFIC_PID=person-1&STUDY_ID=study-2&"
            "SESSION_ID=session-3&token=reset-4&code=JOIN")
    clean = flt._redact(path)
    for secret in ("person-1", "study-2", "session-3", "reset-4"):
        assert secret not in clean
    assert "code=JOIN" in clean


def test_credential_urls_send_no_referrer_policy():
    async def app(scope, receive, send):
        await PlainTextResponse("ok")(scope, receive, send)

    async def exercise():
        middleware = SecurityHeadersMiddleware(app)

        async def call_next(_):
            return PlainTextResponse("ok")

        for request in (
            _request("/backoffice/password-reset", b"token=secret"),
            _request("/backoffice/reset-password/secret"),
            _request("/prolific", b"PROLIFIC_PID=person"),
            _request("/withdraw/secret"),
        ):
            response = await middleware.dispatch(request, call_next)
            assert response.headers["Referrer-Policy"] == "no-referrer"

    asyncio.run(exercise())


def test_ordinary_page_keeps_normal_referrer_policy():
    async def app(scope, receive, send):
        await PlainTextResponse("ok")(scope, receive, send)

    async def exercise():
        middleware = SecurityHeadersMiddleware(app)

        async def call_next(_):
            return PlainTextResponse("ok")

        response = await middleware.dispatch(
            _request("/class-code", b"code=ABCD"),
            call_next,
        )
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    asyncio.run(exercise())
