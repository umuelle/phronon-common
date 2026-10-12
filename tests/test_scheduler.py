"""scheduler.py: the background clock the eight tools each wrote for themselves.

Behaviour, not source: a thread starts or does not, a job runs or does not, a
failing job is logged and runs again, the heartbeat row is written or not.
The deploy's boot-check tripwire is the regex deploy.sh greps the boot log
with; the clock's own log lines are checked against it.
"""
from __future__ import annotations

import logging
import re
import threading
import time

import pytest

from phronon_common import scheduler as S

# server-ops/deploy.sh, the boot check: a log line matching this fails the deploy.
DEPLOY_TRIPWIRE = re.compile(
    r"retention pass|sweep started|clock started|Started the retention clock|retention thread",
    re.IGNORECASE)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeDb:
    """Records what retention_heartbeat.record writes."""

    def __init__(self):
        self.writes = []

    def __call__(self):
        db = self

        class Cursor:
            def execute(self, sql, params):
                db.writes.append((sql, params))

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


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (S.BOOT_CHECK_ENV, "WHITEOUT_SKIP_BACKGROUND", "DB_SKIP_BACKGROUND"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def clocks():
    made = []
    yield made
    for sched in made:
        sched.stop(timeout=5)


def _wait_for(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_nothing_runs_at_construction_or_registration():
    calls = []
    before = threading.active_count()
    sched = S.Scheduler("t-idle")
    sched.add("retention", lambda: calls.append(1), every=3600)
    assert calls == [] and not sched.running
    assert threading.active_count() == before


def test_the_boot_check_keeps_the_clock_off_and_says_so_without_tripping_the_deploy(
        monkeypatch, caplog):
    monkeypatch.setenv(S.BOOT_CHECK_ENV, "1")
    calls = []
    sched = S.Scheduler("t-boot", skip_env="WHITEOUT_SKIP_BACKGROUND")
    sched.add("retention", lambda: calls.append(1), every=3600)
    with caplog.at_level(logging.INFO, logger="phronon_common.scheduler"):
        assert sched.start() is False
    time.sleep(0.05)
    assert calls == [] and not sched.running
    text = caplog.text
    assert "boot check: background clock not started" in text
    assert not DEPLOY_TRIPWIRE.search(text)


@pytest.mark.parametrize("skip_env", ["WHITEOUT_SKIP_BACKGROUND",
                                      ("MM_SKIP_BACKGROUND", "WHITEOUT_SKIP_BACKGROUND")])
def test_the_tools_own_skip_switches_keep_working(monkeypatch, caplog, skip_env):
    monkeypatch.setenv("WHITEOUT_SKIP_BACKGROUND", "1")
    sched = S.Scheduler("t-skip", skip_env=skip_env)
    sched.add("retention", lambda: None, every=3600)
    with caplog.at_level(logging.INFO, logger="phronon_common.scheduler"):
        assert sched.start() is False
    assert "WHITEOUT_SKIP_BACKGROUND=1" in caplog.text
    assert not DEPLOY_TRIPWIRE.search(caplog.text)


def test_a_switch_set_to_anything_but_1_does_not_skip(monkeypatch, clocks):
    monkeypatch.setenv("DB_SKIP_BACKGROUND", "0")
    sched = S.Scheduler("t-zero", skip_env="DB_SKIP_BACKGROUND")
    clocks.append(sched)
    sched.add("retention", lambda: None, every=3600)
    assert sched.start() is True


def test_skip_under_pytest_for_the_tools_that_asked_for_it():
    sched = S.Scheduler("t-pytest", skip_under_pytest=True)
    sched.add("retention", lambda: None, every=3600)
    assert sched.refusal() == "under pytest"
    assert sched.start() is False


def test_start_runs_the_job_in_a_daemon_thread_and_trips_the_deploy_check(caplog, clocks):
    ran = threading.Event()
    sched = S.Scheduler("t-start")
    clocks.append(sched)
    sched.add("retention", ran.set, every=3600)
    with caplog.at_level(logging.INFO, logger="phronon_common.scheduler"):
        assert sched.start() is True
    assert ran.wait(5)
    assert sched._thread.daemon
    # A clock that starts during a boot check must still fail the deploy.
    assert DEPLOY_TRIPWIRE.search(caplog.text)
    assert "retention every 1 h, at once" in caplog.text


def test_a_failing_job_is_logged_and_runs_again(caplog, clocks):
    outcomes = iter([RuntimeError("database gone"), None, None])
    done = threading.Event()

    def job():
        outcome = next(outcomes, None)
        if outcome is not None:
            raise outcome
        done.set()

    sched = S.Scheduler("t-fail")
    clocks.append(sched)
    j = sched.add("retention", job, every=0.05)
    with caplog.at_level(logging.ERROR, logger="phronon_common.scheduler"):
        sched.start()
        assert done.wait(5)
    assert sched.running
    assert j.failures == 1 and j.runs >= 2
    failed = [r for r in caplog.records if "job retention failed" in r.getMessage()]
    assert failed and failed[0].exc_info is not None


def test_one_clock_per_process(clocks, caplog):
    first = S.Scheduler("t-same")
    clocks.append(first)
    first.add("retention", lambda: None, every=3600)
    second = S.Scheduler("t-same")
    clocks.append(second)
    second.add("retention", lambda: None, every=3600)
    assert first.start() is True
    with caplog.at_level(logging.WARNING, logger="phronon_common.scheduler"):
        assert second.start() is False
    assert "already running" in caplog.text
    first.stop()
    assert second.start() is True          # after a stop, a new one may start


def test_first_run_delay_and_interval_after_the_run_finished():
    clock = FakeClock()
    sched = S.Scheduler("t-tick", clock=clock)
    calls = []
    sched.add("cleanup", lambda: calls.append("cleanup"), every=3600, first_after=3600)
    sched.add("retention", lambda: calls.append("retention"), every=86400, first_after=60)
    assert sched.run_due() == []
    clock.now += 60
    assert sched.run_due() == ["retention"]
    assert sched.seconds_to_next() == 3540
    clock.now += 3540
    assert sched.run_due() == ["cleanup"]
    clock.now += 3600
    assert sched.run_due() == ["cleanup"]
    assert calls == ["retention", "cleanup", "cleanup"]


def test_run_due_never_raises_and_reschedules_a_failed_job():
    clock = FakeClock()
    sched = S.Scheduler("t-due", clock=clock)

    def boom():
        raise ValueError("no")

    job = sched.add("retention", boom, every=3600)
    assert sched.run_due() == ["retention"]
    assert job.failures == 1 and job.next_due == clock.now + 3600


def test_the_heartbeat_is_stamped_after_a_pass_that_returned_and_never_after_one_that_raised():
    db = FakeDb()
    sched = S.Scheduler("t-heart")
    outcome = {"raise": False}

    def retention_pass():
        if outcome["raise"]:
            raise RuntimeError("half done")
        return "warned=2, anonymised=1"

    sched.add("retention", retention_pass, every=3600, heartbeat=db)
    assert sched.run_now("retention") == "warned=2, anonymised=1"
    assert len(db.writes) == 1
    sql, params = db.writes[0]
    assert "retention_runs" in sql and params == ["warned=2, anonymised=1"]

    outcome["raise"] = True
    with pytest.raises(RuntimeError):
        sched.run_now("retention")              # tests see the exception
    sched.run_due(now=float("inf"))             # the thread's path swallows it
    assert len(db.writes) == 1                  # and neither stamped


def test_a_job_without_a_string_result_stamps_an_empty_detail():
    db = FakeDb()
    sched = S.Scheduler("t-heart2")
    sched.add("retention", lambda: {"warned": 0}, every=3600, heartbeat=db)
    sched.run_now("retention")
    assert db.writes[0][1] == [""]


def test_registration_is_checked(clocks):
    sched = S.Scheduler("t-reg")
    clocks.append(sched)
    sched.add("retention", lambda: None, every=3600)
    with pytest.raises(ValueError):
        sched.add("retention", lambda: None, every=3600)
    with pytest.raises(ValueError):
        sched.add("other", lambda: None, every=0)
    sched.start()
    with pytest.raises(RuntimeError):
        sched.add("late", lambda: None, every=60)


def test_no_jobs_no_thread():
    assert S.Scheduler("t-empty").start() is False


def test_stop_ends_the_thread(clocks):
    sched = S.Scheduler("t-stop")
    sched.add("retention", lambda: None, every=3600)
    assert sched.start()
    sched.stop(timeout=5)
    assert not sched.running
