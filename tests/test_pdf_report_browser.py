"""The fleet's PDF builder, run in real browsers (TO DO FL-098, 26 October 2026).

pdf-report.js is the machinery under three reports (Layoff, Whiteout, Polarity
Profiler). What it does can only be judged in a browser with jsPDF loaded:
which characters reach the PDF, where the cursor goes, when a page starts, what
is skipped rather than allowed to break the document. So this serves a page
under the strictest Content-Security-Policy in the fleet (Whiteout's: no
inline script, images from 'self' and data: only), builds a report with the
real master and the tools' own jsPDF, and checks what came out, in Chromium
and in WebKit.

What would go red:
  * a character outside what jsPDF's fonts can print reaching doc.text (it
    prints a wrong glyph and mismeasures the line), or a WinAnsi mark (a dash,
    a curly quote) being thrown away although the font has it;
  * a paragraph that runs past the bottom limit instead of starting a page;
  * a chart in a hidden tab coming out empty, or a broken chart, an empty
    canvas or a missing html2canvas costing the whole document;
  * a table cell cut to one line, or a table without a <thead> failing;
  * page numbers on the wrong pages; hidden panels left open afterwards;
  * a CSP violation, or output that is not a PDF.

jsPDF comes from a tool's static/vendor/ beside this package (the matrix and
the workspace always have one); without one the test skips and says so.
Needs Playwright: on this Mac the browser venv of
server-ops/browser_submit_check.py, re-run under it when pytest's interpreter
lacks it. Run directly for a readable report:
    ~/.local/phronon-browser/venv/bin/python tests/test_pdf_report_browser.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
BUILDER = PACKAGE / "pdf-report.js"
JSPDF_NAME = "jspdf-2.5.1.umd.min.js"
JSPDF_CANDIDATES = [PACKAGE.parent / tool / "static" / "vendor" / JSPDF_NAME
                    for tool in ("Whiteout", "Layoff-Exercise", "polarity-profiler")]
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "font-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; frame-ancestors 'self'; form-action 'self'")

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>pdf probe</title></head>
<body>
  <div class="tab-panel" id="shown"><svg id="chart" viewBox="0 0 400 200">
    <rect x="0" y="0" width="400" height="200" fill="#ffffff"/>
    <rect x="20" y="20" width="300" height="60" fill="#2e78d2"/>
    <text x="20" y="150" font-size="20">Group A − 12</text></svg></div>
  <div class="tab-panel" id="away" hidden><svg id="hidden-chart" viewBox="0 0 300 300">
    <circle cx="150" cy="150" r="120" fill="#d14836"/></svg></div>
  <div class="tab-panel" id="styled" style="display:none"></div>
  <table id="t">
    <thead><tr><th>Group</th><th>Score</th><th>Note</th></tr></thead>
    <tbody>
      <tr><td>A</td><td>−32</td><td>20 short of its best member, which the second round closed almost entirely, and the third round then opened again</td></tr>
      <tr><td>B ▲</td><td>▼ −5</td><td>✓ surfaced</td></tr>
    </tbody>
  </table>
  <table id="headless"><tbody><tr><td>x</td><td>y</td></tr></tbody></table>
  <table id="empty"><thead><tr><th>Nothing</th></tr></thead><tbody></tbody></table>
  <script src="/jspdf.js"></script>
  <script src="/pdf-report.js"></script>
  <script src="/probe.js"></script>
</body></html>
"""

PROBE_JS = r"""
'use strict';
window.__violations = [];
document.addEventListener('securitypolicyviolation', function (e) {
  window.__violations.push(e.violatedDirective + ' ' + e.blockedURI);
});
window.__probe = (async function () {
  var P = window.PhrononPdf, out = {};
  out.ready = P.ready();
  out.safe = P.safe('−32 ▲ 3, ▼ −5, ▲ +2 ≥ 70 ≤ 9 → ↔ ' +
                    '✓ ○ ⚠ risk Δ ─ “q” ‘s’ – — ' +
                    '… • € üß x 😀 中');

  // The panels: shown both ways a tool hides one, then put back.
  var restore = P.revealPanels('.tab-panel');
  out.revealed = [document.getElementById('away').hidden,
                  document.getElementById('styled').style.display];
  restore();
  out.restored = [document.getElementById('away').hidden,
                  document.getElementById('styled').style.display];

  var r = P.report({ orientation: 'portrait', margin: 14, bottom: 18 });
  out.page = [r.W, r.H, r.usable];
  // Every string doc.text is handed, to check none escaped safe().
  var seen = [];
  var realText = r.doc.text.bind(r.doc);
  r.doc.text = function (t) {
    (Array.isArray(t) ? t : [t]).forEach(function (s) { seen.push(String(s)); });
    return realText.apply(null, arguments);
  };

  out.textH = r.text('Polarity ↔ profile', 14, 20, { size: 10 });
  out.wrapH = r.text('one two three four five six seven eight nine ten', 14, 30,
                     { size: 10, maxW: 30 });

  r.y = 270;
  var long = new Array(40).join('A long sentence that keeps going. ');
  out.writeLines = r.write(long, { size: 9.5, lineH: 4.4, room: 6, after: 2 });
  out.afterWrite = { y: r.y, pages: r.doc.getNumberOfPages() };

  r.page();
  out.svgShown = await r.svg(document.getElementById('chart'), { after: 5 });
  out.yAfterSvg = r.y;
  out.svgHidden = await r.svg(document.getElementById('hidden-chart'), { w: 60 });
  out.yAfterHidden = r.y;
  var broken = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  out.svgBroken = await r.svg(broken);
  var blank = document.createElement('canvas');
  blank.width = 0; blank.height = 0;
  out.imageEmpty = r.image({ canvas: blank, width: 10, height: 10 });
  out.domWithoutLibrary = await r.dom(document.body);

  r.page();
  out.table = r.table(document.getElementById('t'));
  out.headless = r.table(document.getElementById('headless'));
  out.emptyTable = r.table(document.getElementById('empty'));

  var numbered = [];
  r.eachPage(function (doc, p, n) { numbered.push(p + '/' + n); }, { from: 2 });
  out.numbered = numbered;
  var allButLast = [];
  r.eachPage(function (doc, p) { allButLast.push(p); }, { from: 2, to: -1 });
  out.allButLast = allButLast;

  out.pages = r.doc.getNumberOfPages();
  out.seen = seen;
  var bytes = r.doc.output();
  out.head = bytes.slice(0, 5);
  out.violations = window.__violations;
  return out;
})().catch(function (e) { return { error: String(e && e.stack || e) }; });
"""


def _jspdf() -> Path | None:
    return next((p for p in JSPDF_CANDIDATES if p.exists()), None)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (http.server's name)
        files = {
            "/": (PAGE.encode(), "text/html; charset=utf-8"),
            "/jspdf.js": (_jspdf().read_bytes(), "text/javascript; charset=utf-8"),
            "/pdf-report.js": (BUILDER.read_bytes(), "text/javascript; charset=utf-8"),
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
                except Exception:  # noqa: BLE001 - WebKit absent is reported, not fatal
                    continue
                try:
                    page = browser.new_page()
                    errors: list = []
                    page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
                    page.goto(url)
                    res = page.evaluate("window.__probe")
                    res["pageErrors"] = errors
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
    import pytest
    if _jspdf() is None:
        pytest.skip("no jsPDF beside the package (a tool's static/vendor/ is needed)")
    if _have_playwright():
        return probe()
    if not BROWSER_VENV_PY.exists():
        pytest.skip("playwright is not installed (browser venv: "
                    "server-ops/browser_submit_check.py has the two install lines)")
    run = subprocess.run([str(BROWSER_VENV_PY), __file__, "--json"],
                         capture_output=True, text=True, timeout=240,
                         env={**os.environ, "PYTHONPATH": ""})
    assert run.returncode == 0, run.stderr[-3000:]
    return json.loads(run.stdout)


# "▼ −5": the number carries its own sign, so the arrow is decoration and goes.
SAFE = ("-32 + 3, -5, +2 >= 70 <= 9 -> <-> • o ! risk Delta - “q” ‘s’ "
        "– — … • € üß x  ")
ALLOWED = set(chr(c) for c in range(0x100)) | set(
    "€‚ƒ„…†‡ˆ‰Š‹ŒŽ"
    "‘’“”•–—˜™š›œžŸ")


def _check(report: dict) -> None:
    assert "chromium" in report, report.keys()
    for key, r in report.items():
        assert "error" not in r, (key, r.get("error"))
        assert r["pageErrors"] == [] and r["violations"] == [], (key, r["pageErrors"], r["violations"])
        assert r["ready"] is True and r["head"] == "%PDF-", key

        # Characters: meaning kept as ASCII, WinAnsi marks kept, the rest gone.
        assert r["safe"] == SAFE, (key, r["safe"])
        bad = sorted({ch for s in r["seen"] for ch in s if ch not in ALLOWED})
        assert not bad, (key, "reached doc.text unfiltered", bad)
        assert "Polarity <-> profile" in r["seen"], key

        assert r["revealed"] == [False, "block"], key
        assert r["restored"] == [True, "none"], key

        assert r["page"] == [210, 297, 182], key
        assert abs(r["textH"] - 4.2) < 1e-9, key
        assert r["wrapH"] > 2 * 4.2, (key, "maxW did not wrap")

        # The paragraph started at 270 mm with 18 mm kept free: it went on to
        # page 2 and every line stayed above the limit.
        assert r["writeLines"] > 10 and r["afterWrite"]["pages"] >= 2, key
        assert r["afterWrite"]["y"] <= 297 - 18 + 4.4 + 2, key

        # Charts: the shown one across the usable width, the hidden-tab one at
        # its asked width; failures skipped, nothing thrown.
        assert r["svgShown"] is True and abs(r["yAfterSvg"] - (14 + 182 / 2 + 5)) < 1e-6, key
        assert r["svgHidden"] is True and abs(r["yAfterHidden"] - (r["yAfterSvg"] + 60)) < 1e-6, key
        assert r["svgBroken"] is False and r["imageEmpty"] is False, key
        assert r["domWithoutLibrary"] is False, key

        # Tables: the long cell wrapped to two lines and cut with '..'; the
        # arrows made safe; a table without <thead> laid out; an empty one skipped.
        assert r["table"] is True and r["headless"] is True and r["emptyTable"] is False, key
        cells = [s for s in r["seen"] if s.startswith("20 short") or s.endswith("..")]
        assert cells and any(s.endswith("..") for s in cells), (key, cells)
        assert "-32" in r["seen"] and "-5" in r["seen"], (key, r["seen"][-12:])
        assert any(s.startswith("B +") for s in r["seen"]), (key, r["seen"][-12:])

        n = r["pages"]
        assert r["numbered"] == [f"{p}/{n}" for p in range(2, n + 1)], key
        assert r["allButLast"] == list(range(2, n)), key


def test_the_pdf_builder_in_real_browsers():
    _check(_report())


if __name__ == "__main__":
    result = probe()
    if "--json" in sys.argv:
        print(json.dumps(result))
    else:
        _check(result)
        print("pdf builder probe: OK in", ", ".join(sorted(result)))
