"""One test run per test database at a time (FL-085, 4 October 2026).

WHY THIS EXISTS
A tool's suite writes to its `<db>_test` schema. On the owner's Mac so do
`server-ops/common_candidate_matrix.py`, the browser gate (deploy step 1d),
`coverage_diagnostic.py` and `mutation_probe.py`, and several AI sessions run
suites at the same time. Session workspaces separate their git checkouts but
not their databases, and nothing made two runs wait for each other. Two Layoff
suites started together failed 9 to 12 tests each, a different set every time,
and each passed on a rerun: exactly what a flaky test looks like, and a session
spent an hour chasing one.

THE LOCK
A MySQL named lock, `phronon-test-run.<database>`, held by a connection of its
own for the life of the pytest process. MySQL releases it when that
connection closes, so a run that is killed never leaves it behind. Being the
database's lock rather than a file's, it holds across users (the server runs
suites as several service users) and needs no shared directory. CI gives
every job its own MySQL, so there it is always free.

A second run WAITS and says so, up to `PHRONON_TEST_RUN_WAIT` seconds (default
600). When the wait runs out, it stops before its first test, red, and says
why. A run with no database named (DB_NAME unset), or none it can reach, runs
as before: the tests that need a database report that themselves.

HOW A TOOL USES IT, in tests/conftest.py:

    from phronon_common.testing import run_lock

    def pytest_sessionstart(session):
        run_lock.hold_the_test_database(session)

`server-ops/fleet_testkit_check.py` refuses a tool whose conftest does not.
The browser gate takes the same lock by name: it runs in a venv of its own,
without this package, so it spells the name out (`lock_name` here is the
reference, and a server-ops test compares the two).

No pytest import here (see __init__.py). The function takes the session
pytest hands the hook and stops the run with that session's own `Interrupted`.
"""
from __future__ import annotations

import os
import sys
import time

PREFIX = "phronon-test-run."
DEFAULT_WAIT = 600          # seconds; a full suite takes 35 to 90
_SLICE = 2                  # one GET_LOCK call never blocks longer than this
_NOTE_EVERY = 60

#: database -> the connection holding its lock, kept open until the process ends
_held: dict = {}


def lock_name(database: str) -> str:
    """The MySQL lock for one test database (MySQL caps a lock name at 64)."""
    return (PREFIX + database)[:64]


def _first(cur):
    row = cur.fetchone()
    return row[0] if row else None


def _get(cur, name: str, seconds: int) -> bool:
    cur.execute("SELECT GET_LOCK(%s, %s)", (name, seconds))
    return _first(cur) == 1


def take(conn, database: str, wait: int = DEFAULT_WAIT, say=print) -> float:
    """Hold the run lock for `database` on `conn`, an open connection that the
    caller keeps open for as long as the lock must hold. Returns how many
    seconds it waited. Raises TimeoutError after `wait` seconds.

    The wait is taken in short slices: a connector whose read timeout is
    shorter than the wait would otherwise drop the connection mid-wait, and the
    slices let the waiting run say it is still there.
    """
    name = lock_name(database)
    cur = conn.cursor()
    if _get(cur, name, 0):
        return 0.0
    cur.execute("SELECT IS_USED_LOCK(%s)", (name,))
    holder = _first(cur)
    say(f"Another test run is using {database} (MySQL connection {holder}). "
        f"This run waits for it to finish, for up to {wait} s.")
    started = time.monotonic()
    next_note = _NOTE_EVERY
    while True:
        waited = time.monotonic() - started
        if waited >= wait:
            raise TimeoutError(
                f"Another test run held {database} for {wait} s, so this run "
                f"stopped before its first test. Find the other run with: "
                f"ps -ax -o pid,etime,command | grep '[p]ytest'. "
                f"PHRONON_TEST_RUN_WAIT sets how long to wait (FL-085).")
        if _get(cur, name, max(1, min(_SLICE, int(wait - waited)))):
            say(f"The other run on {database} has finished; this run starts "
                f"after {waited:.0f} s of waiting.")
            return waited
        if waited >= next_note:
            say(f"Still waiting for {database} ({waited:.0f} s).")
            next_note += _NOTE_EVERY


def _wait_from(env) -> int:
    try:
        return max(1, int(env.get("PHRONON_TEST_RUN_WAIT", "")))
    except ValueError:
        return DEFAULT_WAIT


def _sayer(session):
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        def say(message):
            reporter.write_line(message, yellow=True)
            reporter._tw.flush()
        return say
    return lambda message: print(message, file=sys.stderr, flush=True)


def hold_the_test_database(session, environ=None) -> bool:
    """For a conftest's `pytest_sessionstart`: hold the lock on the database
    this run's DB_* settings name, for the rest of the process. Returns True
    when it holds it, False when there is no database to hold. A run that
    waits too long is stopped with `session.Interrupted`."""
    env = os.environ if environ is None else environ
    database = env.get("DB_NAME", "")
    if not database:
        return False
    if database in _held:
        return True
    try:
        import mysql.connector
    except ImportError:
        return False
    try:
        conn = mysql.connector.connect(
            host=env.get("DB_HOST") or "127.0.0.1",
            port=int(env.get("DB_PORT") or 3306),
            user=env.get("DB_USER", ""),
            password=env.get("DB_PASSWORD", ""),
            connection_timeout=5,
            autocommit=True,
        )
    except Exception:  # noqa: BLE001 — no reachable database: nothing to share
        return False
    say = _sayer(session)
    try:
        take(conn, database, _wait_from(env), say)
    except TimeoutError as exc:
        conn.close()
        # pytest's terminal reporter prints this as "! Interrupted: … !" and
        # exits with 2 (INTERRUPTED); test_run_lock.py runs a real pytest to
        # prove both.
        raise session.Interrupted(str(exc)) from None
    _held[database] = conn
    return True
