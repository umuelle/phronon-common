"""common_assets.py: shared styles and scripts served from the release a tool
runs (TO DO FL-069, pilot in Peak Season).

A throwaway tool folder carries the manifest; a scratch folder plays the
server's /var/www/.phronon_common-releases with two published releases.
"""
# No `from __future__ import annotations`: FastAPI resolves endpoint annotations.
from pathlib import Path

import pytest

from phronon_common import common_assets as ca
from phronon_common import shared_assets

LISTED = ["backoffice-core.css", "passkeys.js"]


def _releases(tmp_path: Path) -> Path:
    root = tmp_path / ca.RELEASES_DIR_NAME
    for tag in ("v1.0.0", "v1.1.0"):
        (root / tag).mkdir(parents=True)
        (root / tag / ".release").write_text(f"{tag} {'a' * 40}\n")
        for m in LISTED:
            (root / tag / m).write_text(f"/* {m} in {tag} */")
    return root


@pytest.fixture
def client(tmp_path):
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates
    from fastapi.testclient import TestClient

    base = tmp_path / "tool"
    (base / "templates").mkdir(parents=True)
    (base / "templates" / "page.html").write_text(
        "{{ asset('/static/css/backoffice-core.css') }}|{{ asset('/static/css/own.css') }}")
    templates = Jinja2Templates(directory=str(base / "templates"))
    templates.env.globals["asset"] = lambda p: p + "?v=checkout"
    app = FastAPI()
    common = ca.install(app, templates, LISTED)

    @app.get("/page")
    def page():
        return templates.env.get_template("page.html").render()

    return common, TestClient(app, base_url="https://testserver")


def test_a_listed_copy_is_linked_in_the_release_and_the_rest_as_before(client):
    common, c = client
    assert c.get("/page").json() == (
        f"/common/{common.release}/backoffice-core.css|/static/css/own.css?v=checkout")
    assert common.release == ca.release_name()


def test_the_release_answers_with_the_master_cached_for_a_year(client):
    common, c = client
    r = c.get(f"/common/{common.release}/backoffice-core.css")
    assert r.status_code == 200
    assert r.content == shared_assets.master_path("backoffice-core.css").read_bytes()
    assert r.headers["content-type"].startswith("text/css")
    assert r.headers["cache-control"] == ca.CACHE
    js = c.head(f"/common/{common.release}/passkeys.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")


@pytest.mark.parametrize("path", [
    "/common/{rel}/svg-charts.js",          # a master this tool does not list
    "/common/{rel}/.release",
    "/common/{rel}/..%2Fpyproject.toml",
    "/common/latest/passkeys.js",           # not a release name
    "/common/v0.0.1/passkeys.js",           # another release, outside the server layout
])
def test_nothing_else_is_answered(client, path):
    common, c = client
    assert c.get(path.format(rel=common.release)).status_code == 404


def test_on_the_server_another_published_release_is_answered_too(tmp_path):
    """After a refresh, a page rendered by the old release still loads its
    files from the old folder, which stays beside the new one."""
    root = _releases(tmp_path)
    common = ca.CommonAssets(LISTED, masters=root / "v1.1.0")
    assert common.release == "v1.1.0"
    assert common.file_for("v1.0.0", "passkeys.js").read_text() == "/* passkeys.js in v1.0.0 */"
    assert common.file_for("v1.1.0", "passkeys.js").read_text() == "/* passkeys.js in v1.1.0 */"
    assert common.file_for("v9.9.9", "passkeys.js") is None


def test_install_needs_known_masters(tmp_path):
    from fastapi import FastAPI
    from fastapi.templating import Jinja2Templates

    templates = Jinja2Templates(directory=str(tmp_path))
    templates.env.globals["asset"] = lambda p: p
    for bad in ([], ["no-such.js"]):
        with pytest.raises(RuntimeError, match="known masters"):
            ca.install(FastAPI(), templates, bad)
