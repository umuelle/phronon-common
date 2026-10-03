"""The legal-content checks every tool runs against ITS OWN notice.json.

Since 4 October 2026 each tool keeps its notice content in
`legal_content/notice.json` (phronon_common.legal_content says why). The
checks that used to run in this package over all nine entries of
`legal_conf.TOOLS` run here instead, in each tool's own suite, against the
file that tool actually publishes. A tool's test file is a few lines:

    from phronon_common.testing.legal_content import LegalContent

    class TestLegalContent(LegalContent):
        TOOL_KEY = "whiteout"
        NOTICE_PATH = PROJECT_ROOT / "legal_content" / "notice.json"
        APP_SOURCES = (PROJECT_ROOT / "app.py",)

What only a fleet-wide view can see (nine retention periods side by side,
the same German word for "educator" everywhere) is server-ops/legal_table.py,
run by the deploy preflight.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from phronon_common.legal import render_legal
from phronon_common.legal_conf import lifetime_seconds
from phronon_common.legal_content import check_config, load_legal_config
from phronon_common.sessions import ADMIN_SESSION_MAX_AGE, EDUCATOR_SESSION_MAX_AGE

DOCS = ["impressum", "legal_notice", "privacy", "cookies", "terms", "index"]

# (pattern, why): Tier 1 false statements and Tier 2 dead law.
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
GERMAN_AUDIENCES = {"Teilnehmende", "Backoffice", "alle"}


def _bullets(section: str) -> list[str]:
    return [b.strip() for b in re.findall(r"<li>(.*?)</li>", section, re.S)]


def _hours(text: str) -> set:
    return {int(n) for n in re.findall(r"(\d+)\s*hours?", text)}


class LegalContent:
    TOOL_KEY: str = ""
    NOTICE_PATH: Path = Path()
    #: The tool's source files that read the notice version (app.py, and for
    #: Moral Mirror legal_branding.py): checked to read it from THIS file.
    APP_SOURCES: tuple = ()

    # ── helpers ──────────────────────────────────────────────────────────
    def cfg(self) -> dict:
        return load_legal_config(self.TOOL_KEY, self.NOTICE_PATH)

    def render(self, doc: str, lang: str = "en") -> str:
        return render_legal(self.TOOL_KEY, doc, lang, config=self.cfg())

    def pages(self):
        langs = ["en"] + (["de"] if "de" in self.cfg()["languages"] else [])
        for doc in DOCS:
            for lang in (["de"] if doc == "impressum" else langs):
                yield doc, lang

    # ── the file itself ──────────────────────────────────────────────────
    def test_the_file_passes_the_checker(self):
        import json
        raw = json.loads(self.NOTICE_PATH.read_text(encoding="utf-8"))
        assert check_config(raw, self.TOOL_KEY) == []

    def test_the_app_publishes_and_records_from_this_file(self):
        """The pages and the notice version stored with answers come from the
        same loaded object, and nothing reads the old shared table any more."""
        assert self.APP_SOURCES, "name the app's source files in APP_SOURCES"
        seen_loader = False
        for src in self.APP_SOURCES:
            text = Path(src).read_text(encoding="utf-8")
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                    assert not any(n and n.endswith("legal_conf") for n in names), (
                        f"{src} still imports legal_conf: the notice is read from the shared "
                        f"package's frozen copy instead of this tool's own file")
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "load_legal_config":
                    seen_loader = True
        assert seen_loader, "no load_legal_config(...) call in the app's sources"

    # ── every page ───────────────────────────────────────────────────────
    def test_every_page_renders_clean(self):
        for doc, lang in self.pages():
            html = self.render(doc, lang)
            assert html.strip(), f"{doc}/{lang} rendered empty"
            for pat, why in FORBIDDEN:
                assert not re.search(pat, html), f"forbidden string in {doc}/{lang}: {pat!r} — {why}"

    def test_impressum_is_german_and_complete(self):
        html = self.render("impressum", "de")
        assert 'lang="de"' in html and "§ 5 DDG" in html
        assert "Urs Müller" in html and "Gotenstr. 21" in html and "10829 Berlin" in html
        assert self.cfg()["contact_email"] in html
        assert 'content="index, follow"' in html
        assert "Art. 12 Abs. 3 DSGVO" in html

    def test_privacy_art13_essentials(self):
        html = self.render("privacy", "en")
        for needle in ("Art. 4(7) GDPR", "IONOS SE", "outside the EU/EEA",
                       "Berliner Beauftragte", "Alt-Moabit 59",
                       "Your right to object", "Art. 12(3) GDPR", "Art. 22 GDPR"):
            assert needle in html, f"privacy notice lacks {needle!r}"

    def test_the_shared_recipients_block_is_present(self):
        html = self.render("privacy", "en")
        assert re.search(r"We use no third parties for advertising.*?no participant data and no\s*content\.",
                         html, re.S), "the shared recipients + third-country block is missing"

    # ── German ───────────────────────────────────────────────────────────
    def test_a_german_tool_publishes_a_german_notice(self):
        cfg = self.cfg()
        if "de" not in cfg["languages"]:
            assert "cookies_de" not in cfg
            return
        html = self.render("privacy", "de")
        assert "Datenschutzerklärung" in html and "DSGVO" in html
        assert "§ 25 Abs. 2 Nr. 2 TDDDG" in self.render("cookies", "de")
        text = self.NOTICE_PATH.read_text(encoding="utf-8")
        assert "Kursleitung" not in text, "the fleet's German word for an educator is “Lehrperson”"

    def test_the_german_cookie_table_matches_the_english_one(self):
        cfg = self.cfg()
        if "de" not in cfg["languages"]:
            return
        for (name, en_purpose, en_life, _ew), (de_name, de_purpose, de_life, de_who) in zip(
                cfg["cookies"], cfg["cookies_de"]):
            assert de_name == name, "a cookie name is a literal the browser sends"
            assert lifetime_seconds(de_life) == lifetime_seconds(en_life), (
                f"{name} publishes different lifetimes: EN {en_life!r}, DE {de_life!r}")
            if lifetime_seconds(en_life):
                assert lifetime_seconds(de_life), f"{name}: {de_life!r} cannot be read as a lifetime"
            assert de_purpose != en_purpose, f"{name}: the German purpose is the English sentence"
            assert de_who in GERMAN_AUDIENCES, f"{name}: “{de_who}” is not one of {sorted(GERMAN_AUDIENCES)}"
        html = re.sub(r"<code>.*?</code>", " ", self.render("cookies", "de"), flags=re.S)
        text = re.sub(r"<[^>]+>", " ", html)
        for english in (" hours", " minutes", "participants", "backoffice"):
            assert english not in text, f"the German cookie page still says “{english.strip()}”"
        assert "Lebensdauer" in text and "Betrifft" in text
        en_text = re.sub(r"<[^>]+>", " ", self.render("cookies", "en"))
        assert "Lebensdauer" not in en_text and "Teilnehmende" not in en_text

    def test_both_locales_make_the_same_number_of_promises(self):
        cfg = self.cfg()
        for field in ("collect", "basis", "access", "retention"):
            block = cfg[field]
            if "de" in block and "en" in block:
                en, de = _bullets(block["en"]), _bullets(block["de"])
                assert len(en) == len(de), (
                    f"{field}: {len(en)} bullets in English, {len(de)} in German — "
                    f"a promise in one locale only is a promise half-kept")

    # ── the backoffice session cookie ────────────────────────────────────
    def test_the_published_session_lifetimes_match_the_code(self):
        cfg = self.cfg()
        rows = [(name, life) for name, purpose, life, audience in cfg["cookies"]
                if audience == "backoffice" and "signed in" in purpose]
        assert rows, "no backoffice session row: the tool publishes no session lifetime at all"
        admin, educator = ADMIN_SESSION_MAX_AGE // 3600, EDUCATOR_SESSION_MAX_AGE // 3600
        for name, life in rows:
            if cfg.get("is_hub"):
                assert _hours(life) == {admin}, f"{name}: {life!r}"
            else:
                assert _hours(life) == {educator, admin}, (
                    f"{name} publishes {sorted(_hours(life))} h; the code gives {educator} h to "
                    f"educators and {admin} h to admins")
                assert "administrator" in life.lower() and "educator" in life.lower(), f"{name}: {life!r}"
