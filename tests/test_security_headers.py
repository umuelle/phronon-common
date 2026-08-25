"""Cache headers: "public" is a property of a page, and only GET/HEAD serve pages.

The allowlist used to apply to every HTTP method, so the RESPONSE to
POST /join — which can echo the e-mail address the person just typed —
carried no no-store header (external review, 25 August 2026). Every response
to a state-changing method is per-person by construction, so all of them are
no-store now, allowlist or not.
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from phronon_common.security_headers import DEFAULT_PUBLIC, SecurityHeadersMiddleware


def _app():
    async def page(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[
        Route("/", page),
        Route("/join", page, methods=["GET", "POST"]),
        Route("/backoffice/anything", page, methods=["GET", "POST"]),
    ])
    app.add_middleware(SecurityHeadersMiddleware, csp="default-src 'self'",
                       public_paths=DEFAULT_PUBLIC)
    return TestClient(app)


def _cache(response) -> str:
    return response.headers.get("Cache-Control", "")


def test_public_get_pages_stay_cacheable():
    client = _app()
    assert "no-store" not in _cache(client.get("/"))
    assert "no-store" not in _cache(client.get("/join"))


def test_post_responses_are_no_store_even_on_public_paths():
    """The regression this file exists for: the join form's POST response."""
    client = _app()
    response = client.post("/join", data={"email": "someone@example.org"})
    assert "no-store" in _cache(response), (
        "POST /join went out cacheable — the allowlist is being applied "
        "without looking at the method again"
    )


def test_private_paths_are_no_store_for_every_method():
    client = _app()
    assert "no-store" in _cache(client.get("/backoffice/anything"))
    assert "no-store" in _cache(client.post("/backoffice/anything"))


def test_head_follows_get():
    """HEAD serves the same representation as GET; a differing cache header
    would let an intermediary cache confuse the two."""
    client = _app()
    assert "no-store" not in _cache(client.head("/join"))
