"""The loader, the checker and the router's explicit configuration (4 October 2026).

Each tool keeps its own legal_content/notice.json; this package only loads,
checks and renders it. The tools' REAL content is tested in each tool's own
suite (phronon_common.testing.legal_content). Here: three example files in
tests/fixtures/legal/ (an English-only tool, a bilingual one and the hub,
written from the old shared table the day it went, FL-079) and every way a
file can be wrong.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.legal import build_legal_router, render_legal  # noqa: E402
from phronon_common.legal_content import (  # noqa: E402
    LegalConfigError, check_config, load_legal_config)

ENGLISH, BILINGUAL, HUB = "drawbridge", "whiteout", "phronon"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "legal"


def _example(key: str) -> dict:
    """A fresh copy of one example file's content."""
    return json.loads((FIXTURES / f"{key}.json").read_text(encoding="utf-8"))


def _write(tmp_path, raw: dict) -> Path:
    p = tmp_path / "notice.json"
    p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return p


@pytest.mark.parametrize("key", [ENGLISH, BILINGUAL, HUB])
def test_a_valid_file_loads_and_every_page_renders(tmp_path, key):
    cfg = load_legal_config(key, _write(tmp_path, _example(key)))
    assert cfg["key"] == key and cfg["contact_email"] == f"info@{cfg['domain']}"
    langs = ["en"] + (["de"] if "de" in cfg["languages"] else [])
    for doc in ("impressum", "legal_notice", "privacy", "cookies", "terms", "index"):
        for lang in (["de"] if doc == "impressum" else langs):
            html = render_legal(key, doc, lang, config=cfg)
            assert html.strip() and cfg["tool_name"] in html, f"{key} {doc}/{lang}"


def _broken(change):
    raw = _example(BILINGUAL)
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
    raw = _example(BILINGUAL)
    assert "de" not in raw["provenance"] and check_config(raw, BILINGUAL) == []


def test_an_english_only_tool_may_not_carry_a_german_cookie_table():
    raw = _example(ENGLISH)
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
    p = _write(tmp_path, _example(ENGLISH))
    a, b = load_legal_config(ENGLISH, p), load_legal_config(ENGLISH, p)
    a["purpose"]["en"] = "changed"
    assert b["purpose"]["en"] != "changed"


def test_the_router_and_the_renderer_refuse_another_tools_config(tmp_path):
    cfg = load_legal_config(ENGLISH, _write(tmp_path, _example(ENGLISH)))
    with pytest.raises(ValueError):
        build_legal_router(BILINGUAL, config=cfg)
    with pytest.raises(ValueError):
        render_legal(BILINGUAL, "privacy", config=cfg)


def test_the_router_serves_the_given_config(tmp_path):
    """The tool's own file is what is published."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    raw = _example(ENGLISH)
    raw["purpose"]["en"] = "<p>MARKER-FROM-THE-TOOLS-OWN-FILE</p>"
    cfg = load_legal_config(ENGLISH, _write(tmp_path, raw))
    app = FastAPI()
    app.include_router(build_legal_router(ENGLISH, config=cfg))
    c = TestClient(app)
    assert "MARKER-FROM-THE-TOOLS-OWN-FILE" in c.get("/privacy").text
    assert c.head("/privacy").status_code == 200
    assert c.get("/imprint", follow_redirects=False).status_code == 301


def test_the_german_routes_exist_only_for_a_german_tool(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    for key, german in ((BILINGUAL, True), (ENGLISH, False)):
        cfg = load_legal_config(key, _write(tmp_path, _example(key)))
        app = FastAPI()
        app.include_router(build_legal_router(key, config=cfg))
        c = TestClient(app)
        assert c.get("/impressum").status_code == 200
        assert (c.get("/de/privacy").status_code == 200) is german
        assert (c.get("/de/cookies").status_code == 200) is german


def test_there_is_no_page_without_the_tools_own_content():
    """FL-079 (25 October 2026): the frozen shared table that used to answer
    a call without `config=` is gone, so such a call fails loudly at startup
    instead of publishing an old notice."""
    with pytest.raises(TypeError):
        build_legal_router(BILINGUAL)
    with pytest.raises(TypeError):
        render_legal(BILINGUAL, "privacy", "en")
    from phronon_common import legal_conf
    assert not hasattr(legal_conf, "TOOLS") and not hasattr(legal_conf, "get_tool")
