"""Every fetch() that POSTs must send the CSRF token where THIS tool reads it.

The original bug (10 August 2026): a fetch POST carried the token in a body the
tool's checker never read, so it 403'd silently. The scan below is the fleet's
answer, and it was copied into eight repositories rather than shared — nine
versions of one scanner, differing only in each tool's DECLARATION of where its
own check reads the token.

WHAT IS GENUINELY PER-TOOL, and therefore stays a parameter here:

  * `token_read_from` — which carriers this tool's CSRF check actually reads:
    "urlencoded", "multipart", "json", "header".
  * `accept_json_required` — true only where a CSRF failure would otherwise be
    HTML and the caller's response.json() would throw a parse error instead of
    showing the message. That is the shared middleware, which negotiates
    content. Tools that raise HTTPException get a JSON error body either way,
    so there it is good practice, not a defect, and is not enforced.
  * `csrf_scope_prefixes` — the path prefixes this tool's check covers; None
    means every path. A fetch POST outside it is not a CSRF question at all.
  * `source` — the code that DECIDES where the token may live, read back for
    the drift check. Two shapes, both deliberate:
      - tools with their own checker in app.py pass that file;
      - tools on `phronon_common.csrf` must resolve it BY IMPORT, not by path.
        The shared package lives in three places (a sibling folder on a laptop,
        /var/www/phronon_common on the server, site-packages in CI), and the
        first version of that check guessed paths, found none of the three in
        CI, and turned the gate red on all three shared-middleware tools.
        `shared_middleware_source()` below does the import.

Source-level: no database, no app import, so it can never skip. No pytest
import — see phronon_common/testing/__init__.py for why the wiring stays local.
"""
from __future__ import annotations

import re
from pathlib import Path

_POST_FETCH = re.compile(r"method:\s*['\"]POST['\"]")
# The first argument of fetch(, up to any ${...} interpolation — enough to tell
# which part of the site is being posted to.
_FETCH_URL = re.compile(r"fetch\(\s*[`'\"]([^`'\"$]*)")
# The options object sits just after fetch(; a body is sometimes built just
# above it. The window covers both, generously: a false failure here costs a
# minute, and a false pass cost an outage.
_WINDOW_BEFORE, _WINDOW_AFTER = 800, 500


def app_source(project_root: Path | str) -> str:
    """The tool's own app.py — for tools whose CSRF check lives there."""
    return (Path(project_root) / "app.py").read_text(encoding="utf-8", errors="ignore")


def shared_middleware_source() -> str:
    """`phronon_common.csrf`'s own source, resolved BY IMPORT.

    Never by path: see the module docstring. If the import fails the caller
    gets an empty string and the drift check fails loudly, which is correct —
    a tool that declares the shared middleware must be able to see it.
    """
    try:
        import inspect

        from phronon_common import csrf as _csrf
        return inspect.getsource(_csrf)
    except Exception:  # pragma: no cover - environment, not behaviour
        return ""


def scanned_files(project_root: Path | str):
    """Templates AND static JS.

    Whiteout is why this is not templates-only: its board and autosave POSTs
    live in static/js/rank.js and take the token from a <meta> tag, so a
    template-only scan reported "no fetch POSTs" for the tool that has the most
    interesting ones.
    """
    root = Path(project_root)
    yield from sorted((root / "templates").rglob("*.html"))
    js = root / "static" / "js"
    if js.is_dir():
        yield from sorted(js.rglob("*.js"))


def _in_csrf_scope(head: str, csrf_scope_prefixes) -> bool:
    if csrf_scope_prefixes is None:
        return True
    match = _FETCH_URL.search(head)
    if not match:
        return True          # URL built at runtime: check it rather than miss it
    return match.group(1).startswith(tuple(csrf_scope_prefixes))


def post_fetch_sites(project_root: Path | str, csrf_scope_prefixes=None):
    """(where, window) for every fetch() that posts, inside the CSRF scope."""
    root = Path(project_root)
    for path in scanned_files(root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"fetch\(", text):
            window = text[max(0, match.start() - _WINDOW_BEFORE):
                          match.start() + _WINDOW_AFTER]
            if not _POST_FETCH.search(window):
                continue
            if not _in_csrf_scope(text[match.start():match.start() + 200],
                                  csrf_scope_prefixes):
                continue
            line = text[:match.start()].count("\n") + 1
            yield f"{path.relative_to(root)}:{line}", window


def mechanisms_used(window: str) -> set:
    used = set()
    if "X-CSRF-Token" in window or "csrf-token" in window:
        used.add("header")
    if "URLSearchParams" in window:
        used.add("urlencoded")
    if "FormData" in window:
        used.add("multipart")
    if "JSON.stringify" in window and re.search(r"csrf", window, re.I):
        used.add("json")
    return used


# ── the four assertions ─────────────────────────────────────────────────────

def assert_declaration_matches_the_code(source: str, token_read_from) -> None:
    """A stale "the header works here" is what would send the next author down
    the 10 August path — in either direction."""
    assert source, "could not read this tool's CSRF implementation to check against"
    reads_header = "X-CSRF-Token" in source
    if "header" in token_read_from:
        assert reads_header, (
            "TOKEN_READ_FROM claims the X-CSRF-Token header is read, but the "
            "CSRF implementation never mentions it — every fetch relying on "
            "the header would 403")
    else:
        assert not reads_header, (
            "TOKEN_READ_FROM says the header is NOT read, but the CSRF "
            "implementation does read it — update the declaration, and the "
            "templates may now rely on it")


def assert_every_post_fetch_sends_the_token(project_root, token_read_from,
                                            csrf_scope_prefixes=None) -> None:
    offenders = []
    for where, window in post_fetch_sites(project_root, csrf_scope_prefixes):
        used = mechanisms_used(window)
        if not (used & set(token_read_from)):
            offenders.append(f"{where} (sends via {sorted(used) or 'nothing'}; "
                             f"this tool reads {sorted(token_read_from)})")
    assert not offenders, (
        "fetch() POST(s) send the CSRF token only by a route this tool's check "
        "does not read — every one of them 403s silently:\n  "
        + "\n  ".join(offenders))


def assert_no_post_fetch_relies_on_formdata_alone(project_root,
                                                  csrf_scope_prefixes=None) -> None:
    """Fleet standard, stricter than some tools would need: the body is
    URLSearchParams. FormData is multipart, which the shared middleware cannot
    read at all, so a FormData here is one refactor away from the original bug
    even in a tool whose own checker copes with it today."""
    offenders = [where for where, window in post_fetch_sites(project_root, csrf_scope_prefixes)
                 if mechanisms_used(window) == {"multipart"}]
    assert not offenders, (
        "fetch() POST(s) carry the token only in a FormData (multipart) body: "
        + ", ".join(offenders))


def assert_every_post_fetch_names_json_in_accept(project_root, accept_json_required,
                                                 csrf_scope_prefixes=None) -> None:
    if not accept_json_required:
        # Not a defect in this tool: its CSRF failure is an HTTPException, so
        # the body is JSON either way and response.json() succeeds. Deliberately
        # a plain return, NOT a skip — the fleet conftests fail a run on an
        # unregistered skip, and rightly: a skip and a pass look identical.
        return
    offenders = [where for where, window in post_fetch_sites(project_root, csrf_scope_prefixes)
                 if "'Accept': 'application/json'" not in window
                 and '"Accept": "application/json"' not in window]
    assert not offenders, (
        "fetch() POST(s) without Accept: application/json — a CSRF failure will "
        "arrive as HTML and response.json() will throw a parse error instead of "
        "showing it: " + ", ".join(offenders))
