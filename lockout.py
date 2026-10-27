"""Shared account-lockout policy — one definition used by every tool (harmonization).

Policy (decided July 24, 2026, matching the strictest existing implementations —
ControversyGenerator and Inequality): after MAX_ATTEMPTS consecutive failures the
account locks with exponential backoff, starting at BASE_LOCK_SECONDS and doubling
per further failure, capped at MAX_LOCK_SECONDS. A successful login resets the
counter. Change the policy here and the whole fleet follows.

Two usage patterns:

1. DB-backed (tools with an educator/admin table — the Moral Mirror pattern).
   The table needs two columns:  failed_logins INT NOT NULL DEFAULT 0,
   locked_until DATETIME NULL.  In the login route:

       if is_locked(user.get("locked_until")):
           ...render "temporarily locked" error, do NOT check the password...
       if password_ok:
           ...UPDATE ... SET failed_logins=0, locked_until=NULL...
       else:
           fails, until = register_failure(user["failed_logins"])
           ...UPDATE ... SET failed_logins=fails, locked_until=until...

   Comparisons happen in Python against the current UTC time as a naive
   datetime (the DATETIME columns hold naive UTC) — never rely on the database
   clock for the check itself.

2. In-memory (the DB-less hub admin): use MemoryLockout. NOTE: per-process only —
   with N uvicorn workers an attacker gets N times the attempts before every
   worker has locked. Acceptable as brute-force throttling for a single low-value
   login form; not a substitute for the DB-backed variant where a DB exists.

Always key lockout to the ACCOUNT (email), not the IP: attackers rotate IPs,
and IP-keying lets one classroom NAT lock out a whole course.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

MAX_ATTEMPTS = 5           # failures before the first lock
BASE_LOCK_SECONDS = 60     # first lock: 1 minute
MAX_LOCK_SECONDS = 3600    # cap: 1 hour

LOCKED_MESSAGE = "Too many failed attempts. Account temporarily locked — try again later."


def _utcnow() -> datetime:
    """Naive UTC, what datetime.utcnow() returned. utcnow() warns from Python
    3.12 on and is going away (TO DO FL-097)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def register_failure(failed_logins_before: int, now: datetime | None = None) -> tuple[int, datetime | None]:
    """Return (new_failed_logins, locked_until_or_None) after one more failure."""
    fails = (failed_logins_before or 0) + 1
    if fails < MAX_ATTEMPTS:
        return fails, None
    lock_seconds = min(BASE_LOCK_SECONDS * (2 ** (fails - MAX_ATTEMPTS)), MAX_LOCK_SECONDS)
    return fails, (now or _utcnow()) + timedelta(seconds=lock_seconds)


def is_locked(locked_until: datetime | None, now: datetime | None = None) -> bool:
    return locked_until is not None and locked_until > (now or _utcnow())


def seconds_remaining(locked_until: datetime | None, now: datetime | None = None) -> int:
    if locked_until is None or not is_locked(locked_until, now):
        return 0
    return max(0, int((locked_until - (now or _utcnow())).total_seconds()))


class MemoryLockout:
    """Per-process lockout store for apps without a database (see module docstring)."""

    def __init__(self) -> None:
        self._state: dict[str, tuple[int, datetime | None]] = {}

    def is_locked(self, key: str, now: datetime | None = None) -> bool:
        _, until = self._state.get(key, (0, None))
        return is_locked(until, now)

    def register_failure(self, key: str, now: datetime | None = None) -> None:
        fails, _ = self._state.get(key, (0, None))
        self._state[key] = register_failure(fails, now)

    def reset(self, key: str) -> None:
        self._state.pop(key, None)
