"""Session revocation: the epoch must cut old cookies off, and only those."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.sessions import (  # noqa: E402
    cookie_payload, epoch_of, session_is_current,
)


def test_a_fresh_cookie_is_current():
    assert session_is_current(cookie_payload(7, 3), 3)


def test_revocation_invalidates_the_old_cookie():
    old = cookie_payload(7, 3)
    assert session_is_current(old, 3)
    assert not session_is_current(old, 4), "an incremented epoch must refuse the old cookie"


def test_a_cookie_from_before_the_feature_still_works():
    """The migration defaults every row to 0, so nobody is logged out by it."""
    legacy = {"id": 7}                     # no 'ep' key at all
    assert epoch_of(legacy) == 0
    assert session_is_current(legacy, 0)
    assert session_is_current(legacy, None), "missing column must not lock people out"


def test_a_forged_or_corrupt_epoch_does_not_pass():
    assert not session_is_current({"id": 7, "ep": "nonsense"}, 2)
    assert not session_is_current({"id": 7, "ep": 99}, 2)
    assert not session_is_current("not-a-dict", 2)


def test_extras_travel_alongside_without_colliding():
    p = cookie_payload(7, 1, role="ADMIN")
    assert p["id"] == 7 and p["ep"] == 1 and p["role"] == "ADMIN"
