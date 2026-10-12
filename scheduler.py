"""The background clock: periodic jobs in one daemon thread per process.

WHAT THE TOOLS HAD (checked 12 October 2026, FL-098 point 6). Eight of the
nine services run a background clock; the hub has none. Each tool wrote its
own: a ``while True`` loop in a daemon thread, its own sleep, its own guard.

  tool                 jobs (first run, then every)              not started when
  Controversy Gen.     session cleanup (after 1 h, 1 h);         CG_SKIP_BACKGROUND=1
                       retention (after 60 s, 24 h)              (+ boot check, retention only)
  Drawbridge           retention (at once, 24 h)                 DB_SKIP_BACKGROUND=1, boot check
  Inequality           retention (after 30 s, 1 h)               pytest imported, boot check
  Layoff               retention (after 30 s, 1 h)               pytest imported, boot check
  Moral Mirror         retention (at once, 24 h)                 MM_SKIP_BACKGROUND=1, boot check
  Orgsim               retention (after 30 s, 1 h)               pytest imported, boot check
  Polarity Profiler    retention (at once, 1 h)                  DB_SKIP_BACKGROUND=1, boot check
  Whiteout             retention (at once, 24 h)                 WHITEOUT_SKIP_BACKGROUND=1, boot check

The boot check is ``PHRONON_BOOT_CHECK=1``: the deploy starts the new version
once against the live database only to see /health answer, and on 25
September 2026 a clock that ran from there consolidated a Whiteout class
hours early, twice. The deploy fails a tool whose boot log says the clock
started (deploy.sh greps for "clock started" and similar). The skip switches
keep the clock out of test runs and the browser journey; the preview sets
the boot check. None of the copies has jitter: the first-run delay is the
only staggering. Every job catches its own exceptions, logs them and sleeps
on; the retention jobs stamp ``retention_heartbeat`` only after a pass that
did not raise (FL-050).

Every service runs ``uvicorn --workers 2``, so every clock runs twice, once in
each worker process. That stays so: the jobs are already safe to run twice
(``phronon_common.once`` claims each mail, the retention steps are
idempotent UPDATEs and DELETEs, the heartbeat is a one-row upsert), and a
clock that runs in one worker only would stop whenever that worker died.
This module does not replace those locks.

WHAT THE SHARED ONE DOES
  * ``Scheduler(name, skip_env=..., skip_under_pytest=...)`` and ``add(job,
    every=, first_after=)``. Nothing runs at import or at construction;
    ``start()`` is the one call that starts a thread, at the place in app.py
    where the tool starts its thread today.
  * ``start()`` refuses, and says so in the log, under the boot check, when
    any of the tool's skip variables is "1" (the tools keep their names), or
    under pytest if the tool asks for that. It never starts a second thread
    for the same clock in one process. Its start line contains "clock
    started", so the deploy's tripwire keeps working whatever a job is
    called; its refusal lines never do.
  * One daemon thread runs every job of the process in turn. A job's next
    run is ``every`` seconds after its previous run FINISHED, as the copies'
    ``sleep`` after the pass did. A job that raises is logged with
    ``logger.exception`` and runs again on schedule; the thread does not die.
  * ``heartbeat=get_db`` on a job stamps ``retention_heartbeat.record`` after
    a run that did not raise, with the job's return value as the detail when
    it is a string, and never after one that raised: the FL-050 contract,
    written once.
  * Tests: ``run_now(name)`` runs one job synchronously, heartbeat included,
    and lets its exception through; ``run_due(now)`` is one tick of the loop
    against a given clock; ``stop()`` ends the thread.

Standard library only (plus retention_heartbeat, itself stdlib only).
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional, Union

from phronon_common import retention_heartbeat

logger = logging.getLogger(__name__)

BOOT_CHECK_ENV = "PHRONON_BOOT_CHECK"

# Clocks running in this process, by name, so an app module imported twice
# (as "app" and as "__main__", or by a script) cannot start a second thread.
_running: dict = {}
_running_lock = threading.Lock()


def _span(seconds: float) -> str:
    if seconds and seconds % 3600 == 0:
        return "%d h" % (seconds // 3600)
    if seconds and seconds % 60 == 0:
        return "%d min" % (seconds // 60)
    return "%g s" % seconds


@dataclass
class Job:
    name: str
    func: Callable[[], Any]
    every: float
    first_after: float = 0.0
    heartbeat: Optional[Callable] = None
    next_due: float = 0.0
    runs: int = 0
    failures: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def describe(self) -> str:
        first = "at once" if not self.first_after else "first after %s" % _span(self.first_after)
        return "%s every %s, %s" % (self.name, _span(self.every), first)


class Scheduler:
    """A tool's background clock. See the module docstring."""

    def __init__(self, name: str, *, skip_env: Union[str, Iterable[str]] = (),
                 skip_under_pytest: bool = False,
                 clock: Callable[[], float] = time.monotonic):
        self.name = name
        self.skip_env = (skip_env,) if isinstance(skip_env, str) else tuple(skip_env)
        self.skip_under_pytest = skip_under_pytest
        self.clock = clock
        self.jobs: dict = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ── registering ─────────────────────────────────────────────────────────
    def add(self, name: str, func: Callable[[], Any], *, every: float,
            first_after: float = 0.0, heartbeat: Optional[Callable] = None) -> Job:
        """Register ``func`` to run every ``every`` seconds, the first time
        ``first_after`` seconds after ``start()``. ``heartbeat`` is the tool's
        connection factory when the job is the retention pass."""
        if name in self.jobs:
            raise ValueError("job %r is already registered" % name)
        if every <= 0 or first_after < 0:
            raise ValueError("every must be positive and first_after not negative")
        if self.running:
            raise RuntimeError("add jobs before start()")
        job = Job(name, func, float(every), float(first_after), heartbeat)
        job.next_due = self.clock() + job.first_after
        self.jobs[name] = job
        return job

    # ── running one job ────────────────────────────────────────────────────
    def _execute(self, job: Job) -> Any:
        """Run once; stamp the heartbeat only if it returned. Raises."""
        try:
            result = job.func()
        except Exception:
            job.failures += 1
            raise
        finally:
            job.runs += 1
            job.next_due = self.clock() + job.every
        if job.heartbeat is not None:
            retention_heartbeat.record(job.heartbeat,
                                       result if isinstance(result, str) else "")
        return result

    def run_now(self, name: str) -> Any:
        """Run one job synchronously and return what it returned.

        For tests and for a tool's own "run it now" path. Its exception
        propagates; the heartbeat is stamped as on a scheduled run."""
        job = self.jobs[name]
        with job.lock:
            return self._execute(job)

    def run_due(self, now: Optional[float] = None) -> list:
        """One tick: run every job that is due, in the order they were added.

        Never raises. Returns the names of the jobs that ran."""
        ran = []
        for job in list(self.jobs.values()):
            if self._stop.is_set():
                break
            if job.next_due > (self.clock() if now is None else now):
                continue
            if not job.lock.acquire(blocking=False):
                continue                 # already running (a run_now)
            try:
                self._execute(job)
            except Exception:
                logger.exception("background clock %s: job %s failed; next run in %s",
                                 self.name, job.name, _span(job.every))
            finally:
                job.lock.release()
            ran.append(job.name)
        return ran

    def seconds_to_next(self) -> float:
        if not self.jobs:
            return 60.0
        return max(0.0, min(j.next_due for j in self.jobs.values()) - self.clock())

    # ── the thread ──────────────────────────────────────────────────────────
    def refusal(self) -> Optional[str]:
        """Why ``start()`` would not start the thread here, or None."""
        if os.environ.get(BOOT_CHECK_ENV) == "1":
            return "boot check"
        for var in self.skip_env:
            if os.environ.get(var) == "1":
                return "%s=1" % var
        if self.skip_under_pytest and "pytest" in sys.modules:
            return "under pytest"
        if not self.jobs:
            return "no jobs registered"
        return None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start the daemon thread unless a switch says not to. True if started."""
        reason = self.refusal()
        if reason is not None:
            # Worded so the deploy's tripwire ("clock started", ...) cannot match.
            logger.info("%s: background clock not started (%s)", reason, self.name)
            return False
        with _running_lock:
            other = _running.get(self.name)
            if other is not None and other[0] == os.getpid() and other[1].running:
                logger.warning("background clock %s is already running in this process; "
                               "not starting a second one", self.name)
                return False
            self._stop.clear()
            start = self.clock()
            for job in self.jobs.values():
                job.next_due = start + job.first_after
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="phronon-clock-%s" % self.name)
            self._thread.start()
            _running[self.name] = (os.getpid(), self)
        logger.info("background clock started (%s): %s", self.name,
                    "; ".join(j.describe() for j in self.jobs.values()))
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_due()
            self._stop.wait(self.seconds_to_next())

    def stop(self, timeout: float = 10.0) -> None:
        """End the thread after the job it is running (tests, shutdown)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)
        with _running_lock:
            if _running.get(self.name, (None, None))[1] is self:
                del _running[self.name]
