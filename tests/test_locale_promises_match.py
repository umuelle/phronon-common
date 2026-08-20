"""A promise made in one locale must be made in the other.

20 August 2026. The Whiteout prediction bullet was reworded in English — "one
unnamed point per person on a chart… in a small class an educator could work
out which point is yours" — and the German was left saying the answer is shown
"als Gesamtwert für den Kurs", which is the promise the chart had stopped
keeping. Both locales carried the same `notice_version`, so every version check
in the fleet was satisfied while the two texts said different things.

The version number cannot see this. Only a comparison of the two texts can.
"""
from __future__ import annotations

import re

import pytest

from phronon_common import legal_conf


def _strip(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html)


def _bullets(section: str) -> list[str]:
    return [b.strip() for b in re.findall(r"<li>(.*?)</li>", section, re.S)]


@pytest.mark.parametrize("tool", sorted(legal_conf.TOOLS))
def test_both_locales_make_the_same_number_of_promises(tool):
    """Not a translation check — a COUNT check. A bullet added to one locale
    and not the other is exactly how a promise ends up half-kept."""
    cfg = legal_conf.TOOLS[tool]
    for field in ("collect", "basis", "access", "retention"):
        block = cfg.get(field) or {}
        if not isinstance(block, dict) or "de" not in block or "en" not in block:
            continue          # tools with an English-only notice are declared so
        en, de = _bullets(block["en"]), _bullets(block["de"])
        assert len(en) == len(de), (
            f"{tool}.{field}: {len(en)} bullets in English, {len(de)} in German. "
            f"A promise in one locale only is a promise half-kept."
        )


def test_whiteouts_prediction_bullet_says_the_same_thing_in_both():
    """The specific one that went wrong, named so the next reader sees it."""
    collect = legal_conf.TOOLS["whiteout"]["collect"]
    en, de = _strip(collect["en"]), _strip(collect["de"])
    # English: an unnamed point per person, and a small class can be worked out.
    assert "unnamed point per person" in en
    assert "small class" in en
    # German: the same two facts, or the German reader is promised more.
    assert "unbeschrifteter Punkt pro Person" in de
    assert "kleinen Klasse" in de
    assert "als Gesamtwert für den Kurs angezeigt, nie neben Ihrem Namen" not in de, (
        "the old, stronger German promise is back"
    )
