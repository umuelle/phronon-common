"""examples/minimal_tool runs: the new-tool guide's example is executed, not read.

If a shared module changes its wiring (a middleware argument, the legal router,
the CSRF field name), this fails here, in the package that changed, rather
than in the next new tool built from a stale example.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "minimal_tool" / "app.py"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "example-only-0000000000000000000000000000000")
    spec = importlib.util.spec_from_file_location("minimal_tool_app", EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return TestClient(mod.app, base_url="https://testserver")


def test_the_page_carries_the_shared_headers_and_a_nonce(client):
    r = client.get("/")
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    assert f'nonce="{nonce}"' in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "strict-transport-security" in r.headers


def test_the_shared_legal_pages_answer(client):
    for path in ("/privacy", "/impressum", "/cookies", "/legal-notice"):
        assert client.get(path).status_code == 200, path


def test_a_post_needs_the_token_from_the_page(client):
    assert client.post("/echo", data={"word": "x"}).status_code == 403
    token = re.search(r'name="csrf_token" value="([^"]+)"', client.get("/").text).group(1)
    r = client.post("/echo", data={"word": "hello", "csrf_token": token})
    assert r.status_code == 200 and r.json() == {"word": "hello"}


def test_an_unknown_host_is_refused(client):
    assert client.get("/health", headers={"host": "evil.example"}).status_code == 400


def test_the_example_imports_no_tool_code():
    """Only the shared package and the web stack: a new tool starts from
    phronon_common, not from a copy of an existing tool."""
    probe = (
        "import importlib.util, json, os, sys\n"
        "os.environ['APP_SECRET_KEY'] = 'x' * 40\n"
        f"spec = importlib.util.spec_from_file_location('m', {str(EXAMPLE)!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "print(json.dumps(sorted({n.split('.')[0] for n in sys.modules})))\n"
    )
    import os
    import phronon_common
    # The folder this process imports phronon_common from, whatever the
    # checkout is called (CI checks the repo out as phronon-common).
    where = str(Path(phronon_common.__path__[0]).parent)
    env = {**os.environ, "PYTHONPATH": where + os.pathsep + os.environ.get("PYTHONPATH", "")}
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                         check=True, cwd=EXAMPLE.parent, env=env).stdout
    roots = set(json.loads(out.strip().splitlines()[-1]))
    for tool_module in ("app", "db", "config", "services", "database"):
        assert tool_module not in roots
