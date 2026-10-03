"""Shared legal pages for the Phronon fleet — one router, nine tools.

Blueprint: phronon-legal-blueprint.md (rev. 2), Part 2. Canonical text lives
once here (legal_templates/ + legal_conf.py); every app mounts the router and
renders SERVER-SIDE FROM ITS OWN ORIGIN — never cross-domain, never via
JavaScript (Part 2.1: an Impressum that depends on another domain or a script
fails "ständig verfügbar" by construction).

Usage in a tool's app.py, replacing its hand-rolled legal routes:

    from phronon_common.legal import build_legal_router
    from phronon_common.legal_content import load_legal_config
    LEGAL = load_legal_config("whiteout", BASE_DIR / "legal_content" / "notice.json")
    app.include_router(build_legal_router("whiteout", config=LEGAL))

Since 4 October 2026 each tool passes its OWN content (legal_content.py says
why). Without `config=` the router still reads the frozen entry in
legal_conf.TOOLS: that is how tools not yet migrated, and earlier tool
versions a rollback may restore, keep working with this package.

Route map (Part 2.3):
    /impressum      German § 5 DDG page, lang="de". Canonical. Never a redirect.
    /legal-notice   English mirror of the operator data.
    /privacy        Full Art. 13 notice (English).
    /cookies        Cookie notice (English).
    /terms          Terms of use.
    /legal          Thin index.
    /imprint        301 -> /legal (handed out historically; must never 404).
    /de/privacy,    German notice/cookie pages — only on tools whose UI
    /de/cookies     serves German (legal_conf languages).

/accessibility is NOT here: each tool keeps its own statement (they were
rebuilt for the WCAG 2.2 baseline and carry per-tool known-gap lists).
"""
from __future__ import annotations

from pathlib import Path

import jinja2
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from .legal_conf import get_tool

_TEMPLATES = Path(__file__).resolve().parent / "legal_templates"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(_TEMPLATES)),
    autoescape=True,
    undefined=jinja2.StrictUndefined,  # a missing config field must 500 in tests, not render blank
)

_TITLES = {
    "impressum":    {"de": "Impressum"},
    "legal_notice": {"en": "Legal Notice"},
    "privacy":      {"en": "Privacy Policy", "de": "Datenschutzerklärung"},
    "cookies":      {"en": "Cookies", "de": "Cookies"},
    "terms":        {"en": "Terms of Use"},
    "index":        {"en": "Legal information"},
}


def render_legal(tool_key: str, doc: str, lang: str = "en", config: dict | None = None) -> str:
    """Render one legal document to HTML. Exposed for tests.

    `config`: the tool's own content (legal_content.load_legal_config). Without
    it, the frozen legacy entry for `tool_key` (unmigrated tools)."""
    if config is not None and config.get("key") != tool_key:
        raise ValueError(f"legal config for {config.get('key')!r} passed to render {tool_key!r}")
    cfg = config if config is not None else get_tool(tool_key)
    template = _env.get_template(f"{doc}.html")
    return template.render(
        cfg=cfg,
        lang=lang,
        doc_title=_TITLES[doc].get(lang) or next(iter(_TITLES[doc].values())),
        L=lambda prose: prose.get(lang) or prose["en"],
    )


def build_legal_router(tool_key: str, config: dict | None = None) -> APIRouter:
    """The legal routes. `config`: the tool's own content, loaded once at
    startup; every page renders from that one snapshot, the same one the app
    reads its notice version from. Without it, the legacy entry (unmigrated)."""
    if config is not None and config.get("key") != tool_key:
        raise ValueError(f"legal config for {config.get('key')!r} passed to the router for {tool_key!r}")
    cfg = config if config is not None else get_tool(tool_key)  # unknown key: fail at import
    router = APIRouter()

    def page(doc: str, lang: str = "en"):
        # Default arguments bind doc/lang per closure; FastAPI needs a
        # distinct callable per route.
        async def _page(doc=doc, lang=lang) -> HTMLResponse:
            return HTMLResponse(render_legal(tool_key, doc, lang, config=config))
        return _page

    # Every route is NAMED so templates can url_path_for() it — Phronon's
    # base.html does exactly that for 'legal', and an unnamed route turns
    # every page render into a NoMatchFound 500 (found the hard way in CI).
    router.add_api_route("/impressum", page("impressum", "de"), name="impressum",
                         response_class=HTMLResponse, include_in_schema=False,
                         methods=["GET", "HEAD"])
    router.add_api_route("/legal-notice", page("legal_notice"), name="legal_notice",
                         response_class=HTMLResponse, include_in_schema=False,
                         methods=["GET", "HEAD"])
    router.add_api_route("/privacy", page("privacy"), name="privacy",
                         response_class=HTMLResponse, include_in_schema=False,
                         methods=["GET", "HEAD"])
    router.add_api_route("/cookies", page("cookies"), name="cookies",
                         response_class=HTMLResponse, include_in_schema=False,
                         methods=["GET", "HEAD"])
    router.add_api_route("/terms", page("terms"), name="terms",
                         response_class=HTMLResponse, include_in_schema=False,
                         methods=["GET", "HEAD"])
    router.add_api_route("/legal", page("index"), name="legal",
                         response_class=HTMLResponse, include_in_schema=False,
                         methods=["GET", "HEAD"])

    if "de" in cfg["languages"]:
        router.add_api_route("/de/privacy", page("privacy", "de"), name="privacy_de",
                             response_class=HTMLResponse, include_in_schema=False,
                             methods=["GET", "HEAD"])
        router.add_api_route("/de/cookies", page("cookies", "de"), name="cookies_de",
                             response_class=HTMLResponse, include_in_schema=False,
                             methods=["GET", "HEAD"])

    async def _imprint_redirect():
        # Historic canonical URL, published in e-mails and study descriptions.
        # It must keep working forever; /legal orients whoever follows it.
        return RedirectResponse("/legal", status_code=301)

    router.add_api_route("/imprint", _imprint_redirect, name="imprint",
                         include_in_schema=False, methods=["GET", "HEAD"])

    return router
