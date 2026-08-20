"""Cache-busting query strings that come from the file, not from a person.

FL-037, 20 August 2026. Every tool pinned its CSS and JS by hand —
``/static/js/group-agreement.js?v=20260809a`` — so shipping a change meant
remembering to bump a string in a template. On 20 August a rewritten group
board was deployed while three browsers went on running the cached script from
eleven days earlier, and the board looked unfixed in all three. The deploy was
green, the file on the server was right, and only the person holding the stale
cache saw anything wrong.

    asset("/static/js/group-agreement.js")
    -> "/static/js/group-agreement.js?v=8f2c1a0b"

The digest is over the file's CONTENT, so an unchanged file keeps its URL (and
its cache) and a changed one gets a new URL the moment it is deployed. Nobody
has to remember anything, and nobody can forget.

Wiring, in each tool's app.py::

    from phronon_common.assets import asset_url
    templates.env.globals["asset"] = asset_url(BASE_DIR)

and in the template, ``href="{{ asset('/static/css/style.css') }}"``.

The result is cached per path and re-checked against the file's mtime and
size, so a production request does not hash a file on every render, and a
deploy that replaces a file is picked up without a restart — which matters,
because a static-only change may not restart the service at all.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

# path -> (mtime_ns, size, digest). Bounded by the number of static files a
# tool serves, which is dozens.
_CACHE: dict[str, tuple[int, int, str]] = {}


def _digest(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:8]


def asset_url(base_dir):
    """Return an ``asset(path)`` function rooted at this tool's directory.

    ``base_dir`` is the directory holding ``static/`` — the same one the app
    mounts. A path that does not resolve to a file inside it is returned
    unchanged: a missing asset is a broken link either way, and a stylesheet
    that 404s should not also take the page down.
    """
    root = Path(base_dir).resolve()

    def asset(path: str) -> str:
        rel = path.split("?", 1)[0].lstrip("/")
        try:
            file_path = (root / rel).resolve()
            # No traversal out of the tool: `asset('/static/../../.env')` must
            # not stat, hash or admit the existence of anything outside.
            file_path.relative_to(root)
            st = file_path.stat()
        except (OSError, ValueError):
            return path
        key = str(file_path)
        cached = _CACHE.get(key)
        if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
            return f"{path}?v={cached[2]}"
        digest = _digest(file_path)
        _CACHE[key] = (st.st_mtime_ns, st.st_size, digest)
        return f"{path}?v={digest}"

    return asset


def clear_cache() -> None:
    """Forget every digest. For tests; production never needs it, because the
    mtime/size check already notices a replaced file."""
    _CACHE.clear()
