"""passkeys.js sign-in, run in real browsers (27 October 2026).

The owner saw Safari take a long time to show the fingerprint prompt after a
click on "Sign in with a passkey". The page asked the server for a challenge
first and only then asked the browser, outside the click. Since 1.97.0 the
page keeps the latest challenge it fetched (the autofill one, or in the
passkey-first view one fetched for the button) and asks the browser inside
the click. This drives the real master in Chromium and in WebKit (Safari's
engine) under a strict Content-Security-Policy, with a stand-in for the
browser's passkey dialog that records each call, and checks four cases:

  * the normal page: the autofill request waits; a click cancels it and asks
    the browser at once, inside the click, with that same challenge, and no
    request to the server in between;
  * the passkey-first page (the browser remembers a passkey sign-in): a
    challenge is fetched as the page opens and the click uses it the same way;
  * no ready challenge (the server refused the early request): the click
    fetches one and still signs in, as before 1.97.0;
  * a cancelled prompt: the next click uses a NEW challenge, never the spent
    one.

What would go red: a click that waits for the server before asking the
browser, a modal request started while the autofill one is still open, a
challenge used twice, or a sign-in that no longer reaches the server.

Needs Playwright with Chromium and WebKit; see test_country_other_browser.py
for how the browser venv is found. Run directly for the raw report:
    ~/.local/phronon-browser/venv/bin/python tests/test_passkeys_browser.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

SCRIPT = Path(__file__).resolve().parent.parent / "passkeys.js"
BROWSER_VENV_PY = Path.home() / ".local/phronon-browser/venv/bin/python"
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'"


def _page(autofill_url: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>passkey probe</title></head>
<body>
  <div data-passkey-login hidden data-options-url="/options" data-submit-url="/submit"
       data-autofill-url="{autofill_url}" data-csrf="token-1">
    <button type="button" id="start" data-passkey-start>Sign in with a passkey</button>
    <p id="status" data-passkey-status role="status"></p>
    <p data-passkey-or>or</p>
    <p data-passkey-use-password hidden><a href="#">Use e-mail and password instead</a></p>
  </div>
  <form id="login" method="post" action="/password">
    <input name="email" autocomplete="username webauthn">
    <input name="password" type="password">
    <button type="submit">Log in</button>
  </form>
  <script src="/passkeys.js"></script>
</body></html>
"""


# The stand-in for the browser's passkey dialog, installed before the page's
# scripts run. A conditional request waits until it is aborted; a modal one
# answers with a stand-in credential naming the challenge it was given, or is
# cancelled once when the page sets window.__cancelNext.
STAND_IN = r"""
(() => {
  const log = window.__log = [];
  let inClick = false;
  window.addEventListener('click', () => { inClick = true; }, true);
  window.addEventListener('click', () => { inClick = false; }, false);
  const realFetch = window.fetch.bind(window);
  window.fetch = (url, opts) => { log.push({t: 'fetch', url: String(url)}); return realFetch(url, opts); };
  const b64 = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  if (!window.PublicKeyCredential) window.PublicKeyCredential = function () {};
  PublicKeyCredential.isConditionalMediationAvailable = () => Promise.resolve(true);
  if (window.__marker) localStorage.setItem('phronon-passkey-signin', '1');
  // On the prototype: WebKit can replace navigator.credentials' wrapper after
  // a garbage collection, and a property set on the old one is gone with it.
  CredentialsContainer.prototype.get = (opts) => {
    const challenge = b64(opts.publicKey.challenge);
    const mediation = opts.mediation || 'modal';
    log.push({t: 'get', mediation, inClick, challenge,
              activation: navigator.userActivation ? navigator.userActivation.isActive : null});
    if (mediation === 'conditional') {
      return new Promise((_, reject) => opts.signal.addEventListener('abort', () => {
        log.push({t: 'abort', challenge});
        reject(new DOMException('aborted', 'AbortError'));
      }));
    }
    if (window.__cancelNext) {
      window.__cancelNext = false;
      return Promise.reject(new DOMException('cancelled', 'NotAllowedError'));
    }
    return Promise.resolve({toJSON: () => ({id: 'stand-in', type: 'public-key', challenge})});
  };
})();
"""


class _Server(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.issued: list = []      # every challenge handed out, in order
        self.signed_in: list = []   # the challenge each submitted credential carried
        self.lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    server: _Server

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (http.server's name)
        if self.path == "/passkeys.js":
            self._send(200, SCRIPT.read_bytes(), "text/javascript")
        elif self.path == "/refused":
            self._send(200, _page("/autofill-refused").encode(), "text/html; charset=utf-8")
        else:
            self._send(200, _page("/autofill").encode(), "text/html; charset=utf-8")

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        form = self.rfile.read(length).decode()
        if self.path == "/autofill-refused":
            self._send(429, b'{"error": "Too many requests."}', "application/json")
            return
        if self.path in ("/options", "/autofill"):
            with self.server.lock:
                n = len(self.server.issued) + 1
                # 32 bytes, as the server sends; base64url of "challenge-<n>" padded
                challenge = f"challenge-{n:02d}".encode().ljust(32, b".")
                text = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
                self.server.issued.append(text)
            body = {"challenge": text, "timeout": 60000, "rpId": "127.0.0.1",
                    "allowCredentials": [], "userVerification": "required"}
            self._send(200, json.dumps(body).encode(), "application/json")
            return
        if self.path == "/submit":
            cred = json.loads(parse_qs(form)["credential"][0])
            with self.server.lock:
                self.server.signed_in.append(cred["challenge"])
            # {"ok": true} and no redirect: the page stays, so its log can be read
            self._send(200, b'{"ok": true}', "application/json")
            return
        self._send(404, b"{}", "application/json")

    def log_message(self, *args):
        pass


def _until(page, js: str) -> None:
    """Poll a page condition from here: Playwright's wait_for_function
    evaluates a string inside the page, which the page's CSP refuses."""
    _wait(page, lambda: page.evaluate(js))


def _wait(page, condition, *, soft: bool = False) -> None:
    """Poll a condition while the page keeps running. `soft`: give up quietly
    and let the assertions say what is missing."""
    for _ in range(250):
        if condition():
            return
        page.wait_for_timeout(20)
    if not soft:
        raise AssertionError("timed out")


def _case(browser, base: str, path: str, *, server: _Server, marker: bool = False,
          cancel_first: bool = False) -> dict:
    context = browser.new_context()
    context.add_init_script(("window.__marker = true;" if marker else "") + STAND_IN)
    page = context.new_page()
    errors: list = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error"
            and "429" not in m.text else None)    # the refused case's own 429s
    first_issue, first_sign_in = len(server.issued), len(server.signed_in)
    page.goto(base + path)
    # The early request: the autofill one waits as a conditional request; the
    # passkey-first one only fetches; the refused one gets a 429.
    if marker:
        _wait(page, lambda: len(server.issued) > first_issue, soft=True)
    elif path == "/refused":
        _until(page, "window.__log.some(e => e.t === 'fetch')")
        page.wait_for_timeout(300)
    else:
        _until(page, "window.__log.some(e => e.t === 'get')")
    page.wait_for_timeout(100)
    cancelled: list = []
    if cancel_first:
        page.evaluate("window.__cancelNext = true")
        mark = page.evaluate("window.__log.length")
        page.click("#start")
        _until(page, "document.getElementById('status').textContent.includes('Cancelled')")
        _until(page, f"window.__log.slice({mark}).some(e => e.t === 'get' && "
                     "e.mediation === 'conditional')")
        cancelled = page.evaluate(f"window.__log.slice({mark})")
    mark = page.evaluate("window.__log.length")
    page.click("#start")
    _until(page, f"window.__log.slice({mark}).some(e => e.t === 'fetch' && "
                 "e.url.endsWith('/submit'))")
    _wait(page, lambda: len(server.signed_in) > first_sign_in)
    result = {
        "before_click": page.evaluate(f"window.__log.slice(0, {mark})"),
        "after_click": page.evaluate(f"window.__log.slice({mark})"),
        "cancelled": cancelled,
        "issued": server.issued[first_issue:],
        "signed_in": server.signed_in[first_sign_in:],
        "errors": errors,
    }
    context.close()
    return result


def run_probe() -> dict:
    """Drive both browsers; return {browser: {case: result}}."""
    from playwright.sync_api import sync_playwright

    server = _Server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    report: dict = {}
    try:
        with sync_playwright() as pw:
            for engine in (pw.chromium, pw.webkit):
                browser = engine.launch()
                report[engine.name] = {
                    "autofill": _case(browser, base, "/login", server=server),
                    "passkey_first": _case(browser, base, "/login", marker=True, server=server),
                    "refused": _case(browser, base, "/refused", server=server),
                    "cancelled": _case(browser, base, "/login", cancel_first=True, server=server),
                }
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


def _modal(entries: list) -> tuple[int, dict]:
    found = [(i, e) for i, e in enumerate(entries) if e["t"] == "get" and e["mediation"] == "modal"]
    assert len(found) == 1, f"expected one modal request, got {entries}"
    return found[0]


def _asked_at_once(browser: str, case: str, got: dict) -> None:
    """The click asked the browser inside the click, with no server request
    first, using the latest challenge the page had, and that challenge signed in."""
    after = got["after_click"]
    i, modal = _modal(after)
    assert modal["inClick"], f"{browser}, {case}: the browser was asked after the click: {after}"
    assert not any(e["t"] == "fetch" for e in after[:i]), (
        f"{browser}, {case}: a server request came between the click and the prompt: {after}")
    assert modal["challenge"] == got["issued"][-1], (
        f"{browser}, {case}: not the latest challenge: {modal} vs {got['issued']}")
    assert got["signed_in"] == [modal["challenge"]], f"{browser}, {case}: {got['signed_in']}"


def test_a_click_asks_the_browser_at_once_in_both_browsers():
    report = _report()
    assert set(report) == {"chromium", "webkit"}
    for browser, cases in report.items():
        for case, got in cases.items():
            assert got["errors"] == [], f"{browser}, {case}: {got['errors']}"

        # The normal page: the autofill request is cancelled first, then the
        # same challenge goes to the modal request.
        got = cases["autofill"]
        _asked_at_once(browser, "autofill", got)
        after = got["after_click"]
        i, modal = _modal(after)
        aborts = [j for j, e in enumerate(after) if e["t"] == "abort"]
        assert aborts and aborts[0] < i, (
            f"{browser}: the modal request started while the autofill one was open: {after}")
        assert after[aborts[0]]["challenge"] == modal["challenge"]

        # The passkey-first page: one early challenge, no autofill request.
        got = cases["passkey_first"]
        assert not any(e["t"] == "get" for e in got["before_click"]), got["before_click"]
        assert len(got["issued"]) == 1, got["issued"]
        _asked_at_once(browser, "passkey_first", got)

        # No ready challenge: the click fetches one, then asks; still signs in.
        got = cases["refused"]
        after = got["after_click"]
        i, modal = _modal(after)
        assert any(e["t"] == "fetch" and e["url"].endswith("/options") for e in after[:i]), after
        assert got["signed_in"] == [modal["challenge"]] == got["issued"][-1:], got

        # A cancelled prompt spends its challenge: the retry uses the fresh one.
        got = cases["cancelled"]
        spent = _modal(got["cancelled"])[1]["challenge"]
        _asked_at_once(browser, "cancelled", got)
        assert _modal(got["after_click"])[1]["challenge"] != spent


if __name__ == "__main__":
    sys.stdout.write(json.dumps(run_probe()))
