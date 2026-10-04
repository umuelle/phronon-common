"""testing/run_lock.py: one test run per test database at a time (FL-085).

The lock is MySQL's, so these tests take it against the real server (the
`test_db` fixture; this package's CI has MySQL and may not skip them). Lock
names are plain strings: each test locks a database name of its own, which
need not exist, so nothing here can make a real suite wait.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from phronon_common.testing import run_lock

PKG = Path(__file__).resolve().parents[1]


class _Interrupted(KeyboardInterrupt):
    pass


class FakeSession:
    """What the hook is handed, as far as run_lock reads it."""
    Interrupted = _Interrupted

    def __init__(self):
        self.config = SimpleNamespace(pluginmanager=SimpleNamespace(get_plugin=lambda name: None))


@pytest.fixture
def lock_env(test_db):
    """DB_* for a database name no real run uses, and the lock released after."""
    database = f"{os.environ['DB_NAME']}_lock_{uuid.uuid4().hex[:8]}"
    env = {k: os.environ[k] for k in ("DB_HOST", "DB_USER", "DB_PASSWORD") if k in os.environ}
    env["DB_NAME"] = database
    yield env
    held = run_lock._held.pop(database, None)
    if held is not None:
        held.close()


def _holder(get_db, database):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT GET_LOCK(%s, 0)", (run_lock.lock_name(database),))
    assert cur.fetchone()[0] == 1
    return conn


def _free(get_db, database, seconds=0) -> bool:
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK(%s, %s)", (run_lock.lock_name(database), seconds))
        got = cur.fetchone()[0] == 1
        cur.execute("SELECT RELEASE_LOCK(%s)", (run_lock.lock_name(database),))
        cur.fetchall()
        return got
    finally:
        conn.close()


def test_the_lock_is_named_after_the_database_and_fits_mysql():
    assert run_lock.lock_name("layoff_exercise_test") == "phronon-test-run.layoff_exercise_test"
    assert len(run_lock.lock_name("x" * 100)) == 64


def test_a_run_with_no_database_named_takes_no_lock():
    assert run_lock.hold_the_test_database(FakeSession(), environ={}) is False


def test_an_unreachable_database_is_not_this_lock_s_business():
    """The suite's own database tests report a missing database; the lock must
    not turn it into a different failure, or into a wait."""
    started = time.monotonic()
    env = {"DB_NAME": "nothing_test", "DB_HOST": "127.0.0.1", "DB_PORT": "1", "DB_USER": "x"}
    assert run_lock.hold_the_test_database(FakeSession(), environ=env) is False
    assert time.monotonic() - started < 10


def test_a_run_holds_its_database_until_it_ends(test_db, lock_env):
    assert run_lock.hold_the_test_database(FakeSession(), environ=lock_env) is True
    assert not _free(test_db, lock_env["DB_NAME"]), "a second run could start beside this one"
    # Asked twice in one process (pytest.main called again), it is the same lock.
    assert run_lock.hold_the_test_database(FakeSession(), environ=lock_env) is True
    run_lock._held.pop(lock_env["DB_NAME"]).close()        # the process ends
    assert _free(test_db, lock_env["DB_NAME"])


def test_a_second_run_waits_says_so_and_stops_red(test_db, lock_env, capsys):
    holder = _holder(test_db, lock_env["DB_NAME"])
    try:
        started = time.monotonic()
        with pytest.raises(_Interrupted, match="stopped before its first test"):
            run_lock.hold_the_test_database(
                FakeSession(), environ={**lock_env, "PHRONON_TEST_RUN_WAIT": "2"})
        waited = time.monotonic() - started
    finally:
        holder.close()
    assert 2 <= waited < 8, waited
    assert f"Another test run is using {lock_env['DB_NAME']}" in capsys.readouterr().err
    assert lock_env["DB_NAME"] not in run_lock._held


def test_a_second_run_starts_when_the_first_one_ends(test_db, lock_env, capsys):
    holder = _holder(test_db, lock_env["DB_NAME"])
    threading.Timer(2.5, holder.close).start()
    assert run_lock.hold_the_test_database(
        FakeSession(), environ={**lock_env, "PHRONON_TEST_RUN_WAIT": "30"}) is True
    assert "has finished; this run starts after" in capsys.readouterr().err


def test_a_killed_run_leaves_no_lock_behind(test_db, lock_env):
    """The point of a lock held by a connection: kill -9 a run and the next one
    starts at once, with nobody to clean up."""
    holder = subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(f"""
            import time, mysql.connector
            c = mysql.connector.connect(host={lock_env['DB_HOST']!r}, user={lock_env['DB_USER']!r},
                                        password={lock_env.get('DB_PASSWORD', '')!r})
            cur = c.cursor()
            cur.execute("SELECT GET_LOCK(%s, 0)", ({run_lock.lock_name(lock_env['DB_NAME'])!r},))
            print(cur.fetchone()[0], flush=True)
            time.sleep(60)
        """)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "1"
        assert not _free(test_db, lock_env["DB_NAME"])
        holder.kill()
        holder.wait(10)
        assert _free(test_db, lock_env["DB_NAME"], seconds=5)
    finally:
        holder.kill()


def _pytest_run(tmp_path, env):
    """A real pytest run whose conftest uses the hook exactly as a tool's does."""
    marker = tmp_path / "a-test-ran"
    (tmp_path / "conftest.py").write_text(textwrap.dedent("""
        from phronon_common.testing import run_lock

        def pytest_sessionstart(session):
            run_lock.hold_the_test_database(session)
    """))
    (tmp_path / "test_one.py").write_text(
        f"def test_one():\n    open({str(marker)!r}, 'w').close()\n")
    # cwd = the package's parent, as test_import_boundaries.py runs it, so the
    # child imports this checkout of phronon_common.
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"],
        cwd=PKG.parent, env={**os.environ, **env}, capture_output=True, text=True, timeout=120)
    return proc, marker.exists()


def test_a_real_pytest_run_stops_before_its_first_test_and_says_why(test_db, lock_env, tmp_path):
    holder = _holder(test_db, lock_env["DB_NAME"])
    try:
        proc, ran = _pytest_run(tmp_path, {**lock_env, "PHRONON_TEST_RUN_WAIT": "2"})
    finally:
        holder.close()
    out = proc.stdout + proc.stderr
    assert proc.returncode == 2, out            # pytest's INTERRUPTED: red, not green
    assert not ran, "a test ran while another run held the database"
    assert "Another test run is using" in out, out
    assert "Interrupted: Another test run held" in out and "ps -ax -o pid,etime,command" in out, out


def test_a_real_pytest_run_with_the_database_free_just_runs(test_db, lock_env, tmp_path):
    proc, ran = _pytest_run(tmp_path, lock_env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ran
    assert "Another test run" not in proc.stdout + proc.stderr
