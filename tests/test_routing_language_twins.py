"""routing.add_language_twins / guard_query_lang / lang_prefix (6 October 2026).

The three tools that speak more than one language wrote `/{lang}/x` twins by
hand; these tests pin the one rule that replaces them.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

fastapi = pytest.importorskip("fastapi", reason="requires the live server environment (fastapi)")
from fastapi import APIRouter, FastAPI, Form  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from phronon_common import routing  # noqa: E402

LOCALES = ("en", "de")


def _app(keep=("/withdraw",), guard=False):
    router = APIRouter()

    @router.get("/")
    def home(lang: str = "en", code: str = ""):
        return {"page": "home", "lang": lang, "code": code}

    @router.get("/join")
    def join_get(lang: str = "en", code: str = ""):
        return {"page": "join", "lang": lang, "code": code}

    @router.post("/join")
    def join_post(lang: str = "en", code: str = Form(""), consent: str = Form("")):
        return {"page": "join-post", "lang": lang, "code": code, "consent": consent}

    @router.get("/withdraw")
    def withdraw(lang: str = "en", token: str = ""):
        return {"page": "withdraw", "lang": lang, "token": token}

    @router.post("/group")
    def group():                       # language-neutral: takes no lang at all
        return {"page": "group"}

    made = routing.add_language_twins(router, LOCALES, ["/", "/join", "/withdraw", "/group"],
                                      keep_prefix=keep)
    if guard:
        routing.guard_query_lang(router, LOCALES)
    app = FastAPI()
    app.include_router(routing.answer_head(router))
    app.state.router = router
    return app, made


def test_twins_are_registered_in_route_order_with_the_base_handler():
    app, made = _app()
    assert made == ["/{lang}", "/{lang}/join", "/{lang}/join", "/{lang}/withdraw", "/{lang}/group"]
    by_path = {}
    for r in app.state.router.routes:
        by_path.setdefault(r.path, []).append(r)
    for twin in by_path["/{lang}/join"]:
        base = next(b for b in by_path["/join"] if b.methods == twin.methods)
        assert twin.endpoint is base.endpoint


def test_a_twin_binds_lang_from_the_path_and_every_field_like_its_base():
    c = TestClient(_app()[0])
    assert c.get("/de/join?code=AB12").json() == {"page": "join", "lang": "de", "code": "AB12"}
    r = c.post("/de/join", data={"code": "AB12", "consent": "yes"})
    assert r.json() == {"page": "join-post", "lang": "de", "code": "AB12", "consent": "yes"}
    assert c.get("/de").json()["lang"] == "de"
    assert c.post("/de/group").json() == {"page": "group"}


def test_the_canonical_prefix_redirects_a_get_and_keeps_the_query():
    c = TestClient(_app()[0])
    r = c.get("/en/join?code=AB12", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/join?code=AB12"
    r = c.get("/en", follow_redirects=False)
    assert r.status_code == 301 and r.headers["location"] == "/"
    assert c.head("/en/join", follow_redirects=False).status_code == 301


def test_a_post_to_the_canonical_prefix_is_served_not_redirected():
    """A redirected POST loses its body (Layoff answered 301 to it until now)."""
    r = TestClient(_app()[0]).post("/en/join", data={"code": "AB12"}, follow_redirects=False)
    assert r.status_code == 200 and r.json()["lang"] == "en" and r.json()["code"] == "AB12"


def test_a_token_page_keeps_its_prefix():
    r = TestClient(_app()[0]).get("/en/withdraw?token=abc", follow_redirects=False)
    assert r.status_code == 200 and r.json() == {"page": "withdraw", "lang": "en", "token": "abc"}


def test_an_unknown_language_is_a_404():
    c = TestClient(_app()[0])
    assert c.get("/xx/join").status_code == 404
    assert c.post("/fr/join", data={"code": "A"}).status_code == 404


def test_twin_gets_answer_head_like_its_base():
    app, _ = _app()
    twin = next(r for r in app.state.router.routes if r.path == "/{lang}/join" and "GET" in r.methods)
    assert "HEAD" in twin.methods


def test_the_query_guard_refuses_a_language_the_tool_does_not_speak():
    c = TestClient(_app(guard=True)[0])
    assert c.get("/join?lang=de").json()["lang"] == "de"
    for hostile in ("/evil.example", "//evil.example", "xx"):
        assert c.get("/join", params={"lang": hostile}).status_code == 404, hostile
    assert c.get("/join").status_code == 200


def test_a_missing_base_or_an_existing_twin_is_refused():
    router = APIRouter()

    @router.get("/a")
    def a():
        return {}

    with pytest.raises(ValueError, match="no route"):
        routing.add_language_twins(router, LOCALES, ["/a", "/b"])
    routing.add_language_twins(router, LOCALES, ["/a"])
    with pytest.raises(ValueError, match="already exists"):
        routing.add_language_twins(router, LOCALES, ["/a"])


def test_lang_prefix_and_locale_prefixes():
    assert routing.lang_prefix("de", LOCALES) == "/de"
    assert routing.lang_prefix("en", LOCALES) == ""
    for hostile in ("/evil.example", "xx", ""):
        assert routing.lang_prefix(hostile, LOCALES) == ""
    assert routing.locale_prefixes(LOCALES) == ("", "/en", "/de")
