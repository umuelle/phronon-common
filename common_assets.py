"""Shared styles and scripts served from the release a tool runs (TO DO FL-069).

Pilot in Peak Season, owner's go of 14 November 2026. Every other tool copies
the masters it uses into its own static/ (shared_assets.py,
server-ops/sync_shared_assets.py); a change to a master is then a release and a
deploy of every tool that carries the file. A tool whose ops/tool.json says

    "operations": {"shared_assets": [...], "shared_assets_served": "central"}

carries no copies, and its app names the same list to `install` (the
application never reads ops/: release_plan.py counts that folder as no
production input; the tool's own test requires the two lists to agree). Its
pages link each listed master at

    /common/<release>/<master>        e.g. /common/v1.106.0/backoffice-core.css

and its own app answers from the release folder the process loaded. A change
to a master reaches the tool with the release's refresh.

What keeps it safe:

* same site: the tool's own app serves the file on the tool's own address, so
  the security policy ('self') and nginx stay as they are (nginx hands every
  path outside /static/ to the app);
* same order: templates keep their links; only the address `asset()` returns
  changes, so stylesheet order and every page's markup stay the same;
* immutable: the address carries the release name and a release folder is
  never changed after publishing, so browsers may keep the file for a year; a
  page rendered before a refresh keeps loading the bytes it was rendered with,
  because older release folders stay beside the active one;
* one release per page: the scripts that speak to the server (passkeys.js,
  recovery-codes.js) come from the release whose code rendered the page.

Only listed masters are served, by name: no path from the request reaches the
file system. Outside the server's release layout (a checkout, a wheel) only
the process's own release is answered.

HOW A TOOL USES IT, in app.py, once, after `templates.env.globals["asset"]`
is set:

    from phronon_common import common_assets
    common_assets.install(app, templates, SHARED_ASSETS_FROM_RELEASE)

`install` loads the web framework lazily; importing this module does not.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

from phronon_common import shared_assets

PREFIX = "/common"
CENTRAL = "central"
#: A release folder never changes, so neither does the file at its address.
CACHE = "public, max-age=31536000, immutable"
RELEASES_DIR_NAME = ".phronon_common-releases"
_RELEASE = re.compile(r"^v\d+\.\d+\.\d+$")
_MEDIA = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}


def release_name(masters: Optional[Path] = None) -> str:
    """The release this process loaded: the tag in the release folder's
    `.release` file, or v<version> in a checkout or a wheel."""
    folder = Path(masters or shared_assets.MASTERS)
    try:
        tag = (folder / ".release").read_text(encoding="utf-8").split()[0]
        if _RELEASE.match(tag):
            return tag
    except (OSError, IndexError):
        pass
    from phronon_common import __version__
    return f"v{__version__}"


class CommonAssets:
    def __init__(self, served: list[str], masters: Optional[Path] = None):
        self.masters = Path(masters or shared_assets.MASTERS).resolve()
        self.release = release_name(self.masters)
        self.served = set(served)
        #: "/static/js/passkeys.js" -> "passkeys.js"
        self.by_copy_path = {"/" + shared_assets.ASSETS[a]: a for a in served}

    def url(self, master: str) -> str:
        return f"{PREFIX}/{self.release}/{master}"

    def wrap_asset(self, asset: Callable[[str], str]) -> Callable[[str], str]:
        """asset() as before, except that a listed copy's address becomes the
        master's address in this release."""
        def central_asset(path: str) -> str:
            master = self.by_copy_path.get(path.split("?", 1)[0])
            return self.url(master) if master else asset(path)
        return central_asset

    def file_for(self, release: str, master: str) -> Optional[Path]:
        """The file for /common/<release>/<master>, or None. The release this
        process loaded, or (on the server) an older or newer published one
        beside it, for pages rendered by another worker."""
        if master not in self.served or not _RELEASE.match(release):
            return None
        if release == self.release:
            folder = self.masters
        elif self.masters.parent.name == RELEASES_DIR_NAME:
            folder = self.masters.parent / release
        else:
            return None
        f = folder / master
        return f if f.is_file() else None


def install(app: Any, templates: Any, served: list[str]) -> CommonAssets:
    """Serve the listed masters from the release, and link them there."""
    from starlette.responses import FileResponse, PlainTextResponse, Response

    unknown = [a for a in served if a not in shared_assets.ASSETS]
    if not served or unknown:
        raise RuntimeError(f"common_assets.install: needs a list of known masters (unknown: {unknown})")
    if "asset" not in templates.env.globals:
        raise RuntimeError("common_assets.install: set templates.env.globals['asset'] first")
    ca = CommonAssets(served)
    templates.env.globals["asset"] = ca.wrap_asset(templates.env.globals["asset"])

    async def common_file(release: str, master: str) -> Response:
        """A shared master as published in a release. Public, like /static."""
        f = ca.file_for(release, master)
        if f is None:
            return PlainTextResponse("Not found", status_code=404)
        return FileResponse(f, media_type=_MEDIA.get(f.suffix, "application/octet-stream"),
                            headers={"Cache-Control": CACHE})

    # response_model=None: what FastAPI derived from the unannotated function
    # before; a Response annotation would otherwise ask it for a model.
    app.add_api_route(PREFIX + "/{release}/{master}", common_file,
                      methods=["GET", "HEAD"], include_in_schema=False, response_model=None)
    return ca
