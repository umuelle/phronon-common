"""The shared audit trail (FL-002, 12 August 2026).

No database: a fake connection records what SQL would have run. What these pin:

  * record() NEVER raises — a failed audit INSERT must not turn "the class was
    deleted" into a 500 the educator sees;
  * the trail prunes itself on write, at most once per day per process — this
    is what keeps the 12-month promise in the four tools that have no
    background retention worker;
  * client_ip is rate_limit's — ONE answer to "whose address is this", with
    the trusted-proxy rule that stops a caller writing its own address into
    the log.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import audit  # noqa: E402


class FakeCursor:
    def __init__(self, log, fail=False):
        self.log, self.fail, self.rowcount = log, fail, 3

    def execute(self, sql, params=None):
        if self.fail:
            raise RuntimeError("db down")
        self.log.append((" ".join(sql.split()), params))

    def close(self):
        pass


class FakeConn:
    def __init__(self, log, fail=False):
        self.log, self.fail, self.committed = log, fail, False

    def cursor(self):
        return FakeCursor(self.log, self.fail)

    def commit(self):
        self.committed = True

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _reset_prune_throttle():
    audit._last_prune_monotonic = None
    yield
    audit._last_prune_monotonic = None


def test_record_writes_the_row():
    log = []
    audit.record(lambda: FakeConn(log), "class_deleted",
                 admin_id=7, admin_email="a@b.c", subject="ABC123",
                 details={"n": 2}, ip="203.0.113.9")
    inserts = [s for s, _ in log if s.startswith("INSERT")]
    assert len(inserts) == 1
    assert log[0][1][0] == "class_deleted"
    assert log[0][1][2] == "a@b.c"


def test_record_never_raises():
    """The whole contract: a broken database must not break the audited action."""
    audit.record(lambda: FakeConn([], fail=True), "login_success")
    audit.record(lambda: (_ for _ in ()).throw(RuntimeError("no conn")), "login_success")


def test_a_write_prunes_but_only_once_per_day():
    log = []
    for _ in range(3):
        audit.record(lambda: FakeConn(log), "login_success")
    deletes = [s for s, _ in log if s.startswith("DELETE")]
    assert len(deletes) == 1, "the self-prune must be throttled, not per-write"
    assert "INTERVAL %s DAY" in deletes[0]


def test_prune_uses_the_published_retention():
    log = []
    audit.prune(lambda: FakeConn(log))
    assert log[0][1] == (audit.RETENTION_DAYS,)
    assert audit.RETENTION_DAYS == 365, (
        "the retention window is PUBLISHED in every privacy notice and the "
        "Art. 30 record — change all of them together, never this alone"
    )


def test_client_ip_is_the_shared_one():
    """One answer to 'whose address is this' — not a second copy here."""
    from phronon_common.rate_limit import client_ip as rl_client_ip
    assert audit.client_ip is rl_client_ip


def test_vocabulary_covers_what_the_notice_claims():
    """The privacy notice names the categories; the vocabulary must have them.
    (Sign-ins, password changes, account create/delete, class data.)"""
    for needed in ("login_success", "login_failed", "password_changed",
                   "admin_created", "admin_deleted", "class_deleted",
                   "class_anonymised"):
        assert needed in audit.ACTIONS
