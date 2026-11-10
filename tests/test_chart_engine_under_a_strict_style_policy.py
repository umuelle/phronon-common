"""The chart engine on a page that allows no inline styles (10 November 2026).

Eight tools send `style-src 'self' 'unsafe-inline'`. Peak Season, the tenth
property, sends `style-src 'self'`: no inline <style>, no style attribute.
Until this day the engine wrote each chart's size and font as a `style`
ATTRIBUTE on its <svg>; such a page refused it (also when a script sets it)
and logged an error for every chart: the chart lost its minimum width, and the
browser journey, which fails a tool for a console error, failed the tool.

The engine now sets those declarations through the element. This test serves
a page under the strict policy, draws with the real master in Chromium and in
WebKit, and checks what a person and a gate would see:

  * no Content-Security-Policy violation and no console error;
  * the declarations are IN FORCE on every chart (display, minimum width,
    font), which they were not while the attribute was refused;
  * a chart still exports as a PNG with ink in it (the export copies the
    element's styles).

What would go red: the engine writing a style attribute again (or using
`cssText`, which such a policy refuses as well), in either engine.

Needs Playwright; on this Mac it lives in the browser venv, and the probe is
re-run under it when the interpreter running pytest lacks it (as
tests/test_chart_export_browser.py does).
    ~/.local/phronon-browser/venv/bin/python tests/test_chart_engine_under_a_strict_style_policy.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "svg-charts.js"
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"

# Peak Season's policy for styles: this site's stylesheets, nothing inline.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "frame-ancestors 'none'")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>strict style policy probe</title></head>
<body>
  <div id="rows"></div>
  <div id="bars"></div>
  <div id="line"></div>
  <div id="narrow"></div>
  <script src="/svg-charts.js"></script>
  <script src="/probe.js"></script>
</body></html>
"""

PROBE_JS = r"""
'use strict';
window.__violations = [];
document.addEventListener('securitypolicyviolation', function (e) {
  window.__violations.push(e.violatedDirective + ' ' + (e.sourceFile || e.blockedURI));
});
var PC = window.PhrononCharts;
PC.drawRows(document.getElementById('rows'), [
  { label: 'Group A', sub: '4 people', best: -2, worst: -40, avg: -24, grp: -8 },
  { label: 'Group B', sub: '5 people', best: -6, worst: -30, avg: -14, grp: -20 },
], { aria: 'Group scores' });
PC.drawBars(document.getElementById('bars'), [
  { label: '1', value: 3 }, { label: '2', value: 7 }, { label: '3', value: 5 },
], { aria: 'Answers per option', height: 300 });
PC.drawLine(document.getElementById('line'), [
  { label: 'Hotel Larch', values: [1, 2, 3, 2], color: '#2a78d6' },
], { cats: ['1', '2', '3', '4'], aria: 'A line over four seasons', yLabel: 'units', xLabel: 'season' });
PC.drawRadar(document.getElementById('narrow'), ['a', 'b', 'c'],
  [{ label: 'one', values: [1, 2, 3] }], { aria: 'A radar', max: 3 });

function seen(id) {
  var svg = document.getElementById(id).querySelector('svg');
  if (!svg) { return null; }
  var cs = getComputedStyle(svg);
  return { display: cs.display, minWidth: cs.minWidth, font: cs.fontFamily,
           own: [svg.style.display, svg.style.height, svg.style.minWidth, svg.style.fontFamily] };
}
window.__probe = (async function () {
  var out = { charts: {} };
  ['rows', 'bars', 'line', 'narrow'].forEach(function (id) { out.charts[id] = seen(id); });
  var blob = await PC.exportChartPng(document.getElementById('bars'), { download: false });
  var bmp = await createImageBitmap(blob);
  var c = document.createElement('canvas');
  c.width = bmp.width; c.height = bmp.height;
  var ctx = c.getContext('2d');
  ctx.drawImage(bmp, 0, 0);
  var d = ctx.getImageData(0, 0, c.width, c.height).data, ink = 0;
  for (var i = 0; i < d.length; i += 4) { if (d[i] < 200 || d[i + 1] < 200 || d[i + 2] < 200) ink++; }
  out.png = { width: bmp.width, height: bmp.height, ink: ink };
  out.violations = window.__violations;
  return out;
})().catch(function (e) { return { error: String(e && e.stack || e) }; });
"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        files = {
            "/": (PAGE.encode(), "text/html; charset=utf-8"),
            "/svg-charts.js": (ENGINE.read_bytes(), "text/javascript; charset=utf-8"),
            "/probe.js": (PROBE_JS.encode(), "text/javascript; charset=utf-8"),
        }
        body, ctype = files.get(self.path, (b"not found", "text/plain"))
        self.send_response(200 if self.path in files else 404)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def probe() -> dict:
    """Serve the page, run it in each engine, return everything checked."""
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    report: dict = {}
    try:
        with sync_playwright() as p:
            for name in ("chromium", "webkit"):
                try:
                    browser = getattr(p, name).launch()
                except Exception as exc:  # noqa: BLE001 - an engine that is not installed is reported, not fatal
                    report[name] = {"missing": str(exc)[:200]}
                    continue
                try:
                    page = browser.new_page()
                    console: list = []
                    page.on("console", lambda m, console=console: console.append(m.text) if m.type == "error" else None)
                    page.on("pageerror", lambda e, console=console: console.append("uncaught: " + str(e)))
                    page.goto(url)
                    res = page.evaluate("window.__probe")
                    res["console"] = [c for c in console if "favicon" not in c]
                    report[name] = res
                finally:
                    browser.close()
    finally:
        server.shutdown()
    return report


def _have_playwright() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


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


def test_the_engine_draws_without_an_inline_style_under_a_strict_policy():
    report = _report()
    assert "chromium" in report and "missing" not in report["chromium"], report.get("chromium")
    for engine, res in report.items():
        if "missing" in res:
            continue                      # WebKit is not installed everywhere; Chromium always runs
        assert "error" not in res, f"[{engine}] the probe failed: {res.get('error')}"
        assert res["violations"] == [], f"[{engine}] the policy refused something the engine did: {res['violations']}"
        assert res["console"] == [], f"[{engine}] the console shows errors: {res['console']}"
        for chart in ("rows", "bars", "line"):
            got = res["charts"][chart]
            assert got, f"[{engine}] {chart}: no chart was drawn"
            assert got["display"] == "block" and got["minWidth"] == "700px", \
                f"[{engine}] {chart}: the chart's size is not in force: {got}"
            assert "system-ui" in got["font"], f"[{engine}] {chart}: the chart's font is not in force: {got['font']}"
            assert got["own"][0] == "block" and got["own"][1] == "auto" and got["own"][2] == "700px", \
                f"[{engine}] {chart}: the declarations are not on the element, where the export reads them: {got}"
        assert res["png"]["ink"] > 500 and res["png"]["width"] > 0, f"[{engine}] the exported PNG is empty: {res['png']}"


if __name__ == "__main__":
    out = probe()
    if "--json" in sys.argv:
        print(json.dumps(out))
    else:
        for engine, res in out.items():
            print(engine, json.dumps(res, indent=1)[:1500])
