"""Do a background side effect at most once, however many workers run the job.

Every tool runs its background jobs (the retention pass, PP's notification
loop, Layoff's hourly sweep) inside each uvicorn worker, and the workers start
them together after every restart. A job shaped "select what is not yet done,
do it, stamp it done" therefore runs twice whenever there are two workers: on
1 October 2026 Drawbridge mailed an educator the same retention warning twice,
0.17 s apart, and Controversy Generator's participant warning had the same
race with a worse result (each send rotates the deletion link, so the first
copy arrived dead). Whiteout had found and fixed it on 25 August; the fix
stayed in Whiteout.

The safe shape is CLAIM, ACT, RELEASE ON FAILURE:

    UPDATE t SET col = <mark> WHERE id = %s AND <col not yet marked>

The database lets exactly one caller change the row. That caller acts; every
other caller sees rowcount 0 and walks away. If the action fails, or raises,
the mark is put back so the next pass tries again.

It lives here, and every background mail in the fleet goes through it, so the
shape does not depend on how many workers a tool happens to run today. A tool
with one worker is not exempt: its worker count is one line in a unit file.

THREE KINDS OF MARK, because the fleet uses three:

  * a timestamp, "not yet marked" = IS NULL (the default; ``mark=NOW`` or
    ``mark=UTC_NOW``), e.g. ``educator_warned_at``;
  * a value, "not yet marked" = the column is not that value, e.g. PP's
    ``anonymization_warning_sent_for_deadline`` (marked with the deadline, so
    a postponed deadline is a new, unmarked one) or a boolean flag;
  * either of those over several rows at once (``keys`` a list), e.g. PP's
    batch of self-guided responses that one educator mail covers.

``get_db`` is the tool's connection factory, the same callable it hands to
``retention_heartbeat.record`` and ``audit``. The helper reads
``cursor.rowcount`` itself. That matters: several tools' own ``execute``
helpers return ``lastrowid``, which is 0 for every UPDATE, so a claim tested
through them reads as never won and the mail would never go out.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional, Sequence, Union

logger = logging.getLogger(__name__)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _SqlNow:
    def __init__(self, sql: str):
        self.sql = sql

    def __repr__(self) -> str:
        return self.sql


NOW = _SqlNow("NOW()")
UTC_NOW = _SqlNow("UTC_TIMESTAMP()")

Keys = Union[Any, Sequence[Any]]


def _ident(name: str) -> str:
    if not isinstance(name, str) or not _IDENT.match(name):
        raise ValueError("not a plain SQL identifier: %r" % (name,))
    return name


def _key_list(keys: Keys) -> list:
    if isinstance(keys, (list, tuple, set, frozenset)):
        out = list(keys)
    else:
        out = [keys]
    if not out:
        raise ValueError("no keys to claim")
    return out


def _run(get_db: Callable, sql: str, params: list) -> int:
    conn = get_db()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount
        finally:
            cur.close()
    finally:
        conn.close()


def claim(get_db: Callable, table: str, column: str, keys: Keys, *,
          mark: Any = NOW, key_column: str = "id") -> int:
    """Mark the row(s) as taken; return how many THIS call marked.

    0 means another caller had already marked them (or the rows are gone).
    With several keys a partial count is possible only if another caller
    claimed some of the same rows at the same moment; act on what you got.
    """
    t, c, k = _ident(table), _ident(column), _ident(key_column)
    ks = _key_list(keys)
    where_keys = "%s IN (%s)" % (k, ",".join(["%s"] * len(ks)))
    if isinstance(mark, _SqlNow):
        sql = "UPDATE %s SET %s = %s WHERE %s AND %s IS NULL" % (
            t, c, mark.sql, where_keys, c)
        params = ks
    else:
        # <=> is NULL-safe equality: an unmarked NULL row counts as "not this
        # value" and is claimable.
        sql = "UPDATE %s SET %s = %%s WHERE %s AND NOT (%s <=> %%s)" % (
            t, c, where_keys, c)
        params = [mark] + ks + [mark]
    return _run(get_db, sql, params)


def release(get_db: Callable, table: str, column: str, keys: Keys, *,
            restore: Any = None, key_column: str = "id") -> None:
    """Put the mark back to ``restore`` (NULL by default), re-arming the job."""
    t, c, k = _ident(table), _ident(column), _ident(key_column)
    ks = _key_list(keys)
    sql = "UPDATE %s SET %s = %%s WHERE %s IN (%s)" % (
        t, c, k, ",".join(["%s"] * len(ks)))
    _run(get_db, sql, [restore] + ks)


def once(get_db: Callable, table: str, column: str, keys: Keys,
         action: Callable[[], Any], *, mark: Any = NOW, restore: Any = None,
         key_column: str = "id",
         succeeded: Callable[[Any], bool] = bool) -> Optional[Any]:
    """Claim, run ``action()``, release unless it succeeded.

    Returns None when another caller holds the claim (nothing was done; that
    is not a failure and must not be counted as one). Otherwise returns what
    ``action`` returned. ``succeeded(result)`` decides whether the mark stays;
    by default any truthy result keeps it (True from a send, a count > 0 from
    a batch). If ``action`` raises, the mark is released and the error
    propagates.

    ``restore`` is what the column held before, for value marks whose
    previous state was not NULL (PP's previous deadline, a FALSE flag).

    With several keys, the action runs if ANY row was claimed. Two callers
    that selected the same set get all-or-nothing (row locks serialise the
    two UPDATEs). Only callers that selected overlapping but DIFFERENT sets,
    which needs a row to cross the job's time threshold in the milliseconds
    between their SELECTs, could each claim part and each act once.
    """
    if not claim(get_db, table, column, keys, mark=mark, key_column=key_column):
        return None
    ok = False
    try:
        result = action()
        ok = bool(succeeded(result))
        return result
    finally:
        if not ok:
            try:
                release(get_db, table, column, keys, restore=restore,
                        key_column=key_column)
            except Exception:
                # Logged, never raised over the action's own outcome. A failed
                # release leaves the row marked: the job is skipped, not
                # repeated, which is the safe direction for a mail.
                logger.exception("once: could not release %s.%s for %r",
                                 table, column, keys)
