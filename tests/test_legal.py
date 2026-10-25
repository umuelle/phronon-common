"""Render every legal document from the shared templates and enforce the
anti-regression register (phronon-legal-blueprint.md, Part 6).

This is the build-time half of the guard; server-ops/legal_check.py asserts
the same things against the live sites after deploy. Each tool runs the same
checks against its own published notice.json
(phronon_common.testing.legal_content); here the templates are rendered with
three example files in tests/fixtures/legal/ (an English-only tool, a
bilingual one and the hub), so a template change is caught in this package
before any tool sees it.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.legal import render_legal  # noqa: E402
from phronon_common.legal_content import load_legal_config  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "legal"
TOOLS = ("drawbridge", "whiteout", "phronon")
GERMAN = "whiteout"


def get_tool(key: str) -> dict:
    return load_legal_config(key, FIXTURES / f"{key}.json")


def _render(key: str, doc: str, lang: str = "en") -> str:
    return render_legal(key, doc, lang, config=get_tool(key))

DOCS = ["impressum", "legal_notice", "privacy", "cookies", "terms", "index"]

# (pattern, why) — Tier 1 false statements and Tier 2 dead law.
FORBIDDEN = [
    (r"\bTMG\b", "TMG repealed — § 5 DDG"),
    (r"\bTTDSG\b", "renamed TDDDG"),
    (r"RStÄ?V", "dead treaty citation"),
    (r"\bVSBG\b", "a voluntary VSBG statement creates an obligation"),
    (r"\bBFSG\b", "cite the standard, never the statute"),
    (r"5 business days", "contradicts the § 5 DDG fast-contact position"),
    (r"SHA-256", "passwords are bcrypt"),
    (r"fully anonymous", "tokens/hashes make data pseudonymous"),
    (r"Streitbeilegung|ec\.europa\.eu/consumers/odr", "EU ODR platform is dead"),
    (r"to any third parties", "IONOS SE is a named processor"),
    (r"[Nn]o third parties\b(?!,? for advertising)", "IONOS SE is a named processor"),
    (r"urs-mueller\.com", "private domain"),
]


def _pages():
    for key in TOOLS:
        cfg = get_tool(key)
        langs = ["en"] + (["de"] if "de" in cfg["languages"] else [])
        for doc in DOCS:
            for lang in (["de"] if doc == "impressum" else langs):
                yield key, doc, lang


@pytest.mark.parametrize("key,doc,lang", list(_pages()))
def test_renders_clean(key, doc, lang):
    html = _render(key, doc, lang)
    assert html.strip(), f"{key}/{doc}/{lang} rendered empty"
    for pat, why in FORBIDDEN:
        m = re.search(pat, html)
        assert not m, f"forbidden string in {key}/{doc}/{lang}: {pat!r} — {why}"


@pytest.mark.parametrize("key", list(TOOLS))
def test_impressum_is_german_and_complete(key):
    html = _render(key, "impressum", "de")
    assert 'lang="de"' in html
    assert "§ 5 DDG" in html
    assert "Urs Müller" in html and "Gotenstr. 21" in html and "10829 Berlin" in html
    assert f"info@{get_tool(key)['domain']}" in html
    assert 'content="index, follow"' in html
    assert "Art. 12 Abs. 3 DSGVO" in html


@pytest.mark.parametrize("key", list(TOOLS))
def test_privacy_art13_essentials(key):
    html = _render(key, "privacy", "en")
    for needle in ("Art. 4(7) GDPR", "IONOS SE", "outside the EU/EEA",
                   "Berliner Beauftragte", "Alt-Moabit 59",
                   "Your right to object", "Art. 12(3) GDPR", "Art. 22 GDPR"):
        assert needle in html, f"{key}: privacy notice lacks {needle!r}"


def test_german_ui_tools_have_german_notice():
    # Part 1.2a: a tool that addresses users in German owes them the notice
    # in German. Adding "de" to a tool's languages without German prose must
    # fail loudly (StrictUndefined/KeyError), never render half-English.
    key = GERMAN
    html = _render(key, "privacy", "de")
    assert "Datenschutzerklärung" in html
    assert "DSGVO" in html
    html = _render(key, "cookies", "de")
    assert "§ 25 Abs. 2 Nr. 2 TDDDG" in html


def test_cookie_tables_have_rows():
    for key in TOOLS:
        cfg = get_tool(key)
        assert cfg["cookies"], f"{key} has no cookie table rows"
        for row in cfg["cookies"]:
            assert len(row) == 4


def test_shared_blocks_render_identically():
    # The recipients paragraph must be byte-identical in every example once the
    # per-tool e-mail is normalised out — it lives in exactly one partial.
    variants = set()
    for key in TOOLS:
        html = _render(key, "privacy", "en")
        m = re.search(r"We use no third parties for advertising.*?no participant data and no\s*content\.",
                      html, re.S)
        assert m, (
            f"{key}: the shared recipients + third-country block could not be "
            f"found. Its closing sentence changed on 2026-08-01 (the flat "
            f"'No personal data is transferred outside the EU/EEA' became a "
            f"paragraph naming the Microsoft Art. 46 safeguards and "
            f"healthchecks.io's EU/US infrastructure); if it moved again, "
            f"re-anchor this test rather than deleting it"
        )
        variants.add(m.group(0))
    assert len(variants) == 1, "recipients block drifted between tools"


def test_healthchecks_is_named_for_the_alert_check_too():
    # Since 1.88.0 (TO DO FL-107, wording approved by the owner on 25 October
    # 2026) every alert run pings healthchecks.io, besides the backup run. The
    # list and the transfers paragraph say so in both languages; going back to
    # "backup run only" would publish less than the server sends.
    for key in TOOLS:
        en = " ".join(_render(key, "privacy", "en").split())
        assert "monitoring that the backup run and the platform's alert check happened" in en, key
        assert "status pings from the backup run and the alert check" in en, key
    de = " ".join(_render(GERMAN, "privacy", "de").split())
    assert "ob der Sicherungslauf und die Störungsprüfung der Plattform stattgefunden haben" in de
    assert "Statusmeldungen des Sicherungslaufs und der Störungsprüfung" in de


# ── The stylesheet (FL-093, 25 October 2026) ────────────────────────────────

def _router_client(key: str):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from phronon_common.legal import build_legal_router
    app = FastAPI()
    app.include_router(build_legal_router(key, config=get_tool(key)))
    return TestClient(app)


def test_the_router_serves_the_stylesheet_its_pages_link():
    """The rules that were a <style> block in layout.html come from one file,
    served by the router itself at a versioned same-origin address."""
    from phronon_common.legal import STYLESHEET_URL
    sheet = (Path(__file__).resolve().parents[1] / "legal_templates" / "legal.css").read_text(encoding="utf-8")
    c = _router_client(GERMAN)
    for path in ("/privacy", "/de/cookies", "/impressum", "/legal"):
        html = c.get(path).text
        assert f'<link rel="stylesheet" href="{STYLESHEET_URL}">' in html, path
        assert "<style" not in html, f"{path} still carries an inline style block"
    r = c.get(STYLESHEET_URL)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")
    assert r.text == sheet and ".lp-wrap" in r.text
    assert "immutable" in r.headers["cache-control"]
    assert c.head("/legal.css").status_code == 200
    # The version is the file's content: a changed rule is a new address.
    import hashlib
    assert STYLESHEET_URL.endswith(hashlib.sha256(sheet.encode()).hexdigest()[:12])


def test_a_page_rendered_outside_the_router_carries_the_same_rules_inline():
    """render_legal without stylesheet_url (a tool's own legal router that does
    not serve the sheet yet, and every test): the same file, inline, with its
    quotes intact, so the page never loses its layout."""
    sheet = (Path(__file__).resolve().parents[1] / "legal_templates" / "legal.css").read_text(encoding="utf-8")
    html = _render(GERMAN, "privacy", "en")
    assert sheet in html and '"Segoe UI"' in html
    assert '<link rel="stylesheet"' not in html
