"""country-other.js, run in real browsers (FL-102, 25 October 2026).

The box behind "Other / not listed" must show only while that choice is
selected, and be emptied when it hides. This serves pages under a strict
Content-Security-Policy (`script-src 'self'`, no inline script), drives the
real master in Chromium and in WebKit, and checks four layouts:

  * the box inside the select's form (every tool today);
  * the box OUTSIDE the form, joined to it with a `form=` attribute: until
    FL-102 the script looked only inside the form element, so Inequality had
    to move its form's opening tag above the country select;
  * two forms on one page: each select drives its own box;
  * a select in no form: the first box in the document.

What would go red: a box that stays hidden on Other, stays visible or keeps
its typed text on another choice, or a select that drives another form's box.

Needs Playwright with Chromium and WebKit. On this Mac it lives in the browser
venv (~/.local/phronon-browser/venv, see server-ops/browser_submit_check.py);
when the interpreter running pytest lacks it, the probe is re-run under that
venv. Run directly for the raw report:
    ~/.local/phronon-browser/venv/bin/python tests/test_country_other_browser.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "country-other.js"
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'"

_OPTIONS = ('<option value="">Choose</option><option value="DE">Germany</option>'
            '<option value="OTHER">Other / not listed</option>')
PAGE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>country box probe</title></head>
<body>
  <form id="inside"><select data-country-select>{_OPTIONS}</select>
    <input id="box-inside" data-country-other hidden></form>

  <form id="joined"><select data-country-select>{_OPTIONS}</select></form>
  <input id="box-joined" form="joined" data-country-other hidden>

  <form id="first"><select data-country-select>{_OPTIONS}</select>
    <input id="box-first" data-country-other hidden></form>
  <form id="second"><select data-country-select>{_OPTIONS}</select>
    <input id="box-second" data-country-other hidden></form>

  <script src="/country-other.js"></script>
</body></html>
"""
LOOSE = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>no form</title></head>
<body>
  <select data-country-select>{_OPTIONS}</select>
  <p><input id="box-loose" data-country-other hidden></p>
  <script src="/country-other.js"></script>
</body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        if self.path == "/country-other.js":
            body, kind = SCRIPT.read_bytes(), "text/javascript"
        elif self.path == "/loose":
            body, kind = LOOSE.encode(), "text/html; charset=utf-8"
        else:
            body, kind = PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _state(page, box: str) -> dict:
    return page.eval_on_selector(f"#{box}", "b => ({hidden: b.hidden, "
                                 "shown: getComputedStyle(b).display !== 'none', value: b.value})")


def run_probe() -> dict:
    """Drive both browsers; return {browser: {case: [states...]}}."""
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    report: dict = {}
    try:
        with sync_playwright() as pw:
            for engine in (pw.chromium, pw.webkit):
                browser = engine.launch()
                page = browser.new_page()
                errors: list = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                got: dict = {}
                page.goto(base + "/")
                for form, box in (("inside", "box-inside"), ("joined", "box-joined"),
                                  ("first", "box-first")):
                    select = f"#{form} select"
                    steps = [_state(page, box)]
                    page.select_option(select, "OTHER")
                    steps.append(_state(page, box))
                    # Typed by script: a box that never showed cannot be filled
                    # by a user, and the next step must still be checkable.
                    page.eval_on_selector(f"#{box}", "b => { b.value = 'Atlantis'; }")
                    if form == "first":   # the other form's box must not move
                        steps.append(_state(page, "box-second"))
                    page.select_option(select, "DE")
                    steps.append(_state(page, box))
                    got[form] = steps
                page.goto(base + "/loose")
                steps = [_state(page, "box-loose")]
                page.select_option("select", "OTHER")
                steps.append(_state(page, "box-loose"))
                got["loose"] = steps
                got["errors"] = errors
                report[engine.name] = got
                browser.close()
    finally:
        server.shutdown()
    return report


def _report() -> dict:
    try:
        import playwright  # noqa: F401
    except ImportError:
        import pytest   # here, so the browser venv can run this file without it
        if not BROWSER_VENV_PY.exists():
            pytest.skip("needs Playwright (the browser venv, see server-ops/browser_submit_check.py)")
        out = subprocess.run([str(BROWSER_VENV_PY), __file__], capture_output=True, text=True,
                             timeout=300)
        assert out.returncode == 0, out.stderr[-2000:]
        return json.loads(out.stdout)
    return run_probe()


HIDDEN = {"hidden": True, "shown": False, "value": ""}
SHOWN = {"hidden": False, "shown": True, "value": ""}


def test_the_box_follows_its_own_select_in_both_browsers():
    report = _report()
    assert set(report) == {"chromium", "webkit"}
    for browser, got in report.items():
        assert got["errors"] == [], f"{browser}: {got['errors']}"
        for form in ("inside", "joined"):
            assert got[form] == [HIDDEN, SHOWN, HIDDEN], f"{browser}, box {form}: {got[form]}"
        assert got["first"] == [HIDDEN, SHOWN, HIDDEN, HIDDEN], (
            f"{browser}: the first form's select moved another form's box: {got['first']}")
        assert got["loose"] == [HIDDEN, SHOWN], f"{browser}, no form: {got['loose']}"


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run_probe()))
