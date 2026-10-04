"""frontend_assets.py: immutable stylesheet bundles, the application's half
(TO DO FL-078; pilot in Layoff, fleet-wide from v1.74.0).

A scratch folder plays the server's /var/www/.phronon-frontend/<service>; a
throwaway tool folder carries the contract. The last tests wire a small
FastAPI app through install(), exactly as a tool's app.py does.
"""
# No `from __future__ import annotations`: FastAPI must resolve the Request
# annotation of the test app's endpoint, which is imported inside a fixture.
import json
import os
from pathlib import Path

import pytest

from phronon_common import frontend_assets as fa

CSS = "css/backoffice.css"


def _tool(tmp_path: Path, tool: str = "layoff") -> Path:
    base = tmp_path / "tool"
    (base / "frontend").mkdir(parents=True)
    (base / "static" / "css").mkdir(parents=True)
    (base / "static" / CSS).write_text("/* checkout */")
    (base / "frontend" / "contract.json").write_text(json.dumps(
        {"contract_version": 1, "tool": tool, "assets": [CSS]}))
    return base


def _bundle(root: Path, bid: str, css: bytes) -> str:
    d = root / "bundles" / bid / "css"
    d.mkdir(parents=True, exist_ok=True)
    (d / "backoffice.css").write_bytes(css)
    return bid


def _activate(root: Path, bid: str, tool: str = "layoff", **over) -> None:
    m = {"schema": 1, "tool": tool, "bundle": bid, "files": {CSS: "h"}}
    m.update(over)
    tmp = root / "active.json.tmp"
    tmp.write_text(json.dumps(m))
    os.replace(tmp, root / "active.json")


@pytest.fixture
def fe(tmp_path):
    root = tmp_path / "frontend-root"
    root.mkdir()
    return fa.Frontend(_tool(tmp_path), root=root)


def _asset(fe, path):
    return fe.wrap_asset(lambda p: p + "?v=checkout")(path)


def _in_request(fe, fn):
    token = fe.begin_request()
    try:
        return fn()
    finally:
        fe.end_request(token)


def test_a_tool_without_a_contract_is_not_enrolled(tmp_path):
    fe = fa.Frontend(tmp_path)
    assert fe.contract is None and fe.root is None and fe.current() is None
    assert _in_request(fe, lambda: _asset(fe, "/static/css/backoffice.css")) == "/static/css/backoffice.css?v=checkout"
    assert fe.bundle_file("0" * 16, CSS) is None


def test_the_server_folder_is_the_tools_service_name(tmp_path, monkeypatch):
    monkeypatch.delenv("FRONTEND_ROOT", raising=False)
    from phronon_common.registry import TOOLS
    for key, tool in TOOLS.items():
        assert fa.default_root(key) == Path("/var/www/.phronon-frontend") / tool.service
    assert fa.Frontend(_tool(tmp_path, "whiteout")).root == Path("/var/www/.phronon-frontend/whiteout-exercise")
    monkeypatch.setenv("FRONTEND_ROOT", str(tmp_path / "preview"))
    assert fa.Frontend(_tool(tmp_path / "x", "whiteout")).root == tmp_path / "preview"


def test_without_a_manifest_everything_stays_on_the_checkout(fe):
    assert _in_request(fe, lambda: _asset(fe, "/static/css/backoffice.css")) == "/static/css/backoffice.css?v=checkout"


def test_an_enrolled_file_comes_from_the_active_bundle_and_others_do_not(fe):
    bid = _bundle(fe.root, "a" * 16, b"a{}")
    _activate(fe.root, bid)

    def both():
        return (_asset(fe, "/static/css/backoffice.css"), _asset(fe, "/static/css/backoffice-core.css"))
    assert _in_request(fe, both) == (f"/frontend/{bid}/css/backoffice.css",
                                     "/static/css/backoffice-core.css?v=checkout")
    assert fe.active_bundle() == bid


def test_one_request_keeps_one_bundle_even_if_activation_happens_mid_render(fe):
    old = _bundle(fe.root, "a" * 16, b"a{}")
    _activate(fe.root, old)
    token = fe.begin_request()
    try:
        first = _asset(fe, "/static/css/backoffice.css")
        new = _bundle(fe.root, "b" * 16, b"b{}")
        _activate(fe.root, new)                      # activation during the render
        assert _asset(fe, "/static/css/backoffice.css") == first
    finally:
        fe.end_request(token)
    assert _in_request(fe, lambda: _asset(fe, "/static/css/backoffice.css")) == f"/frontend/{new}/css/backoffice.css"


@pytest.mark.parametrize("bad", [
    "{not json",
    json.dumps({"schema": 1, "tool": "whiteout", "bundle": "0" * 16, "files": {CSS: "x"}}),
    json.dumps({"schema": 1, "tool": "layoff", "bundle": "../../etc", "files": {CSS: "x"}}),
    json.dumps({"schema": 1, "tool": "layoff", "bundle": "f" * 16, "files": {CSS: "x"}}),   # no such bundle
    json.dumps({"schema": 1, "tool": "layoff", "bundle": "a" * 16, "files": {}}),           # not the contract's set
])
def test_a_broken_manifest_keeps_the_last_good_one(fe, bad):
    good = _bundle(fe.root, "a" * 16, b"a{}")
    _activate(fe.root, good)
    assert fe.current()["bundle"] == good
    (fe.root / "active.json").write_text(bad)
    assert fe.current()["bundle"] == good


def test_a_broken_manifest_with_no_good_one_means_the_checkout_for_all(fe):
    (fe.root / "active.json").write_text("{not json")
    assert fe.current() is None


def test_bundle_files_resolve_only_inside_their_bundle(fe):
    bid = _bundle(fe.root, "a" * 16, b"a{}")
    assert fe.bundle_file(bid, CSS)[1].startswith("text/css")
    for rel in ("../active.json", "css/../../active.json", ".hidden.css", "css/x.js", "css/missing.css", ""):
        assert fe.bundle_file(bid, rel) is None, rel
    assert fe.bundle_file("../bundles", CSS) is None
    (fe.root / "bundles" / bid / "css" / "link.css").symlink_to(fe.root / "active.json")
    assert fe.bundle_file(bid, "css/link.css") is None


# ── install(): what a tool's app.py does ─────────────────────────────────────
@pytest.fixture
def app_and_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI, Request
    from fastapi.templating import Jinja2Templates
    from fastapi.testclient import TestClient

    from phronon_common.security_headers import DEFAULT_PUBLIC, SecurityHeadersMiddleware

    base = _tool(tmp_path)
    (base / "templates").mkdir()
    (base / "templates" / "page.html").write_text(
        "<link rel=\"stylesheet\" href=\"{{ asset('/static/css/backoffice.css') }}\">")
    root = tmp_path / "frontend-root"
    root.mkdir()
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, public_paths=DEFAULT_PUBLIC)
    templates = Jinja2Templates(directory=str(base / "templates"))
    templates.env.globals["asset"] = lambda p: p + "?v=checkout"
    monkeypatch.setattr(fa, "_installed", None)
    fe = fa.install(app, templates, base, root=root)

    @app.get("/page")
    async def page(request: Request):
        return templates.TemplateResponse(request, "page.html")

    @app.get("/health")
    async def health():
        return {"status": "ok", "frontend_bundle": fa.active_bundle()}

    return fe, TestClient(app, base_url="https://testserver")


def test_install_wires_the_asset_global_the_route_and_health(app_and_client):
    fe, client = app_and_client
    assert client.get("/health").json()["frontend_bundle"] is None
    assert "/static/css/backoffice.css?v=checkout" in client.get("/page").text
    old = _bundle(fe.root, "a" * 16, b"/* old */")
    _activate(fe.root, old)
    new = _bundle(fe.root, "b" * 16, b"/* new */")
    _activate(fe.root, new)
    assert f"/frontend/{new}/css/backoffice.css" in client.get("/page").text
    assert client.get("/health").json()["frontend_bundle"] == new
    r = client.get(f"/frontend/{old}/css/backoffice.css")         # an old page's URL
    assert r.status_code == 200 and r.content == b"/* old */"
    assert r.headers["content-type"].startswith("text/css")
    assert "immutable" in r.headers["cache-control"] and "no-store" not in r.headers["cache-control"]
    assert client.head(f"/frontend/{new}/css/backoffice.css").status_code == 200
    assert client.get(f"/frontend/{old}/css/../../active.json").status_code == 404


def test_install_needs_the_asset_global_first(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=str(tmp_path))
    with pytest.raises(RuntimeError, match="asset"):
        fa.install(FastAPI(), templates, tmp_path)
