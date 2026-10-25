"""Session length depends on the role — and the published tables must say so.

Owner's decision, 19 August 2026: an educator's session runs 6 hours (a
teaching day with a break in it), an admin's 3 (a short, deliberate visit with
the whole tool behind it). Before this the whole fleet ran a flat 4 hours.

Two things are pinned here, and the second is the one that rots:

  1. `max_age_for` answers the two numbers, for every spelling of the role the
     fleet uses ("ADMIN" in one schema, "admin" in another) — and OWNER, the
     hub's own role, which `twofactor.is_required` forgot for three weeks.

  2. Every backoffice row in every published cookie table names those same two
     numbers. Since FL-079 (25 October 2026) that half runs in each tool's own
     suite against the notice it publishes
     (phronon_common.testing.legal_content,
     `test_the_published_session_lifetimes_match_the_code`), and
     `closing_audit.py` checks the same pairing from the other end (published
     text against the `max_age` in the app).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import signing  # noqa: E402
from phronon_common.sessions import (  # noqa: E402
    ADMIN_SESSION_MAX_AGE, EDUCATOR_SESSION_MAX_AGE, MAX_SESSION_AGE,
    is_privileged, max_age_for, session_age_ok,
)


# ── The two numbers ─────────────────────────────────────────────────────────

def test_the_two_lifetimes_are_six_and_three_hours():
    assert EDUCATOR_SESSION_MAX_AGE == 6 * 3600
    assert ADMIN_SESSION_MAX_AGE == 3 * 3600


def test_an_admin_session_is_shorter_than_an_educator_session():
    """The direction is the whole point — do not let a refactor invert it."""
    assert ADMIN_SESSION_MAX_AGE < EDUCATOR_SESSION_MAX_AGE


def test_the_ceiling_is_the_longer_of_the_two():
    """Signers are built with the ceiling, before any role is known."""
    assert MAX_SESSION_AGE == EDUCATOR_SESSION_MAX_AGE
    assert signing.DEFAULT_MAX_AGE == MAX_SESSION_AGE


# ── Reading the role ────────────────────────────────────────────────────────

def test_every_spelling_of_admin_gets_the_short_session():
    for role in ("ADMIN", "admin", " Admin ", "OWNER", "owner"):
        assert is_privileged(role), role
        assert max_age_for(role) == ADMIN_SESSION_MAX_AGE, role


def test_educators_and_facilitators_get_the_long_session():
    for role in ("EDUCATOR", "educator", "facilitator"):
        assert not is_privileged(role), role
        assert max_age_for(role) == EDUCATOR_SESSION_MAX_AGE, role


def test_a_missing_role_gets_the_long_session_not_the_short_one():
    """A tool whose role column is empty must not have every educator cut to
    three hours by a spelling change — that is a visible outage. The safe
    direction here is the behaviour every account already had."""
    for role in (None, "", "   ", "something-new"):
        assert max_age_for(role) == EDUCATOR_SESSION_MAX_AGE, repr(role)


# ── The second, narrower age check ──────────────────────────────────────────

class _RecordingSigner:
    """Stands in for a CookieSigner and records the age it was asked about."""

    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def loads(self, raw, max_age=None):
        self.asked.append(max_age)
        return self.answer


def test_an_admin_cookie_is_re_checked_against_the_shorter_limit():
    sig = _RecordingSigner({"id": 1})
    assert session_age_ok(sig, "cookie", "ADMIN")
    assert sig.asked == [ADMIN_SESSION_MAX_AGE]


def test_an_admin_cookie_older_than_three_hours_is_refused():
    sig = _RecordingSigner(None)          # the signer rejects it as too old
    assert not session_age_ok(sig, "cookie", "ADMIN")


def test_an_educator_cookie_needs_no_second_check():
    """It was already verified against the ceiling, which IS their limit."""
    sig = _RecordingSigner(None)
    assert session_age_ok(sig, "cookie", "educator")
    assert sig.asked == [], "re-checking an educator would refuse a valid session"


# ── The real thing: a signed cookie, aged ───────────────────────────────────
# The checks above use a stand-in signer, which proves the plumbing asks the
# right question but not that itsdangerous answers it. This drives a real
# CookieSigner against a moved clock, and it is the test that would have caught
# a signer built with the wrong ceiling.

def test_a_real_cookie_is_refused_at_three_hours_for_an_admin_and_six_for_an_educator():
    import itsdangerous.timed as _timed
    from phronon_common.signing import CookieSigner

    signer = CookieSigner("a-secret-key-for-this-test-only", salt="admin")
    raw = signer.dumps({"id": 1, "ep": 0})

    real_time = time.time

    def accepted(hours_old: int, role: str) -> bool:
        _timed.time.time = lambda: real_time() + hours_old * 3600
        try:
            # Both halves, in the order a request does them: the ceiling the
            # signer was built with, then the role's own limit.
            return signer.loads(raw) is not None and session_age_ok(signer, raw, role)
        finally:
            _timed.time.time = real_time

    assert accepted(2, "ADMIN"), "an admin must stay signed in for the first 3 hours"
    assert not accepted(4, "ADMIN"), "an admin session must be dead at 4 hours"
    assert accepted(4, "educator"), "an educator must survive 4 hours — the old fleet limit"
    assert accepted(5, "educator")
    assert not accepted(7, "educator"), "nobody survives past the 6-hour ceiling"
