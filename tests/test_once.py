"""once.py: claim, act, release on failure.

This package's CI has no MySQL, so the table below is a dict behind a lock
that answers exactly the two UPDATE shapes once.py writes, with MySQL's
semantics (rowcount = rows CHANGED). Each tool proves the same thing against
its real database with two racing threads.
"""
from __future__ import annotations

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from phronon_common import once


class FakeTable:
    def __init__(self, rows):
        self.rows = dict(rows)          # key -> column value
        self.lock = threading.Lock()
        self.statements = []

    def get_db(self):
        table = self

        class Cursor:
            rowcount = -1

            def execute(self, sql, params):
                table.statements.append((sql, list(params)))
                with table.lock:
                    self.rowcount = table._apply(sql, list(params))

            def close(self):
                pass

        class Conn:
            def cursor(self):
                return Cursor()

            def commit(self):
                pass

            def close(self):
                pass

        return Conn()

    def _apply(self, sql, params):
        if "IS NULL" in sql:                      # claim with a timestamp
            keys = params
            new, cond = "now", lambda v: v is None
        elif "<=>" in sql:                        # claim with a value
            new, keys = params[0], params[1:-1]
            cond = lambda v: v != new
        else:                                     # release
            new, keys = params[0], params[1:]
            cond = lambda v: True
        changed = 0
        for k in keys:
            if k in self.rows and cond(self.rows[k]) and self.rows[k] != new:
                self.rows[k] = new
                changed += 1
        return changed


# ── The SQL ─────────────────────────────────────────────────────────────────

def test_a_timestamp_claim_only_takes_an_unmarked_row():
    t = FakeTable({7: None})
    assert once.claim(t.get_db, "classes", "educator_warned_at", 7) == 1
    sql, params = t.statements[-1]
    assert sql == ("UPDATE classes SET educator_warned_at = NOW() "
                   "WHERE id IN (%s) AND educator_warned_at IS NULL")
    assert params == [7]
    assert once.claim(t.get_db, "classes", "educator_warned_at", 7) == 0


def test_utc_now_is_available_for_tools_that_stamp_utc():
    t = FakeTable({1: None})
    once.claim(t.get_db, "participants", "retention_warned_at", 1, mark=once.UTC_NOW)
    assert "SET retention_warned_at = UTC_TIMESTAMP()" in t.statements[-1][0]


def test_a_value_claim_takes_a_row_marked_for_something_else():
    """PP marks the warning with the deadline it was sent for: a postponed
    deadline must be claimable again, the same deadline must not."""
    old, new = datetime(2026, 10, 1), datetime(2026, 10, 31)
    t = FakeTable({5: old})
    assert once.claim(t.get_db, "responses", "sent_for_deadline", 5, mark=new) == 1
    sql, params = t.statements[-1]
    assert "NOT (sent_for_deadline <=> %s)" in sql
    assert params == [new, 5, new]
    assert once.claim(t.get_db, "responses", "sent_for_deadline", 5, mark=new) == 0


def test_a_batch_claim_counts_the_rows_it_took():
    t = FakeTable({1: 0, 2: 0, 3: 1})
    assert once.claim(t.get_db, "responses", "notified", [1, 2, 3], mark=1) == 2


@pytest.mark.parametrize("bad", ["classes; DROP TABLE x", "a b", "", "1col", None])
def test_identifiers_are_never_interpolated_unchecked(bad):
    t = FakeTable({1: None})
    with pytest.raises(ValueError):
        once.claim(t.get_db, bad, "col", 1)
    with pytest.raises(ValueError):
        once.claim(t.get_db, "t", bad, 1)
    with pytest.raises(ValueError):
        once.release(t.get_db, "t", "col", 1, key_column=bad)


def test_an_empty_batch_is_refused():
    with pytest.raises(ValueError):
        once.claim(FakeTable({}).get_db, "t", "c", [])


def test_rowcount_comes_from_the_cursor_not_lastrowid():
    """Several tools' execute() returns lastrowid, 0 for every UPDATE. once.py
    must never route through those."""
    import inspect
    assert "lastrowid" not in inspect.getsource(once._run)


# ── once() ──────────────────────────────────────────────────────────────────

def test_two_racing_callers_act_once():
    t = FakeTable({7: None})
    acted = []

    def send():
        time.sleep(0.05)
        acted.append(1)
        return True

    start = threading.Barrier(4)

    def worker(_):
        start.wait()
        return once.once(t.get_db, "classes", "educator_warned_at", 7, send)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(worker, range(4)))
    assert len(acted) == 1
    assert sorted(results, key=lambda r: r is None) == [True, None, None, None]
    assert t.rows[7] == "now"


def test_a_failed_action_re_arms():
    t = FakeTable({7: None})
    assert once.once(t.get_db, "classes", "w", 7, lambda: False) is False
    assert t.rows[7] is None


def test_a_raising_action_re_arms_and_the_error_propagates():
    t = FakeTable({7: None})

    def boom():
        raise RuntimeError("template broke")

    with pytest.raises(RuntimeError):
        once.once(t.get_db, "classes", "w", 7, boom)
    assert t.rows[7] is None


def test_release_restores_the_previous_value():
    old, new = datetime(2026, 10, 1), datetime(2026, 10, 31)
    t = FakeTable({5: old})
    once.once(t.get_db, "responses", "sent_for", 5, lambda: False, mark=new, restore=old)
    assert t.rows[5] == old


def test_a_count_result_keeps_the_mark_when_positive():
    t = FakeTable({3: None, 4: None})
    assert once.once(t.get_db, "quizes", "p", 3, lambda: 2) == 2
    assert t.rows[3] == "now"
    assert once.once(t.get_db, "quizes", "p", 4, lambda: 0) == 0
    assert t.rows[4] is None


def test_a_custom_success_rule():
    t = FakeTable({1: None})
    result = once.once(t.get_db, "t", "c", 1, lambda: (True, "250 OK"),
                       succeeded=lambda r: r[0])
    assert result == (True, "250 OK") and t.rows[1] == "now"


def test_a_failed_release_is_logged_not_raised(caplog):
    t = FakeTable({1: None})
    calls = {"n": 0}
    real = t.get_db

    def flaky_get_db():
        calls["n"] += 1
        if calls["n"] == 2:             # the release
            raise RuntimeError("db went away")
        return real()

    assert once.once(flaky_get_db, "t", "c", 1, lambda: False) is False
    assert "could not release" in caplog.text
