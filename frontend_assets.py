"""Immutable stylesheet bundles: the application's half of the frontend-only
release path (TO DO FL-078). Pilot in Layoff on 4 October 2026, fleet-wide from
v1.74.0 at the owner's request, so no tool is the odd one out.

WHY: a change to a tool's own `backoffice.css` should reach production without
a full deploy (new environment, migrations, the whole server suite, a
restart). `server-ops/frontend_release.py` builds the enrolled files at an
exact commit into an immutable bundle, publishes it under

    /var/www/.phronon-frontend/<service>/bundles/<bundle-id>/<path under static/>

and switches `.../active.json` atomically (<service> = the tool's systemd
unit, `registry.ToolIdentity.service`, which is also the leaf of its server
path). This module is the application's half:

* `asset()` (the Jinja global) returns `/frontend/<bundle-id>/<path>` for an
  enrolled file and the usual `/static/<path>?v=<hash>` for everything else;
* one manifest snapshot per request (a context variable set by middleware),
  so a page never mixes two bundles, even if activation happens mid-render;
* the manifest is re-read when its file changes (one stat per request), so a
  new activation needs no restart;
* a malformed manifest, or a bundle missing a file, never yields a partial
  answer: the last good manifest stays in use, or, with none, every enrolled
  file is served the old way from the checkout;
* `/frontend/<bundle-id>/<path>` serves a bundle's file by its id, whatever is
  active now: old pages keep loading the bytes they were rendered with.

What may be enrolled is fixed by the tool's `frontend/contract.json`, which is
deployed normally. A tool without one is not enrolled, and nothing changes.

HOW A TOOL USES IT, in app.py, once, AFTER the `asset` global is set:

    from phronon_common import frontend_assets
    FRONTEND = frontend_assets.install(app, templates, BASE_DIR)

and in /health:  "frontend_bundle": frontend_assets.active_bundle(),

`install` loads the web framework lazily; importing this module does not
(tests/test_import_boundaries.py).
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("phronon.frontend")

SERVER_ROOT = Path("/var/www/.phronon-frontend")
BUNDLE_ID = re.compile(r"^[0-9a-f]{16}$")
MEDIA = {".css": "text/css; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".webp": "image/webp", ".woff": "font/woff", ".woff2": "font/woff2"}
#: Immutable URLs: the bytes behind one never change.
CACHE = "public, max-age=31536000, immutable"


def default_root(tool_key: str) -> Path:
    """Where the server keeps this tool's bundles and active.json."""
    from phronon_common.registry import TOOLS
    return SERVER_ROOT / TOOLS[tool_key].service


class Frontend:
    """One tool's enrolled files and its active bundle (one per process)."""

    def __init__(self, base_dir, root=None):
        self.base_dir = Path(base_dir)
        path = self.base_dir / "frontend" / "contract.json"
        self.contract = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        self.enrolled = tuple((self.contract or {}).get("assets", ()))
        self.tool = (self.contract or {}).get("tool")
        if self.contract is None:
            self.root = None
        else:
            self.root = Path(root or os.environ.get("FRONTEND_ROOT") or default_root(self.tool))
        self._snapshot: contextvars.ContextVar = contextvars.ContextVar(
            f"frontend_snapshot_{id(self)}", default=None)
        self._state = {"stamp": None, "good": None}     # last good manifest, keyed by the file's stat
        self.env = None                                 # the Jinja environment install() wrapped

    # ── the manifest ─────────────────────────────────────────────────────────
    def _valid(self, m) -> bool:
        if not isinstance(m, dict) or m.get("schema") != 1 or m.get("tool") != self.tool:
            return False
        if not BUNDLE_ID.match(str(m.get("bundle", ""))):
            return False
        files = m.get("files")
        if not isinstance(files, dict) or set(files) != set(self.enrolled):
            return False
        bundle = self.root / "bundles" / m["bundle"]
        return all((bundle / rel).is_file() for rel in files)

    def current(self):
        """The manifest for a new request: re-read when the file changed, the
        last good one if the new one is broken, None if there never was one."""
        if self.root is None:
            return None
        path = self.root / "active.json"
        try:
            st = path.stat()
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        except OSError:
            return self._state["good"]
        if stamp != self._state["stamp"]:
            self._state["stamp"] = stamp
            try:
                m = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                m = None
            if self._valid(m):
                self._state["good"] = m
            else:
                log.error("frontend manifest %s is invalid; keeping %s", path,
                          (self._state["good"] or {}).get("bundle", "the checkout's files"))
        return self._state["good"]

    def active_bundle(self):
        """The bundle a fresh page would use (for /health), or None."""
        return (self.current() or {}).get("bundle")

    # ── one request, one bundle ──────────────────────────────────────────────
    def begin_request(self):
        """Middleware: fix this request's manifest. Returns the token to reset."""
        return self._snapshot.set(self.current())

    def end_request(self, token) -> None:
        self._snapshot.reset(token)

    def wrap_asset(self, base_asset):
        """The `asset()` Jinja global: enrolled paths from the request's bundle."""
        def asset(path: str) -> str:
            rel = path.split("?", 1)[0]
            if rel.startswith("/static/"):
                rel = rel[len("/static/"):]
                m = self._snapshot.get()
                if m is not None and rel in m["files"]:
                    return f"/frontend/{m['bundle']}/{rel}"
            return base_asset(path)
        return asset

    # ── serving a bundle's file ──────────────────────────────────────────────
    def bundle_file(self, bundle: str, rel: str):
        """(path, media type) of a bundle's file, or None. No traversal, no
        symlinks, only the published media types."""
        if self.root is None or not BUNDLE_ID.match(bundle):
            return None
        parts = rel.split("/")
        if not rel or any(p in ("", ".", "..") or p.startswith(".") for p in parts):
            return None
        media = MEDIA.get(Path(rel).suffix.lower())
        if media is None:
            return None
        base = (self.root / "bundles" / bundle).resolve()
        p = base.joinpath(*parts)
        try:
            if p.is_symlink() or not p.is_file() or base not in p.resolve().parents:
                return None
        except OSError:
            return None
        return p, media


_installed: Frontend | None = None


def active_bundle():
    """For a tool's /health: the bundle a fresh page would use, or None
    (no contract, or nothing published yet)."""
    return _installed.active_bundle() if _installed is not None else None


def install(app, templates, base_dir, root=None) -> Frontend:
    """Wire the bundles into a FastAPI app: the `asset` global, the
    one-bundle-per-request middleware and the `/frontend/...` route. Call it
    once, at import, after `templates.env.globals["asset"]` is set. A tool
    without `frontend/contract.json` gets the route and the middleware, which
    then do nothing, and its asset() is unchanged."""
    global _installed
    from starlette.responses import FileResponse, PlainTextResponse

    if "asset" not in templates.env.globals:
        raise RuntimeError("frontend_assets.install: set templates.env.globals['asset'] first")
    fe = Frontend(base_dir, root)
    templates.env.globals["asset"] = fe.wrap_asset(templates.env.globals["asset"])
    fe.env = templates.env

    @app.middleware("http")
    async def _frontend_snapshot(request, call_next):
        token = fe.begin_request()
        try:
            return await call_next(request)
        finally:
            fe.end_request(token)

    async def frontend_bundle_file(bundle: str, path: str):
        """A file of an immutable bundle, by the bundle's id: the same bytes
        for as long as the URL exists. Public, like /static."""
        found = fe.bundle_file(bundle, path)
        if found is None:
            return PlainTextResponse("Not found", status_code=404)
        file_path, media = found
        return FileResponse(file_path, media_type=media, headers={"Cache-Control": CACHE})

    app.add_api_route("/frontend/{bundle}/{path:path}", frontend_bundle_file,
                      methods=["GET", "HEAD"], include_in_schema=False)
    _installed = fe
    return fe
