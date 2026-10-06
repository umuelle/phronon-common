"""join_sheet: one body for the eight tools' GET /share/{code} (6 October 2026)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytest.importorskip("fastapi", reason="requires the live server environment (fastapi)")
pytest.importorskip("qrcode", reason="requires the live server environment (qrcode)")
from fastapi import APIRouter, FastAPI, Request  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from phronon_common import join_sheet, rate_limit  # noqa: E402

SESSIONS = {"AB12": {"code": "AB12", "title": "Ethics"}}


def _sheet(**kw):
    def find(request, value):
        return SESSIONS.get(join_sheet.session_code(value))

    def render(request, template, ctx, lang):
        return HTMLResponse(f"{template}|{lang}|{ctx['code']}|{ctx['join_url']}|"
                            f"{'svg' if '<svg' in ctx['qr_svg'] else 'no-qr'}")

    return join_sheet.JoinSheet(
        find=find, join_url=lambda request, row: f"https://tool.example/join?code={row['code']}",
        context=lambda request, row, url, qr: {"code": row["code"], "join_url": url, "qr_svg": qr},
        render=render, client_ip=kw.pop("client_ip", lambda request: "203.0.113.9"), **kw)


def _client(sheet):
    router = APIRouter()

    @router.get("/share/{code}")
    def share(request: Request, code: str):
        return join_sheet.render_join_sheet(request, code, sheet)

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_window():
    rate_limit._shared_window._hits.clear()
    yield
    rate_limit._shared_window._hits.clear()


def test_a_sheet_for_a_known_code_any_case():
    c = _client(_sheet())
    for path in ("/share/AB12", "/share/ab12", "/share/%20ab12%20"):
        r = c.get(path)
        assert r.status_code == 200, path
        assert r.text == "share_card.html|en|AB12|https://tool.example/join?code=AB12|svg"
        assert r.headers["x-robots-tag"] == "noindex, nofollow"


def test_an_unknown_code_is_a_404():
    assert _client(_sheet()).get("/share/ZZ99").status_code == 404


def test_the_qr_encodes_the_join_address():
    svg = join_sheet.qr_svg("https://tool.example/join?code=AB12")
    assert svg.startswith("<?xml") and "<svg" in svg
    assert svg == join_sheet.qr_svg("https://tool.example/join?code=AB12")


def test_twenty_a_minute_per_client():
    c = _client(_sheet())
    codes = [c.get("/share/AB12").status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429
    other = _client(_sheet(client_ip=lambda request: "198.51.100.7"))
    assert other.get("/share/AB12").status_code == 200, "a second address has its own bucket"


def test_find_sees_the_value_as_typed_for_a_token():
    seen = []

    def find(request, value):
        seen.append(value)
        return None

    sheet = join_sheet.JoinSheet(find=find, join_url=lambda r, row: "", context=lambda *a: {},
                                 render=lambda *a: HTMLResponse(""))
    _client(sheet).get("/share/eyJpZCI6NH0.sig-Token_x")
    assert seen == ["eyJpZCI6NH0.sig-Token_x"], "a signed token must reach find unchanged"
