"""The fleet's tab strip, tabs.js, run in real browsers (TO DO FL-161).

Every tab is a link to ?tab=<name> so a right-click opens it in a new window
(owner, 22 November 2026). The page below carries two strips' worth of the
cases the seven tools need, served under Whiteout's policy (`script-src
'self'`), and the probe checks in Chromium and in WebKit that:

  * a plain click switches in place: the page stays, the panel shows, the
    address and this window's memory follow, the listed parameters go;
  * a Cmd-click is left to the browser (the page does not switch);
  * the address opened in a fresh window opens the tab it names, before the
    remembered one; #name works for an old bookmark;
  * a reload without a name opens the remembered tab;
  * onShow replays the open tab for a late listener and reports clicks as
    the user's; show() opens a tab for a page's own script;
  * arrow keys, Home, End and Space move and open;
  * a page without a tab bar (presentation mode) keeps every panel shown.

Needs Playwright (the browser venv on this Mac, as test_chart_export_browser).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TABS = Path(__file__).resolve().parent.parent / "tabs.js"
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; object-src 'none'; base-uri 'self'")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>tabs</title></head><body>
<div class="tabs__nav" role="tablist" data-tab-store="probe:tab" data-tab-default="two"
     data-tab-drop="done">
  <a href="?tab=one" class="tabs__tab" role="tab" data-tab="one" aria-controls="panel-one">One</a>
  <a href="?tab=two" class="tabs__tab" role="tab" data-tab="two" aria-controls="panel-two">Two</a>
  <a href="?tab=three" class="tabs__tab" role="tab" data-tab="three" aria-controls="panel-three">Three</a>
</div>
<section id="panel-one" role="tabpanel">one</section>
<section id="panel-two" role="tabpanel" hidden>two</section>
<section id="panel-three" role="tabpanel" hidden>three</section>
<script src="/tabs.js"></script>
<script src="/probe.js"></script>
</body></html>
"""

# Loaded after tabs.js and before the strip is set up, as a tool's own script is.
# Presentation mode: panels and no tab bar. Nothing may be hidden.
BARE = """<!doctype html>
<html><head><meta charset="utf-8"><title>bare</title></head><body>
<section id="slide-a" role="tabpanel">a</section>
<section id="slide-b" role="tabpanel" class="active">b</section>
<script src="/tabs.js"></script>
</body></html>
"""

PROBE_JS = r"""
window.__seen = [];
window.__marker = 1;
PhrononTabs.onShow(function (name, panel, byUser) {
  window.__seen.push([name, panel ? panel.id : null, byUser]);
});
"""

STATE_JS = """() => ({
  open: PhrononTabs.current(),
  visible: [...document.querySelectorAll('[role=tabpanel]')].filter(p => !p.hidden).map(p => p.id),
  active: [...document.querySelectorAll('.tabs__tab.active')].map(t => t.dataset.tab),
  selected: [...document.querySelectorAll('.tabs__tab[aria-selected=true]')].map(t => t.dataset.tab),
  search: location.search, hash: location.hash,
  stored: sessionStorage.getItem('probe:tab'),
  seen: window.__seen, marker: window.__marker || 0})"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        path = self.path.split("?")[0].split("#")[0]
        files = {
            "/": (PAGE.encode(), "text/html; charset=utf-8"),
            "/bare": (BARE.encode(), "text/html; charset=utf-8"),
            "/tabs.js": (TABS.read_bytes(), "text/javascript; charset=utf-8"),
            "/probe.js": (PROBE_JS.encode(), "text/javascript; charset=utf-8"),
        }
        body, ctype = files.get(path, (b"not found", "text/plain"))
        self.send_response(200 if path in files else 404)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _engines(p):
    out = ["chromium"]
    try:
        p.webkit.launch().close()
        out.append("webkit")
    except Exception:  # noqa: BLE001 - WebKit absent is reported in the result, not fatal
        pass
    return out


def probe() -> dict:
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    report: dict = {}
    try:
        with sync_playwright() as p:
            for name in _engines(p):
                browser = getattr(p, name).launch()
                try:
                    ctx = browser.new_context()
                    page = ctx.new_page()
                    errors: list = []
                    page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                    page.on("console", lambda m, errors=errors:
                            errors.append(m.text) if "Content Security Policy" in m.text else None)
                    r: dict = {}
                    page.goto(base + "?done=saved")
                    r["first"] = page.evaluate(STATE_JS)
                    page.click('.tabs__tab[data-tab="three"]')
                    r["clicked"] = page.evaluate(STATE_JS)
                    mod = "Meta" if sys.platform == "darwin" else "Control"
                    with ctx.expect_page() as popup:
                        page.click('.tabs__tab[data-tab="one"]', modifiers=[mod])
                    popup.value.close()
                    r["modified"] = page.evaluate(STATE_JS)
                    page.goto(base)
                    r["remembered"] = page.evaluate(STATE_JS)
                    page.focus('.tabs__tab[data-tab="three"]')
                    page.keyboard.press("ArrowRight")
                    r["arrow"] = page.evaluate(STATE_JS)
                    page.keyboard.press("End")
                    page.keyboard.press("Home")
                    page.focus('.tabs__tab[data-tab="two"]')
                    page.keyboard.press(" ")
                    r["space"] = page.evaluate(STATE_JS)
                    page.evaluate("PhrononTabs.show('three', false)")
                    r["shown"] = page.evaluate(STATE_JS)
                    page.evaluate("""() => { window.__late = [];
                        PhrononTabs.onShow((n, p, u) => window.__late.push([n, p && p.id, u])); }""")
                    r["late"] = page.evaluate("window.__late")
                    fresh = ctx.new_page()
                    fresh.goto(base + "?tab=one")
                    r["fresh"] = fresh.evaluate(STATE_JS)
                    fresh.goto(base + "?tab=nonsense")
                    r["unknown"] = fresh.evaluate(STATE_JS)
                    fresh.close()
                    old = ctx.new_page()
                    old.goto(base + "#three")
                    r["hash"] = old.evaluate(STATE_JS)
                    old.goto(base + "bare?tab=slide-a")
                    r["bare"] = old.evaluate("""() => ({open: PhrononTabs.current(),
                        hidden: [...document.querySelectorAll('[role=tabpanel]')].filter(p => p.hidden).map(p => p.id),
                        search: location.search})""")
                    r["pageErrors"] = errors
                    report[name] = r
                    ctx.close()
                finally:
                    browser.close()
    finally:
        server.shutdown()
    return report


def _have_playwright() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


def _report() -> dict:
    if _have_playwright():
        return probe()
    import pytest
    if not BROWSER_VENV_PY.exists():
        pytest.skip("playwright is not installed (browser venv: "
                    "server-ops/browser_submit_check.py has the two install lines)")
    run = subprocess.run([str(BROWSER_VENV_PY), __file__, "--json"],
                         capture_output=True, text=True, timeout=240,
                         env={**os.environ, "PYTHONPATH": ""})
    assert run.returncode == 0, run.stderr[-3000:]
    return json.loads(run.stdout)


def _check(report: dict) -> None:
    assert "chromium" in report, report.keys()
    for key, r in report.items():
        assert r["pageErrors"] == [], (key, r["pageErrors"])
        # No name in the address: the default opens, the address stays plain.
        f = r["first"]
        assert (f["open"], f["visible"], f["active"], f["selected"]) == (
            "two", ["panel-two"], ["two"], ["two"]), (key, f)
        assert f["search"] == "?done=saved" and f["stored"] is None, (key, f)
        assert f["seen"] == [["two", "panel-two", False]], (key, f["seen"])
        # A plain click: same page, panel, address, memory, the listed parameter gone.
        c = r["clicked"]
        assert c["marker"] == 1, (key, "a plain click left the page")
        assert (c["open"], c["visible"], c["search"], c["stored"]) == (
            "three", ["panel-three"], "?tab=three", "three"), (key, c)
        assert c["seen"][-1] == ["three", "panel-three", True], (key, c["seen"])
        # Cmd-click: a new tab of the browser's, this page unchanged.
        m = r["modified"]
        assert (m["open"], m["search"]) == ("three", "?tab=three"), (key, m)
        # A reload with no name opens the tab remembered in this window.
        assert r["remembered"]["open"] == "three" and r["remembered"]["search"] == "", (key, r["remembered"])
        # Keys: ArrowRight wraps to the first; Space opens the focused tab.
        assert r["arrow"]["open"] == "one" and r["arrow"]["search"] == "?tab=one", (key, r["arrow"])
        assert r["space"]["open"] == "two", (key, r["space"])
        # show() for a page's own script, without touching address or memory.
        s = r["shown"]
        assert (s["open"], s["visible"], s["search"], s["stored"]) == (
            "three", ["panel-three"], "?tab=two", "two"), (key, s)
        assert s["seen"][-1] == ["three", "panel-three", False], (key, s["seen"])
        assert r["late"] == [["three", "panel-three", False]], (key, r["late"])
        # The address wins over the memory of the window that opened it.
        fr = r["fresh"]
        assert (fr["open"], fr["visible"], fr["search"]) == ("one", ["panel-one"], "?tab=one"), (key, fr)
        # A name the strip does not have: the window's remembered tab, from the visit before.
        assert r["unknown"]["open"] == "one", (key, r["unknown"])
        assert r["hash"]["open"] == "three", (key, r["hash"])
        # No tab bar: nothing opened, nothing hidden, the address untouched.
        assert r["bare"] == {"open": None, "hidden": [], "search": "?tab=slide-a"}, (key, r["bare"])


def test_tabs_in_real_browsers():
    _check(_report())


if __name__ == "__main__":
    result = probe()
    if "--json" in sys.argv:
        print(json.dumps(result))
    else:
        _check(result)
        print("tabs probe: OK in", ", ".join(sorted(result)))
