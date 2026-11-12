"""The hub's OrgDesignSim card describes the game a session starts in.

The card has followed the tool twice. On 28 October 2026 (OD-003) it stopped
describing the Legacy sandbox alone ("~60 min", "52 simulated weeks"). Since
12 November 2026 an educator's new session starts in one game, the design
game: six simulated months, about 20 minutes, about levels and spans of
control. The five earlier versions are retired, so the card no longer speaks
of six or twelve months, of a range of 10 to 30 minutes, or of finances
(OD-012). OrgDesignSim's welcome page states the same six months and 20
minutes; its own suite holds that page to them.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.registry import PRESENTATIONS  # noqa: E402

CARD = PRESENTATIONS["orgsim"]


def _card_text() -> str:
    return " ".join([CARD.blurb, *CARD.how])


def test_the_card_states_the_design_games_length():
    assert re.fullmatch(r"20 min \+ debrief", CARD.duration), CARD.duration
    assert "six simulated months" in _card_text()


def test_the_card_no_longer_describes_the_retired_versions():
    text = _card_text()
    for gone in ("52 simulated weeks", "six or twelve", "twelve simulated months", "finances"):
        assert gone not in text, f"the card still says {gone!r}"
    assert "10" not in CARD.duration and "30" not in CARD.duration


def test_the_card_names_what_the_game_is_about():
    text = _card_text()
    assert "span" in text and "level" in text
    for setting in ("start-up", "turnaround", "merger", "matrix"):
        assert setting in text, f"the card does not name the {setting}"


def test_the_card_says_session_for_what_an_educator_creates():
    assert "creates a session" in _card_text()
