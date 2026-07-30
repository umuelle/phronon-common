"""Shared legal pages for the Phronon fleet — one router, nine tools.

Blueprint: phronon-legal-blueprint.md (rev. 2), Part 2. Canonical text lives
once here (legal_templates/ + legal_conf.py); every app mounts the router and
renders SERVER-SIDE FROM ITS OWN ORIGIN — never cross-domain, never via
JavaScript (Part 2.1: an Impressum that depends on another domain or a script
fails "ständig verfügbar" by construction).

Usage in a tool's app.py, replacing its hand-rolled legal routes:

    from phronon_common.legal import build_legal_router
    app.include_router(build_legal_router("whiteout"))

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


def render_legal(tool_key: str, doc: str, lang: str = "en") -> str:
    """Render one legal document to HTML. Exposed for tests."""
    cfg = get_tool(tool_key)
    template = _env.get_template(f"{doc}.html")
    return template.render(
        cfg=cfg,
        lang=lang,
        doc_title=_TITLES[doc].get(lang) or next(iter(_TITLES[doc].values())),
        L=lambda prose: prose.get(lang) or prose["en"],
    )


def build_legal_router(tool_key: str) -> APIRouter:
    cfg = get_tool(tool_key)  # fail at import time if the key is unknown
    router = APIRouter()

    def page(doc: str, lang: str = "en"):
        # Default arguments bind doc/lang per closure; FastAPI needs a
        # distinct callable per route.
        async def _page(doc=doc, lang=lang) -> HTMLResponse:
            return HTMLResponse(render_legal(tool_key, doc, lang))
        return _page

    router.add_api_route("/impressum", page("impressum", "de"),
                         response_class=HTMLResponse, include_in_schema=False)
    router.add_api_route("/legal-notice", page("legal_notice"),
                         response_class=HTMLResponse, include_in_schema=False)
    router.add_api_route("/privacy", page("privacy"),
                         response_class=HTMLResponse, include_in_schema=False)
    router.add_api_route("/cookies", page("cookies"),
                         response_class=HTMLResponse, include_in_schema=False)
    router.add_api_route("/terms", page("terms"),
                         response_class=HTMLResponse, include_in_schema=False)
    router.add_api_route("/legal", page("index"),
                         response_class=HTMLResponse, include_in_schema=False)

    if "de" in cfg["languages"]:
        router.add_api_route("/de/privacy", page("privacy", "de"),
                             response_class=HTMLResponse, include_in_schema=False)
        router.add_api_route("/de/cookies", page("cookies", "de"),
                             response_class=HTMLResponse, include_in_schema=False)

    async def _imprint_redirect():
        # Historic canonical URL, published in e-mails and study descriptions.
        # It must keep working forever; /legal orients whoever follows it.
        return RedirectResponse("/legal", status_code=301)

    router.add_api_route("/imprint", _imprint_redirect, include_in_schema=False)

    return router
