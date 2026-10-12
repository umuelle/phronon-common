"""translations.py: one loader and one t() for Layoff, Whiteout and PP.

The fixture files below carry the shapes the three tools' real files use:
nested objects, a list read by index (Whiteout), a list read whole (Layoff's
option arrays, PP's month names), strings with their own markup (PP) and
``{name}`` placeholders. The last test loads the tools' real files when the
workspace has them beside this package.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from markupsafe import Markup

from phronon_common import translations as tr

EN = {
    "home": {"title": "Welcome", "hello": "Hello {name}",
             "intro": "Read <strong>{class_name}</strong> first",
             "only_en": "English only", "braces": "Use {{curly}} braces"},
    "demographics": {"age_bands": ["under 25", "25-34", "35-44"],
                     "options": {"gender": ["woman", "man", "non-binary"]}},
    "email": {"subject": "Sales & Marketing: {class_name}"},
}
DE = {
    "home": {"title": "Willkommen", "hello": "Hallo {nmae}",
             "intro": "Lies zuerst <strong>{class_name}</strong>"},
    "demographics": {"age_bands": ["unter 25"]},
}


@pytest.fixture
def i18n(tmp_path):
    folder = tmp_path / "i18n"
    folder.mkdir()
    (folder / "en.json").write_text(json.dumps(EN), encoding="utf-8")
    (folder / "de.json").write_text(json.dumps(DE), encoding="utf-8")
    return folder


@pytest.fixture(autouse=True)
def _fresh_reports():
    tr._reported.clear()
    yield
    tr._reported.clear()


def test_a_missing_german_string_falls_back_to_english_per_string(i18n):
    t = tr.Catalog(i18n, ["en", "de"]).translator("de")
    assert t("home.title") == "Willkommen"
    assert t("home.only_en") == "English only"
    assert tr.Catalog(i18n, ["en", "de"]).load("de")["home"]["only_en"] == "English only"


def test_a_missing_key_returns_the_key_and_is_logged_once(i18n, caplog):
    t = tr.Catalog(i18n, ["en", "de"]).translator("de")
    with caplog.at_level(logging.WARNING, logger="phronon_common.translations"):
        assert t("home.nowhere") == "home.nowhere"
        assert t("home.nowhere") == "home.nowhere"
    assert sum("home.nowhere" in r.getMessage() for r in caplog.records) == 1


def test_a_language_the_tool_does_not_speak_reads_english(i18n, tmp_path):
    (tmp_path / "secret.json").write_text(json.dumps({"home": {"title": "LEAK"}}))
    cat = tr.Catalog(i18n, ["en", "de"])
    for lang in ("fr", "../secret", "/etc/passwd", None, ""):
        assert cat.translator(lang)("home.title") == "Welcome"
        assert cat.language(lang) == "en"


def test_a_broken_translation_reads_english_and_a_broken_english_raises(i18n, caplog):
    (i18n / "de.json").write_text("{ not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="phronon_common.translations"):
        assert tr.Catalog(i18n, ["en", "de"]).translator("de")("home.title") == "Welcome"
    assert any("cannot load" in r.getMessage() for r in caplog.records)
    (i18n / "en.json").unlink()
    with pytest.raises(OSError):
        tr.Catalog(i18n, ["en", "de"]).translator("en")


def test_list_indexes_and_whole_lists(i18n):
    cat = tr.Catalog(i18n, ["en", "de"])
    t = cat.translator("de")
    assert t("demographics.age_bands.0") == "unter 25"           # Whiteout's index
    assert t("demographics.age_bands.2") == "35-44"              # beyond de's list: English
    assert t("demographics.age_bands") == ["unter 25"]           # lists replace, never merge
    assert t("demographics.options.gender") == ["woman", "man", "non-binary"]
    assert t("demographics.age_bands.9") == "demographics.age_bands.9"


def test_the_template_translator_escapes_values_and_keeps_its_own_markup(i18n):
    t = tr.Catalog(i18n, ["en", "de"]).translator("en", html=True)
    out = t("home.intro", class_name="<script>x</script>")
    assert isinstance(out, Markup)
    assert out == "Read <strong>&lt;script&gt;x&lt;/script&gt;</strong> first"
    nested = t("home.intro", class_name=t("home.title"))
    assert nested == "Read <strong>Welcome</strong> first"
    assert t("home.intro", class_name=Markup("<em>ok</em>")) == \
        "Read <strong><em>ok</em></strong> first"


def test_the_plain_translator_returns_text_for_mail_subjects(i18n):
    t = tr.Catalog(i18n, ["en"]).translator("en")
    out = t("email.subject", class_name="R&D <1>")
    assert type(out) is str
    assert out == "Sales & Marketing: R&D <1>"


def test_format_runs_only_with_values(i18n):
    t = tr.Catalog(i18n, ["en"]).translator("en")
    assert t("home.braces") == "Use {{curly}} braces"
    assert t("home.braces", x=1) == "Use {curly} braces"
    assert t("demographics.age_bands", name="x") == ["under 25", "25-34", "35-44"]


def test_a_placeholder_typo_falls_back_to_english_not_to_a_500(i18n, caplog):
    cat = tr.Catalog(i18n, ["en", "de"])
    with caplog.at_level(logging.ERROR, logger="phronon_common.translations"):
        out = cat.translator("de")("home.hello", name="Ada")
    assert out == "Hello Ada"                       # the English string, formatted
    assert any(r.exc_info for r in caplog.records)  # logged with the traceback
    # Both broken: the text unformatted, never an exception.
    t = tr.make_translator({"k": "{a}"}, fallback={"k": "{b}"})
    assert t("k", c=1) == "{a}"
    th = tr.make_translator({"k": "<b>{a}</b>"}, html=True)
    assert th("k", c=1) == Markup("<b>{a}</b>")


def test_load_hands_out_a_copy_the_caller_may_edit(i18n):
    cat = tr.Catalog(i18n, ["en", "de"])
    mine = cat.load("de")
    mine.setdefault("rank", {})["scenario"] = "frozen"          # Whiteout's edit
    mine["home"]["title"] = "changed"
    assert "rank" not in cat.load("de")
    assert cat.translator("de")("home.title") == "Willkommen"
    assert cat.translator("en")("home.title") == "Welcome"


def test_files_are_read_once_until_cleared(i18n):
    cat = tr.Catalog(i18n, ["en", "de"])
    assert cat.translator("en")("home.title") == "Welcome"
    (i18n / "en.json").write_text(json.dumps({"home": {"title": "Edited"}}))
    assert cat.translator("en")("home.title") == "Welcome"
    cat.clear()
    assert cat.translator("en")("home.title") == "Edited"


def test_a_tool_built_dict_with_an_english_fallback(i18n):
    cat = tr.Catalog(i18n, ["en", "de"])
    frozen = tr.deep_merge(cat.load("de"), {"rank": {"intro": "Eingefroren"}})
    t = tr.make_translator(frozen, fallback=cat.load("en"))
    assert t("rank.intro") == "Eingefroren"
    assert t("home.only_en") == "English only"


def test_the_default_language_must_be_one_the_tool_speaks(i18n):
    with pytest.raises(ValueError):
        tr.Catalog(i18n, ["en", "de"], default="fr")
    with pytest.raises(ValueError):
        tr.Catalog(i18n, [])


_WORKSPACE = Path(__file__).resolve().parents[2]
_TOOL_FILES = [(tool, langs) for tool, langs in (
    ("Layoff-Exercise", ["en", "de", "es", "fr", "it", "pt", "ru", "zh", "ar", "hi"]),
    ("Whiteout", ["en", "de"]),
    ("polarity-profiler", ["en", "de"]),
) if (_WORKSPACE / tool / "i18n" / "en.json").is_file()]


def _leaves(data, prefix=""):
    if isinstance(data, dict):
        for k, v in data.items():
            yield from _leaves(v, f"{prefix}{k}.")
    else:
        yield prefix[:-1], data


@pytest.mark.skipif(not _TOOL_FILES, reason="the tools are not beside this checkout")
@pytest.mark.parametrize("tool, langs", _TOOL_FILES)
def test_the_tools_real_files_load_unchanged(tool, langs):
    folder = _WORKSPACE / tool / "i18n"
    cat = tr.Catalog(folder, langs)
    english = json.loads((folder / "en.json").read_text(encoding="utf-8"))
    for lang in langs:
        own = json.loads((folder / f"{lang}.json").read_text(encoding="utf-8"))
        t = cat.translator(lang)
        for key, value in _leaves(english):
            mine = tr.lookup(own, key, None)
            assert t(key) == (value if mine is None else mine), (tool, lang, key)
