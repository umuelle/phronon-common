"""Two language lists per tool (owner, 13 November 2026, FL-135 decision 23).

The registry said English for Moral Mirror and English and German for Layoff,
while each speaks ten languages to its participants: the one field meant the
legal notices' languages to the check that read it and the participant pages'
to the reader of its comment. `locales` is the notices', `participant_locales`
the pages'. server-ops/tool_registry_check.py compares the second with each
tool's i18n files.
"""
from __future__ import annotations

from phronon_common.registry import TOOLS

TEN = ("ar", "de", "en", "es", "fr", "hi", "it", "pt", "ru", "zh")


def test_layoff_and_moral_mirror_speak_ten_languages_and_publish_their_notices_in_fewer():
    assert TOOLS["layoff"].participant_locales == TEN and TOOLS["layoff"].locales == ("en", "de")
    assert TOOLS["moralmirror"].participant_locales == TEN and TOOLS["moralmirror"].locales == ("en",)


def test_a_tool_without_its_own_list_speaks_its_notices_languages():
    for key in ("whiteout", "polarity", "peakseason", "phronon"):
        assert TOOLS[key].participant_locales == TOOLS[key].locales, key


def test_every_tool_speaks_english_first_in_its_notices():
    for key, t in TOOLS.items():
        assert t.locales and t.locales[0] == "en", key
        assert "en" in t.participant_locales, key
