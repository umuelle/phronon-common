"""Instantly revocable admin sessions (TO DO A2) — one mechanism for the fleet.

THE PROBLEM
Admin sessions are signed cookies with an 8-hour life. Signed cookies are
stateless by design: the server can verify one without storing anything, which
is exactly why it cannot take one back. So changing a password, deactivating an
account or removing someone's admin rights left every session that person
already held fully working, for up to eight more hours. That is the wrong
behaviour for all three, and it is the *only* thing you can do after a password
leak — the reason people change passwords in the first place.

THE MECHANISM — an epoch, not a session table
Each admin row carries `session_epoch`, an integer. The number is copied into
the cookie when the session is issued, and checked against the row on every
request. Revoking is therefore one UPDATE:

    UPDATE <admins> SET session_epoch = session_epoch + 1 WHERE id = %s

Every cookie carrying the old number stops validating on its next request —
immediately, everywhere, on every device, with no sweep job and nothing to
expire.

WHY NOT A SESSIONS TABLE
The obvious design stores a row per session and deletes rows to revoke. It
costs a table, a write on every request (or stale `last_seen` data), a cleanup
job for abandoned rows, and a second thing that can fail while someone is
trying to log in. It buys exactly one capability this fleet has never asked
for: revoking ONE device while leaving another signed in, and showing a list of
active sessions. The epoch gives the whole of A2 — "cut off the sessions this
person already has" — for one integer column.

If per-device revocation is ever genuinely wanted, add the table then; the
epoch stays valid alongside it as the "revoke everything" switch.

WHAT MUST CALL revoke()
Anything that changes who someone is or what they may do:
  * a password change or reset (self-service AND admin-set)
  * deactivating or deleting an account
  * changing a role / admin rights
Each tool wires those points itself, because the account tables differ
(`admins` / `users` / `educators` / `facilitators`).

MIGRATION
    ALTER TABLE <table> ADD COLUMN session_epoch INT NOT NULL DEFAULT 0;
Existing cookies carry no epoch and are treated as epoch 0, which matches the
default — so adding the column does NOT log anyone out.
"""
from __future__ import annotations

from typing import Any, Optional

#: Copy-paste DDL. `<table>` is the tool's own admin table.
MIGRATION_SQL = (
    "ALTER TABLE {table} ADD COLUMN session_epoch INT NOT NULL DEFAULT 0;"
)

#: The revocation statement, for tools that want it ready-made.
REVOKE_SQL = "UPDATE {table} SET session_epoch = session_epoch + 1 WHERE id = %s"


def cookie_payload(admin_id: Any, epoch: int, **extra) -> dict:
    """The payload to sign into an admin session cookie.

    Kept as a dict with named keys so a tool can carry its own extras (a role,
    a display name) without colliding with these two.
    """
    payload = {"id": admin_id, "ep": int(epoch or 0)}
    payload.update(extra)
    return payload


def epoch_of(payload: Any) -> int:
    """The epoch inside a decoded cookie payload.

    A payload from before this feature has no epoch and reads as 0 — the same
    value the migration gives every existing row, so nobody is logged out by
    the upgrade itself.
    """
    if isinstance(payload, dict):
        try:
            return int(payload.get("ep") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def session_is_current(payload: Any, row_epoch: Optional[int]) -> bool:
    """True if the cookie's epoch still matches the account's.

    A cookie is refused when its epoch is anything other than the row's current
    value — lower means it was issued before a revocation. A missing row_epoch
    (column absent, or admin row gone) is treated as 0, so a tool that has not
    run the migration yet keeps working rather than locking everyone out.
    """
    try:
        current = int(row_epoch or 0)
    except (TypeError, ValueError):
        current = 0
    return epoch_of(payload) == current
