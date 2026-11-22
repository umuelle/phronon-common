"""A line chart's reference series (owner, 22 November 2026).

Layoff's ranking-by-segment chart compares each demographic segment with the
whole class. The class line is a yardstick, so `drawLine` draws a series with
`reference: true` as a thin dotted line beneath the segment lines, with no
dots and no numbers on it (those would sit on top of the segment's numbers),
and names it in the legend with a dotted mark.

This draws one segment and one reference line with the real master in
Chromium and checks what a reader sees: the segment keeps its dots and its
eight numbers, the reference line has none and is dotted, it lies under the
segment line, and the legend shows a dotted mark for it.

What would go red: `reference` being ignored (the class line gets dots and
numbers and a square legend mark), or drawn over the segment line.

Needs Playwright; on this Mac it lives in the browser venv, and the probe is
re-run under it when the interpreter running pytest lacks it.
    ~/.local/phronon-browser/venv/bin/python tests/test_line_chart_reference_series.py
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

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>reference line probe</title></head>
<body><div id="line"></div>
<script src="/svg-charts.js"></script><script src="/probe.js"></script></body></html>
"""

PROBE_JS = r"""
'use strict';
var cats = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
window.PhrononCharts.drawLine(document.getElementById('line'), [
  { label: 'Whole class (n=27)', values: [5.1, 4.2, 3.5, 3.7, 5.0, 4.3, 4.8, 5.4],
    color: '#6b7280', reference: true },
  { label: 'None (n=11)', values: [5.45, 4.45, 3.36, 3.55, 5.36, 4.09, 4.91, 4.82],
    color: '#1e3c72' },
], { cats: cats, yMin: 1, yMax: 8, yStep: 1, reverse: true, legend: true,
     pointValues: true, aria: 'probe', height: 420 });
var svg = document.querySelector('#line svg');
var paths = Array.prototype.slice.call(svg.querySelectorAll('path'));
var refIdx = paths.findIndex(function (p) { return p.getAttribute('data-reference') === 'true'; });
var segIdx = paths.findIndex(function (p) { return p.getAttribute('stroke') === '#1e3c72'; });
var ref = paths[refIdx];
var nums = Array.prototype.slice.call(svg.querySelectorAll('text'))
  .map(function (t) { return t.textContent; })
  .filter(function (t) { return /^\d+\.\d+$/.test(t); });
var legendLines = Array.prototype.slice.call(svg.querySelectorAll('line'))
  .filter(function (l) { return l.getAttribute('stroke-dasharray') && l.getAttribute('stroke') === '#6b7280'; });
window.__probe = {
  refFound: refIdx >= 0,
  refUnderSegment: refIdx >= 0 && segIdx >= 0 && refIdx < segIdx,
  refDash: ref ? ref.getAttribute('stroke-dasharray') : null,
  refDots: svg.querySelectorAll('circle[fill="#6b7280"]').length,
  segDots: svg.querySelectorAll('circle[fill="#1e3c72"]').length,
  numbers: nums,
  legendDotted: legendLines.length,
};
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


def test_a_reference_series_is_a_dotted_yardstick_without_dots_or_numbers():
    res = _report()
    assert res["errors"] == [], res["errors"]
    assert res["refFound"], "the reference line was not drawn"
    assert res["refDash"], "the reference line is not dotted"
    assert res["refUnderSegment"], "the reference line is drawn over the segment line"
    assert res["refDots"] == 0, "the reference line carries dots"
    assert res["segDots"] == 8, "the segment line lost its dots"
    assert sorted(res["numbers"]) == sorted(
        ["5.45", "4.45", "3.36", "3.55", "5.36", "4.09", "4.91", "4.82"]), \
        f"only the segment's eight numbers should be on the chart: {res['numbers']}"
    assert res["legendDotted"] == 1, "the legend has no dotted mark for the reference line"


if __name__ == "__main__":
    out = probe()
    print(json.dumps(out) if "--json" in sys.argv else json.dumps(out, indent=1))
