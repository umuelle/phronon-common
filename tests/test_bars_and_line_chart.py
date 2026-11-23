"""Stacked bars with a line on a second axis (owner, 23 November 2026).

Peak Season shows the room nights sold by price band as stacked bars and the
average price per night as a line on a right axis: two measures of the same
seasons in different units. `drawBarsAndLine` draws both, each axis from
zero, the line and its axis in one colour.

This draws four seasons with the real master in Chromium and checks what a
reader sees: one segment per non-zero value, the line through one dot per
season with a price, the right axis numbered in the line's colour and on its
own scale (its top tick at the price scale, the left one at the bars'), both
axes starting at zero, and the line named in the legend.

What would go red: the line drawn on the bars' scale, a missing right axis,
an axis that does not start at zero, or the line missing from the legend.

Needs Playwright; on this Mac it lives in the browser venv, and the probe is
re-run under it when the interpreter running pytest lacks it.
    ~/.local/phronon-browser/venv/bin/python tests/test_bars_and_line_chart.py
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
<html lang="en"><head><meta charset="utf-8"><title>bars and line probe</title></head>
<body><div id="chart"></div>
<script src="/svg-charts.js"></script><script src="/probe.js"></script></body></html>
"""

PROBE_JS = r"""
'use strict';
var LC = '#b45309';
window.PhrononCharts.drawBarsAndLine(document.getElementById('chart'), ['1', '2', '3', '4'], [
  { up: 9, mid: 0, low: 0 }, { up: 4, mid: 12, low: 0 }, { up: 0, mid: 10, low: 1.5 }, { up: 0, mid: 3, low: 8 },
], { keys: ['up', 'mid', 'low'], fills: { up: '#33414f', mid: '#6f7c89', low: '#a3adb8' },
     labels: { up: '150 and more', mid: '90 to 145', low: 'under 90' }, darkText: { low: true },
     line: { label: 'Average price per night', values: [175, 140, null, 95], color: LC },
     yLabel: 'Thousand room nights', y2Label: 'Valley Crowns per night', xLabel: 'Season', aria: 'probe', digits: 1 });
var svg = document.querySelector('#chart svg');
var texts = Array.prototype.slice.call(svg.querySelectorAll('text'));
var right = texts.filter(function (t) { return t.getAttribute('data-axis') === 'right'; });
var rightTicks = right.filter(function (t) { return !t.getAttribute('transform'); }).map(function (t) { return t.textContent; });
var leftTicks = texts.filter(function (t) { return t.getAttribute('text-anchor') === 'end'; }).map(function (t) { return t.textContent; });
var line = svg.querySelector('path[data-line="true"]');
window.__probe = {
  segments: svg.querySelectorAll('rect title').length,
  dots: svg.querySelectorAll('circle[fill="' + LC + '"]').length,
  lineStroke: line ? line.getAttribute('stroke') : null,
  rightColoured: right.length > 0 && right.every(function (t) { return t.getAttribute('fill') === LC; }),
  rightTitle: right.some(function (t) { return t.textContent === 'Valley Crowns per night'; }),
  rightFirst: rightTicks[0], rightLast: rightTicks[rightTicks.length - 1],
  leftFirst: leftTicks[0], leftLast: leftTicks[leftTicks.length - 1],
  legendLine: texts.some(function (t) { return t.textContent === 'Average price per night' && t.getAttribute('fill') === LC; }),
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


def test_bars_on_the_left_axis_and_a_line_on_its_own_right_axis():
    res = _report()
    assert res["errors"] == [], res["errors"]
    assert res["segments"] == 7, f"one segment per non-zero value: {res['segments']}"
    assert res["dots"] == 3, "one dot per season with a price, none where the price is missing"
    assert res["lineStroke"] == "#b45309", "the line is drawn in its colour"
    assert res["rightColoured"] and res["rightTitle"], "the right axis and its title carry the line's colour"
    assert res["leftFirst"] == "0" and res["rightFirst"] == "0", "both axes start at zero"
    assert res["leftLast"] == "20" and res["rightLast"] == "200", \
        f"each axis has its own scale: left {res['leftLast']}, right {res['rightLast']}"
    assert res["legendLine"], "the line is named in the legend, in its colour"


if __name__ == "__main__":
    out = probe()
    print(json.dumps(out) if "--json" in sys.argv else json.dumps(out, indent=1))
