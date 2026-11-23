"""The message panel reads like a chat (owner, 23 November 2026).

Your own messages lean right and the others' left, and the educator's
messages are light red. This renders three messages with the real
messages.css and messages.js in Chromium: one of your own, one from the
educator, one from another hotel.

What would go red: the educator's message without its colour (the class
not set for sender 0, or the colour gone from the sheet), or both sides
standing alike.

Needs Playwright; on this Mac it lives in the browser venv, and the probe is
re-run under it when the interpreter running pytest lacks it.
    ~/.local/phronon-browser/venv/bin/python tests/test_messages_browser.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"

INITIAL = [
    {"id": 1, "from": "Hotel Larch", "to": "everyone", "text": "Mine", "mine": True, "direct": False, "hidden": False,
     "sender": 11},
    {"id": 2, "from": "Educator", "to": "everyone", "text": "From the educator", "mine": False, "direct": False,
     "hidden": False, "sender": 0},
    {"id": 3, "from": "Hotel Ibex", "to": "everyone", "text": "From another hotel", "mine": False, "direct": False,
     "hidden": False, "sender": 12},
]
PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>messages probe</title>
<link rel="stylesheet" href="/messages.css"></head>
<body><div class="ph-messages" data-messages data-mode="participant" data-words="{}" data-initial='%s'
     data-can-send="0" data-state="closed" data-scope="probe">
<ul class="ph-messages__list" data-messages-list></ul></div>
<script src="/messages.js"></script>
<script src="/probe.js"></script></body></html>
""" % json.dumps(INITIAL).replace("'", "&#39;")

PROBE_JS = r"""
'use strict';
function look(id) {
  var li = document.querySelector('[data-message-id="' + id + '"]');
  var cs = getComputedStyle(li);
  return { cls: li.className, bg: cs.backgroundColor, left: parseFloat(cs.marginLeft), right: parseFloat(cs.marginRight) };
}
window.__probe = { mine: look(1), educator: look(2), other: look(3) };
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        files = {
            "/": (PAGE.encode(), "text/html; charset=utf-8"),
            "/messages.css": ((HERE / "messages.css").read_bytes(), "text/css; charset=utf-8"),
            "/messages.js": ((HERE / "messages.js").read_bytes(), "text/javascript; charset=utf-8"),
            "/probe.js": (PROBE_JS.encode(), "text/javascript; charset=utf-8"),
        }
        body, ctype = files.get(self.path, (b"not found", "text/plain"))
        self.send_response(200 if self.path in files else 404)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def probe() -> dict:
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                errors: list = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(url)
                res = page.evaluate("window.__probe") or {}
                res["errors"] = errors
                return res
            finally:
                browser.close()
    finally:
        server.shutdown()


def _report() -> dict:
    try:
        import playwright.sync_api  # noqa: F401
        return probe()
    except ImportError:
        pass
    import pytest
    if not BROWSER_VENV_PY.exists():
        pytest.skip("playwright is not installed (browser venv: "
                    "server-ops/browser_submit_check.py has the two install lines)")
    run = subprocess.run([str(BROWSER_VENV_PY), __file__, "--json"],
                         capture_output=True, text=True, timeout=240,
                         env={**os.environ, "PYTHONPATH": ""})
    assert run.returncode == 0, run.stderr[-3000:]
    return json.loads(run.stdout)


def test_own_messages_lean_right_the_others_left_and_the_educators_are_light_red():
    res = _report()
    assert res["errors"] == [], res["errors"]
    mine, educator, other = res["mine"], res["educator"], res["other"]
    assert "ph-messages__item--educator" in educator["cls"], "the educator's message is marked as such"
    assert educator["bg"] == "rgb(253, 232, 230)", f"the educator's message is light red: {educator['bg']}"
    assert other["bg"] != educator["bg"], "another hotel's message keeps its own colour"
    assert mine["left"] > mine["right"], "your own message leans right"
    assert other["right"] > other["left"] and educator["right"] > educator["left"], "the others' lean left"


if __name__ == "__main__":
    out = probe()
    print(json.dumps(out) if "--json" in sys.argv else json.dumps(out, indent=1))
