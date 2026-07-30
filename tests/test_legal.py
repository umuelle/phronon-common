"""Render every legal document for every tool and enforce the
anti-regression register (phronon-legal-blueprint.md, Part 6).

This is the build-time half of the guard; server-ops/legal_check.py asserts
the same things against the live sites after deploy.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.legal import render_legal  # noqa: E402
from phronon_common.legal_conf import TOOLS, get_tool  # noqa: E402

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
    html = render_legal(key, doc, lang)
    assert html.strip(), f"{key}/{doc}/{lang} rendered empty"
    for pat, why in FORBIDDEN:
        m = re.search(pat, html)
        assert not m, f"forbidden string in {key}/{doc}/{lang}: {pat!r} — {why}"


@pytest.mark.parametrize("key", list(TOOLS))
def test_impressum_is_german_and_complete(key):
    html = render_legal(key, "impressum", "de")
    assert 'lang="de"' in html
    assert "§ 5 DDG" in html
    assert "Urs Müller" in html and "Gotenstr. 21" in html and "10829 Berlin" in html
    assert f"info@{get_tool(key)['domain']}" in html
    assert 'content="index, follow"' in html
    assert "Art. 12 Abs. 3 DSGVO" in html


@pytest.mark.parametrize("key", list(TOOLS))
def test_privacy_art13_essentials(key):
    html = render_legal(key, "privacy", "en")
    for needle in ("Art. 4(7) GDPR", "IONOS SE", "outside the EU/EEA",
                   "Berliner Beauftragte", "Alt-Moabit 59",
                   "Your right to object", "Art. 12(3) GDPR", "Art. 22 GDPR"):
        assert needle in html, f"{key}: privacy notice lacks {needle!r}"


@pytest.mark.parametrize("key", ["lsr", "whiteout", "layoff"])
def test_german_ui_tools_have_german_notice(key):
    # Part 1.2a: a tool that addresses users in German owes them the notice
    # in German. Adding "de" to a tool's languages without German prose must
    # fail loudly (StrictUndefined/KeyError), never render half-English.
    html = render_legal(key, "privacy", "de")
    assert "Datenschutzerklärung" in html
    assert "DSGVO" in html
    html = render_legal(key, "cookies", "de")
    assert "§ 25 Abs. 2 Nr. 2 TDDDG" in html


def test_cookie_tables_have_rows():
    for key in TOOLS:
        cfg = get_tool(key)
        assert cfg["cookies"], f"{key} has no cookie table rows"
        for row in cfg["cookies"]:
            assert len(row) == 4


def test_shared_blocks_render_identically():
    # The recipients paragraph must be byte-identical on all nine once the
    # per-tool e-mail is normalised out — it lives in exactly one partial.
    variants = set()
    for key in TOOLS:
        html = render_legal(key, "privacy", "en")
        m = re.search(r"We use no third parties for advertising.*?outside the EU/EEA\.",
                      html, re.S)
        assert m, key
        variants.add(m.group(0))
    assert len(variants) == 1, "recipients block drifted between tools"
