"""The lockout clock is naive UTC without datetime.utcnow() (TO DO FL-097).

utcnow() warns from Python 3.12 on and is deprecated; the fleet's move off
3.10 needs it gone. The DATETIME columns hold naive UTC, so the replacement
must stay naive: an aware value compared with a column's value would raise.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import lockout  # noqa: E402


class _NoUtcnow(datetime):
    @classmethod
    def utcnow(cls):
        raise AssertionError("lockout called datetime.utcnow()")


def test_the_lock_runs_from_now_in_naive_utc(monkeypatch):
    monkeypatch.setattr(lockout, "datetime", _NoUtcnow)
    fails, until = lockout.register_failure(lockout.MAX_ATTEMPTS - 1)
    assert fails == lockout.MAX_ATTEMPTS and until.tzinfo is None
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert timedelta(seconds=55) < until - now <= timedelta(seconds=lockout.BASE_LOCK_SECONDS)
    assert lockout.is_locked(until)
    assert 0 < lockout.seconds_remaining(until) <= lockout.BASE_LOCK_SECONDS
    memory = lockout.MemoryLockout()
    for _ in range(lockout.MAX_ATTEMPTS):
        memory.register_failure("a@example.org")
    assert memory.is_locked("a@example.org")
