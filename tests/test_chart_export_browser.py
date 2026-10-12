"""The chart engine's export functions, run in real browsers (FL-098 point 8).

svg-charts.js now carries the fleet's one SVG-to-PNG routine, its CSV writer
and its ZIP writer. JavaScript that turns a chart into a file can only be
judged in a browser: whether the PNG has the chart in it, whether its ground is
white rather than transparent, whether the ZIP opens. So this test serves a
page under the STRICTEST Content-Security-Policy in the fleet (Whiteout's:
`script-src 'self'`, `img-src 'self' data:` with no blob:), draws charts with
the real master, calls the exports, and checks the files that come out, in
Chromium and in WebKit (Safari's engine, where export bugs have shown up first).

What would go red:
  * a PNG of the wrong size (viewBox x scale), or one from a chart in a hidden
    tab that comes out empty;
  * a transparent or blank PNG (corner pixel not opaque white; no chart ink);
  * a CSP violation (an export that needs blob: images or inline script);
  * a ZIP that Python's zipfile cannot read, with a bad CRC, a lost file, an
    exported .print-hide element, or a CSV without its BOM or with a live
    formula cell;
  * an empty archive that resolves instead of failing (Layoff's 22-byte ZIP);
  * a saved file name that is not the one asked for.

Needs Playwright with Chromium. On this Mac it lives in the browser venv
(~/.local/phronon-browser/venv, see server-ops/browser_submit_check.py); when
the interpreter running pytest lacks it, the probe is re-run under that venv.
Run directly for a readable report:
    ~/.local/phronon-browser/venv/bin/python tests/test_chart_export_browser.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import struct
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "svg-charts.js"
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"

# Whiteout's policy, the strictest of the nine: no inline script at all, and
# images from 'self' and data: only. An export that works here works in all.
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; frame-ancestors 'self'; form-action 'self'")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>export probe</title></head>
<body>
  <div id="board">
    <div id="rows" class="svg-chart"></div>
    <div id="rows-table"></div>
    <div class="tab-panel" hidden><div id="bars" class="svg-chart"></div></div>
    <div class="print-hide"><div id="skipped" class="svg-chart"></div></div>
  </div>
  <div id="empty"></div>
  <script src="/svg-charts.js"></script>
  <script src="/probe.js"></script>
</body></html>
"""

# The probe runs in the page; window.__probe resolves to a JSON-able report.
PROBE_JS = r"""
'use strict';
window.__violations = [];
document.addEventListener('securitypolicyviolation', function (e) {
  window.__violations.push(e.violatedDirective + ' ' + e.blockedURI);
});
var PC = window.PhrononCharts;
PC.drawRows(document.getElementById('rows'), [
  { label: 'Group A', sub: '4 people', best: -2, worst: -40, avg: -24, grp: -8 },
  { label: 'Gruppe Ü', sub: '5 people', best: -6, worst: -30, avg: -14, grp: -20 },
], { aria: 'Group scores ▲ closer ▼ further', verdictLabel: 'Discussion' });
PC.dataTable(document.getElementById('rows-table'), 'Data table',
  ['Group', 'Score', 'Note'],
  [['Group A', -8, '=HYPERLINK("x")'], ['Gruppe Ü', '−20', 'a, "quoted" note']]);
PC.drawBars(document.getElementById('bars'), [
  { label: '1', value: 3 }, { label: '2', value: 7 }, { label: '3', value: 5 },
], { aria: 'Answers per option', height: 300 });
PC.drawBars(document.getElementById('skipped'), [{ label: 'x', value: 1 }],
  { aria: 'not exported' });

function pixels(blob) {
  return createImageBitmap(blob).then(function (bmp) {
    var c = document.createElement('canvas');
    c.width = bmp.width; c.height = bmp.height;
    var ctx = c.getContext('2d');
    ctx.drawImage(bmp, 0, 0);
    var d = ctx.getImageData(0, 0, c.width, c.height).data;
    var ink = 0, blue = 0, total = c.width * c.height;
    for (var i = 0; i < d.length; i += 4) {
      if (d[i] < 200 || d[i + 1] < 200 || d[i + 2] < 200) ink++;
      // The engine's `better` blue, #2a78d6, within anti-aliasing distance.
      if (Math.abs(d[i] - 42) < 30 && Math.abs(d[i + 1] - 120) < 30 &&
          Math.abs(d[i + 2] - 214) < 30) blue++;
    }
    return { w: c.width, h: c.height, corner: [d[0], d[1], d[2], d[3]],
             inkShare: ink / total, bluePixels: blue };
  });
}
function b64(blob) {
  return blob.arrayBuffer().then(function (buf) {
    var bytes = new Uint8Array(buf), bin = '';
    for (var i = 0; i < bytes.length; i += 0x8000)
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(bin);
  });
}
function viewBox(id) {
  var b = document.querySelector('#' + id + ' svg').viewBox.baseVal;
  return [b.width, b.height];
}
function failure(p) {
  return p.then(function () { return 'resolved'; },
                function (e) { return 'rejected: ' + e.message; });
}

window.__probe = (async function () {
  var out = { dpr: window.devicePixelRatio, rowsBox: viewBox('rows'),
              barsBox: viewBox('bars') };
  var plain = await PC.chartPng(document.getElementById('rows'), { scale: 2 });
  out.plain = await pixels(plain);
  out.plain.type = plain.type;
  out.plainB64 = await b64(plain);
  var auto = await PC.chartPng(document.getElementById('rows'));
  out.auto = await pixels(auto);
  var hidden = await PC.chartPng(document.getElementById('bars'), { scale: 2 });
  out.hidden = await pixels(hidden);
  var titled = await PC.chartPng(document.getElementById('rows'),
    { scale: 2, title: 'Who moved closer?', subtitle: 'Session ABC, 12 October' });
  out.titled = await pixels(titled);
  out.csv = PC.tableCsv(document.getElementById('rows-table'));
  out.name = PC.exportName('Ränge: Übersicht / Straße');
  out.emptyZip = await failure(PC.exportChartsZip(document.getElementById('empty'),
                                                  { download: false }));
  out.badItem = await failure(PC.exportChartsZip(
    [{ name: 'ok', text: 'x' }, { name: 'broken', svg: document.getElementById('empty') }],
    { download: false }));
  var progress = [];
  var listZip = await PC.exportChartsZip([
    { name: 'a.txt', text: 'one' }, { name: 'a.txt', text: 'two' },
    { name: 'card.png', blob: function () { return Promise.resolve(plain); } },
  ], { download: false, onProgress: function (d, t) { progress.push(d + '/' + t); } });
  out.listZipB64 = await b64(listZip);
  out.progress = progress;
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


def _engines(p):
    """Chromium always; WebKit when it is installed (it is on this Mac)."""
    out = ["chromium"]
    try:
        b = p.webkit.launch()
        b.close()
        out.append("webkit")
    except Exception:  # noqa: BLE001 - WebKit absent is reported in the result, not fatal
        pass
    return out


def probe() -> dict:
    """Serve the page, run it in each engine, return everything checked."""
    from playwright.sync_api import sync_playwright

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    report: dict = {}
    try:
        with sync_playwright() as p:
            for name in _engines(p):
                browser = getattr(p, name).launch()
                try:
                    for dpr in (1, 3):
                        ctx = browser.new_context(device_scale_factor=dpr, accept_downloads=True)
                        page = ctx.new_page()
                        errors: list = []
                        page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                        page.goto(url)
                        res = page.evaluate("window.__probe")
                        res["pageErrors"] = errors
                        if dpr == 1:
                            with page.expect_download() as dl:
                                page.evaluate("PhrononCharts.exportChartPng("
                                              "document.getElementById('rows'),"
                                              "{filename: 'Ränge Übersicht'})")
                            res["pngDownloadName"] = dl.value.suggested_filename
                            with page.expect_download() as dl:
                                page.evaluate("PhrononCharts.exportChartPng("
                                              "document.getElementById('bars'))")
                            res["pngDefaultName"] = dl.value.suggested_filename
                            with page.expect_download() as dl:
                                page.evaluate("PhrononCharts.exportChartsZip("
                                              "document.getElementById('board'),"
                                              "{filename: 'session ABC'})")
                            res["zipDownloadName"] = dl.value.suggested_filename
                            res["zipB64"] = base64.b64encode(
                                Path(dl.value.path()).read_bytes()).decode()
                            res["violations"] = page.evaluate("window.__violations")
                        report[f"{name}@{dpr}x"] = res
                        ctx.close()
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


def _png_size(data: bytes) -> tuple:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def _check(report: dict) -> None:
    assert "chromium@1x" in report and "chromium@3x" in report, report.keys()
    for key, r in report.items():
        assert "error" not in r, (key, r.get("error"))
        assert r["pageErrors"] == [], (key, r["pageErrors"])
        assert r["violations"] == [], (key, r["violations"])
        vw, vh = r["rowsBox"]
        bw, bh = r["barsBox"]

        # The PNG: viewBox x scale, opaque white ground, the chart's ink on it.
        assert r["plain"]["type"] == "image/png", key
        assert (r["plain"]["w"], r["plain"]["h"]) == (round(vw * 2), round(vh * 2)), key
        assert _png_size(base64.b64decode(r["plainB64"])) == (round(vw * 2), round(vh * 2))
        assert r["plain"]["corner"] == [255, 255, 255, 255], (key, r["plain"]["corner"])
        assert r["plain"]["inkShare"] > 0.01, (key, "the PNG has no chart in it")
        assert r["plain"]["bluePixels"] > 50, (key, "the result marks did not paint")

        # Default scale: devicePixelRatio, never below 2.
        k = max(2, min(4, r["dpr"]))
        assert (r["auto"]["w"], r["auto"]["h"]) == (round(vw * k), round(vh * k)), key

        # A chart inside a hidden tab exports at full size, with its bars.
        assert (r["hidden"]["w"], r["hidden"]["h"]) == (round(bw * 2), round(bh * 2)), key
        assert r["hidden"]["corner"] == [255, 255, 255, 255], key
        assert r["hidden"]["bluePixels"] > 50 or r["hidden"]["inkShare"] > 0.02, key

        # The titled PNG: 32-unit margin round it and a header above the chart.
        assert r["titled"]["w"] == round((vw + 64) * 2), key
        assert r["titled"]["h"] > round((vh + 64) * 2), key
        assert r["titled"]["corner"] == [255, 255, 255, 255], key

        # The CSV: BOM, CRLF, quoting, formula cell neutralised, numbers kept.
        csv = r["csv"]
        assert csv.startswith("﻿Group,Score,Note\r\n"), key
        assert "Group A,-8,\"'=HYPERLINK(\"\"x\"\")\"\r\n" in csv, (key, csv)
        assert "Gruppe Ü,−20,\"a, \"\"quoted\"\" note\"\r\n" in csv, (key, csv)

        assert r["name"] == "Range-Ubersicht-Strasse", key

        # Failures fail: no empty archive, no partial archive.
        assert r["emptyZip"].startswith("rejected: there was nothing"), key
        assert r["badItem"].startswith("rejected: could not export broken"), key

        # A list of items: names kept, duplicates numbered, a lazy blob awaited.
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(r["listZipB64"])))
        assert z.testzip() is None, key
        assert z.namelist() == ["a.txt", "a-2.txt", "card.png"], (key, z.namelist())
        assert z.read("a-2.txt") == b"two"
        assert z.read("card.png") == base64.b64decode(r["plainB64"])
        assert r["progress"] == ["1/3", "2/3", "3/3"], key

        if key.endswith("@1x"):
            assert r["pngDownloadName"] == "Range-Ubersicht.png", key
            assert r["pngDefaultName"] == "answers-per-option.png", key
            assert r["zipDownloadName"] == "session-ABC.zip", key
            z = zipfile.ZipFile(io.BytesIO(base64.b64decode(r["zipB64"])))
            assert z.testzip() is None, key
            # Page order; the .print-hide chart left out; the hidden tab kept.
            assert z.namelist() == [
                "01_group-scores-closer-further.png",
                "02_data-table.csv",
                "03_answers-per-option.png",
            ], (key, z.namelist())
            for n in ("01_group-scores-closer-further.png", "03_answers-per-option.png"):
                w, h = _png_size(z.read(n))
                assert w >= 1800 and h > 100, (key, n, w, h)
            assert z.read("02_data-table.csv").decode("utf-8") == csv


def test_chart_exports_in_real_browsers():
    _check(_report())


if __name__ == "__main__":
    result = probe()
    if "--json" in sys.argv:
        print(json.dumps(result))
    else:
        _check(result)
        print("chart export probe: OK in", ", ".join(sorted(result)))
