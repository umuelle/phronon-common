"""The loader, the checker and the router's explicit configuration (4 October 2026).

Each tool keeps its own legal_content/notice.json; this package only loads,
checks and renders it. The tools' REAL content is tested in each tool's own
suite (phronon_common.testing.legal_content). Here: small examples built from
the frozen legacy entries, and every way a file can be wrong.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import legal_conf  # noqa: E402
from phronon_common.legal import build_legal_router, render_legal  # noqa: E402
from phronon_common.legal_content import (  # noqa: E402
    LegalConfigError, check_config, export_legacy_entry, load_legal_config)

ENGLISH, BILINGUAL, HUB = "drawbridge", "whiteout", "phronon"


def _write(tmp_path, raw: dict) -> Path:
    p = tmp_path / "notice.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.mark.parametrize("key", [ENGLISH, BILINGUAL, HUB])
def test_a_valid_file_loads_and_renders_exactly_like_the_legacy_entry(tmp_path, key):
    cfg = load_legal_config(key, _write(tmp_path, export_legacy_entry(key)))
    langs = ["en"] + (["de"] if "de" in cfg["languages"] else [])
    for doc in ("impressum", "legal_notice", "privacy", "cookies", "terms", "index"):
        for lang in (["de"] if doc == "impressum" else langs):
            assert render_legal(key, doc, lang, config=cfg) == render_legal(key, doc, lang)


def _broken(change):
    raw = export_legacy_entry(BILINGUAL)
    change(raw)
    return raw


@pytest.mark.parametrize("change, says", [
    (lambda r: r.pop("notice_version"), "missing field 'notice_version'"),
    (lambda r: r.update(notice_version=" "), "notice_version is empty"),
    (lambda r: r.update(schema_version=2), "schema_version is 2"),
    (lambda r: r.update(tool_key="layoff"), "tool_key is 'layoff'"),
    (lambda r: r.update(retenton={"en": "x"}), "unknown field(s) retenton"),
    (lambda r: r.update(art9="no"), "'art9' must be a bool"),
    (lambda r: r["purpose"].pop("de"), "'purpose' has no German text"),
    (lambda r: r["purpose"].pop("en"), "'purpose' has no English text"),
    (lambda r: r.update(languages=["de"]), "languages must include 'en'"),
    (lambda r: r.update(languages=["en", "fr"]), "languages must include 'en' and only"),
    (lambda r: r.pop("cookies_de"), "no 'cookies_de' table"),
    (lambda r: r["cookies"].__setitem__(0, ["a", "b", "c"]), "cookies[0] must be [name, description, lifetime, audience]"),
    (lambda r: r["cookies"][0].__setitem__(3, "everyone"), "audience 'everyone'"),
    (lambda r: r["cookies_de"].reverse(), "same cookies, in the same order"),
    (lambda r: r.update(cookies=[]), "'cookies' is empty"),
    (lambda r: r.update(domain="Whiteout-Exercise.org"), "not a bare lower-case host name"),
])
def test_every_kind_of_broken_file_is_refused(tmp_path, change, says):
    raw = _broken(change)
    assert any(says in p for p in check_config(raw, BILINGUAL)), check_config(raw, BILINGUAL)
    with pytest.raises(LegalConfigError):
        load_legal_config(BILINGUAL, _write(tmp_path, raw))


def test_provenance_may_stay_english_on_a_german_tool():
    """State on 4 October 2026: all three German-serving tools publish their
    source credits in English, and the template falls back to it."""
    raw = export_legacy_entry(BILINGUAL)
    assert "de" not in raw["provenance"] and check_config(raw, BILINGUAL) == []


def test_an_english_only_tool_may_not_carry_a_german_cookie_table():
    raw = export_legacy_entry(ENGLISH)
    raw["cookies_de"] = copy.deepcopy(raw["cookies"])
    assert any("does not serve German" in p for p in check_config(raw, ENGLISH))


def test_a_missing_file_and_bad_json_are_refused(tmp_path):
    with pytest.raises(LegalConfigError, match="no legal content"):
        load_legal_config(ENGLISH, tmp_path / "nope.json")
    bad = tmp_path / "notice.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(LegalConfigError, match="not valid JSON"):
        load_legal_config(ENGLISH, bad)


def test_each_load_is_its_own_object(tmp_path):
    p = _write(tmp_path, export_legacy_entry(ENGLISH))
    a, b = load_legal_config(ENGLISH, p), load_legal_config(ENGLISH, p)
    a["purpose"]["en"] = "changed"
    assert b["purpose"]["en"] != "changed"
    assert legal_conf.TOOLS[ENGLISH]["purpose"]["en"] != "changed"


def test_the_router_and_the_renderer_refuse_another_tools_config(tmp_path):
    cfg = load_legal_config(ENGLISH, _write(tmp_path, export_legacy_entry(ENGLISH)))
    with pytest.raises(ValueError):
        build_legal_router(BILINGUAL, config=cfg)
    with pytest.raises(ValueError):
        render_legal(BILINGUAL, "privacy", config=cfg)


def test_the_router_serves_the_given_config_not_the_legacy_one(tmp_path):
    """After a tool migrates, its file is what is published; the frozen
    legacy entry must not leak back in."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    raw = export_legacy_entry(ENGLISH)
    raw["purpose"]["en"] = "<p>MARKER-FROM-THE-TOOLS-OWN-FILE</p>"
    cfg = load_legal_config(ENGLISH, _write(tmp_path, raw))
    app = FastAPI()
    app.include_router(build_legal_router(ENGLISH, config=cfg))
    c = TestClient(app)
    assert "MARKER-FROM-THE-TOOLS-OWN-FILE" in c.get("/privacy").text
    assert c.head("/privacy").status_code == 200
    assert c.get("/imprint", follow_redirects=False).status_code == 301


def test_the_legacy_router_still_works_for_unmigrated_tools():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(build_legal_router(BILINGUAL))
    c = TestClient(app)
    assert c.get("/de/privacy").status_code == 200 and c.get("/impressum").status_code == 200
