"""The hub's OrgDesignSim card describes the game a session starts in
(OD-003, owner, 28 October 2026).

The card said "~60 min" and "Across 52 simulated weeks they restructure it,
week by week", which is the Legacy sandbox. Since OD-008 (27 October 2026) a
new session starts in the 12-month studio, played in monthly rounds, and
OrgDesignSim's welcome page states 10 to 30 minutes across its games. The
card follows: the same range plus the debrief, six or twelve months, and
"session", the fleet's word for what an educator creates.
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


def test_the_card_states_the_welcome_pages_range_of_minutes():
    m = re.match(r"(\d+)–(\d+) min", CARD.duration)
    assert m, CARD.duration
    assert (int(m.group(1)), int(m.group(2))) == (10, 30)


def test_the_card_no_longer_describes_the_legacy_sandbox_alone():
    text = _card_text()
    assert "52 simulated weeks" not in text
    assert "six or twelve simulated months" in text


def test_the_card_says_session_for_what_an_educator_creates():
    assert "creates a session" in _card_text()
