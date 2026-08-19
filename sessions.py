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


# ── How long a session lives, by role (2026-08-19) ──────────────────────────
# Until now every backoffice session in the fleet lived exactly four hours,
# whoever held it. That single number was answering two different questions.
#
# An EDUCATOR holds a session for the length of a teaching day: they sign in
# before class, run an exercise, come back after a break to look at the
# results. Four hours expired in the middle of that often enough to be the
# thing people noticed about the tool. Their account can see and export their
# own classes' data — real, but bounded.
#
# An ADMIN (and the hub's OWNER) can reach every class in the tool, create and
# delete accounts, and change other people's roles. That session is the most
# valuable thing an attacker on a borrowed or shared machine could pick up,
# and it is used in short deliberate visits, not left open all day.
#
# So the two move in opposite directions: educators 6 hours, admins 3.
#
# THE CEILING. `MAX_SESSION_AGE` is the longest life any backoffice cookie may
# have, and it is what the signers are built with — a signature older than
# this is refused before anything else looks at it. The role-specific limit is
# then applied a second time, once the account row has been read, by
# `max_age_for(row['role'])`. It is done in that order on purpose: the role
# that decides the limit is the one in the DATABASE at this request, not the
# one that was true when the cookie was signed. Demoting an admin therefore
# lengthens their session and promoting an educator shortens it immediately,
# without depending on the epoch bump to have been wired up at that call site.
#
# The published cookie tables in `legal_conf.py` name both numbers. If you
# change one here, change it there in the same commit — `closing_audit.py`
# compares them and will fail the deploy if they drift.
EDUCATOR_SESSION_MAX_AGE = 60 * 60 * 6   # 6 hours
ADMIN_SESSION_MAX_AGE = 60 * 60 * 3      # 3 hours

#: The longest any backoffice session may live — build signers with this.
MAX_SESSION_AGE = EDUCATOR_SESSION_MAX_AGE

#: Roles that get the SHORTER session. Deliberately the same set as
#: `twofactor.REQUIRED_ROLES`: both answer "is this account privileged?", and
#: OWNER was missing from that one for three weeks because it was written out
#: by hand. Spellings differ across the fleet ("ADMIN" / "admin"), so the
#: comparison is case-insensitive.
PRIVILEGED_ROLES = ("ADMIN", "OWNER")


def is_privileged(role: Any) -> bool:
    """True for an admin/owner account, False for an educator.

    An unknown or missing role reads as NOT privileged, which gives it the
    longer session. That is the safe direction for a tool whose role column is
    absent or empty: the alternative — treating everything unrecognised as an
    admin — would cut ordinary educators to three hours the moment a spelling
    changed, which is a visible outage, while this errs towards the behaviour
    every account already had before today.
    """
    return str(role or "").strip().upper() in PRIVILEGED_ROLES


def max_age_for(role: Any) -> int:
    """Seconds a session for this role may live. Pass the role from the DB row."""
    return ADMIN_SESSION_MAX_AGE if is_privileged(role) else EDUCATOR_SESSION_MAX_AGE


def session_age_ok(signer: Any, raw: str, role: Any) -> bool:
    """Re-check an already-decoded cookie against the ROLE's own limit.

    The signer was built with `MAX_SESSION_AGE`, so a decoded cookie is only
    known to be younger than the ceiling. This asks the narrower question, and
    is a no-op for a role that gets the ceiling anyway.
    """
    limit = max_age_for(role)
    if limit >= MAX_SESSION_AGE:
        return True
    return signer.loads(raw, max_age=limit) is not None


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
