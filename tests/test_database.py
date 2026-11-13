"""database.py: the fleet's one pool and query helpers (TO DO FL-113).

The first half needs no database: a stand-in pool shows the wait, the revive
and the fixed connection settings. The second half runs against a real MySQL
test database (the `test_db` fixture: skipped on a laptop without one, a
failure in this package's CI), because rollback, transactions, the time zone
and GET_LOCK are the server's behaviour and a fake would only repeat the
assumption.
"""
from __future__ import annotations

import os
import threading
import time
import uuid

import pytest
from mysql.connector.errors import PoolError

from phronon_common import database
from phronon_common.database import Database, DatabaseSettings


def _settings() -> DatabaseSettings:
    return DatabaseSettings(host="db.invalid", port=3306, user="u", password="p", name="tool_test")


class _Conn:
    def __init__(self, ping_error: Exception | None = None):
        self.ping_error = ping_error
        self.closed = False

    def ping(self, **_kw):
        if self.ping_error:
            raise self.ping_error

    def close(self):
        self.closed = True


class _Pool:
    """Refuses `busy` times, as mysql-connector's pool does when it is empty."""

    def __init__(self, busy: int = 0, conn: _Conn | None = None):
        self.busy = busy
        self.conn = conn or _Conn()

    def get_connection(self):
        if self.busy:
            self.busy -= 1
            raise PoolError("Failed getting connection; pool exhausted")
        return self.conn


def _with_pool(pool, **kw) -> Database:
    db = Database(pool_name="t", settings=_settings, **kw)
    db._pool = pool
    return db


# ── Without a database ───────────────────────────────────────────────────────

def test_an_empty_pool_is_waited_for():
    pool = _Pool(busy=3)
    assert _with_pool(pool).connect() is pool.conn and pool.busy == 0


def test_a_pool_that_stays_empty_still_fails_after_the_wait():
    with pytest.raises(PoolError):
        _with_pool(_Pool(busy=10**9), wait_seconds=0.1).connect()


def test_the_wait_is_ten_seconds_unless_a_tool_says_otherwise():
    assert Database(pool_name="t", settings=_settings).wait_seconds == 10


def test_a_connection_whose_ping_fails_is_handed_back_and_the_error_raised():
    conn = _Conn(ping_error=OSError("server has gone away"))
    with pytest.raises(OSError, match="gone away"):
        _with_pool(_Pool(conn=conn)).connect()
    assert conn.closed


def test_every_connection_is_utc_and_utf8mb4_whatever_the_tool_chooses(monkeypatch):
    built = []
    monkeypatch.setattr(database.pooling, "MySQLConnectionPool",
                        lambda **kw: built.append(kw) or object())
    Database(pool_name="dd", settings=_settings, pool_size=7, autocommit=True,
             collation="utf8mb4_unicode_ci").pool()
    Database(pool_name="pp", settings=_settings).pool()
    first, second = built
    assert first == {"pool_name": "dd", "pool_size": 7, "host": "db.invalid", "port": 3306,
                     "user": "u", "password": "p", "database": "tool_test",
                     "autocommit": True, "charset": "utf8mb4", "time_zone": "+00:00",
                     "collation": "utf8mb4_unicode_ci"}
    assert second["time_zone"] == "+00:00" and second["autocommit"] is False
    assert "collation" not in second, "no collation chosen: the server's default for utf8mb4"


def test_the_settings_are_read_at_the_first_query_not_at_import(monkeypatch):
    names = iter(["first", "second"])
    built = []
    monkeypatch.setattr(database.pooling, "MySQLConnectionPool",
                        lambda **kw: built.append(kw["database"]) or object())
    db = Database(pool_name="t", settings=lambda: DatabaseSettings("h", 1, "u", "p", next(names)))
    assert built == []
    db.pool()
    db.pool()
    assert built == ["first"]


def test_threads_asking_together_build_one_pool(monkeypatch):
    built = []
    gate = threading.Barrier(8)

    def slow_pool(**kw):
        time.sleep(0.05)              # a real pool opens connections: a window for a race
        built.append(kw)
        return object()

    monkeypatch.setattr(database.pooling, "MySQLConnectionPool", slow_pool)
    db = Database(pool_name="t", settings=_settings)
    pools = []

    def ask():
        gate.wait()
        pools.append(db.pool())

    threads = [threading.Thread(target=ask) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1 and len({id(p) for p in pools}) == 1


def test_settings_come_from_the_environment_with_the_tools_defaults():
    env = {"DB_HOST": "127.0.0.1", "DB_PORT": "3307", "DB_USER": "x_user",
           "DB_PASSWORD": "secret", "DB_NAME": "x_test"}
    assert DatabaseSettings.from_env(name="x", user="x_user0", environ=env) == \
        DatabaseSettings("127.0.0.1", 3307, "x_user", "secret", "x_test")
    assert DatabaseSettings.from_env(name="x", user="x_user0", environ={}) == \
        DatabaseSettings("localhost", 3306, "x_user0", "", "x")


# ── Against a real database ──────────────────────────────────────────────────

@pytest.fixture
def real(test_db):
    """A Database on the test schema the environment names, and a scratch
    table of its own, dropped afterwards."""
    table = f"phronon_common_db_probe_{uuid.uuid4().hex[:8]}"

    def build(**kw) -> Database:
        return Database(pool_name=f"probe{uuid.uuid4().hex[:6]}", pool_size=3,
                        settings=lambda: DatabaseSettings.from_env(
                            name=os.environ["DB_NAME"], user=os.environ["DB_USER"]), **kw)

    db = build()
    db.write(f"CREATE TABLE {table} (id INT AUTO_INCREMENT PRIMARY KEY, "
             "label VARCHAR(20) NOT NULL UNIQUE, n INT NOT NULL DEFAULT 0)")
    try:
        yield db, table, build
    finally:
        db.write(f"DROP TABLE IF EXISTS {table}")


def test_insert_answers_the_new_id_and_write_the_rows_it_changed(real):
    db, table, _ = real
    first = db.insert(f"INSERT INTO {table} (label) VALUES (%s)", ("a",))
    second = db.insert(f"INSERT INTO {table} (label) VALUES (%s)", ("b",))
    assert second == first + 1
    assert db.write(f"UPDATE {table} SET n = 1 WHERE label = %s", ("a",)) == 1
    # Matched but already 1: MySQL counts rows CHANGED, which a claim relies on.
    assert db.write(f"UPDATE {table} SET n = 1 WHERE label = %s", ("a",)) == 0
    assert db.query_one(f"SELECT label, n FROM {table} WHERE id = %s", (first,)) == \
        {"label": "a", "n": 1}
    assert [r["label"] for r in db.query_all(f"SELECT label FROM {table} ORDER BY id")] == \
        ["a", "b"]


def test_query_one_on_several_rows_leaves_a_clean_connection(real):
    db, table, build = real
    small = build()
    small.pool_size = 1
    small.insert(f"INSERT INTO {table} (label) VALUES ('a'), ('b'), ('c')")
    assert small.query_one(f"SELECT label FROM {table} ORDER BY id") == {"label": "a"}
    assert small.query_one("SELECT 2 AS two") == {"two": 2}


def test_every_connection_runs_in_utc(real):
    db, _, _ = real
    assert db.query_one("SELECT @@session.time_zone AS tz") == {"tz": "+00:00"}


@pytest.mark.parametrize("autocommit", [False, True])
def test_a_transaction_is_all_or_nothing_even_with_autocommit_on(real, autocommit):
    _, table, build = real
    db = build(autocommit=autocommit)
    with pytest.raises(Exception, match="Duplicate"):
        db.transaction([(f"INSERT INTO {table} (label) VALUES (%s)", ("x",)),
                        (f"INSERT INTO {table} (label) VALUES (%s)", ("x",))])
    assert db.query_all(f"SELECT label FROM {table}") == []
    db.transaction([(f"INSERT INTO {table} (label) VALUES (%s)", ("y",)),
                    (f"UPDATE {table} SET n = 5 WHERE label = %s", ("y",))])
    assert db.query_one(f"SELECT n FROM {table}") == {"n": 5}


@pytest.mark.parametrize("autocommit", [False, True])
def test_in_transaction_returns_the_work_and_rolls_back_on_a_failure(real, autocommit):
    _, table, build = real
    db = build(autocommit=autocommit)

    def add_and_count(cur):
        cur.execute(f"INSERT INTO {table} (label) VALUES (%s)", ("z",))
        cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
        return cur.fetchone()["c"]

    assert db.in_transaction(add_and_count) == 1

    def add_then_fail(cur):
        cur.execute(f"INSERT INTO {table} (label) VALUES (%s)", ("w",))
        raise RuntimeError("the second step failed")

    with pytest.raises(RuntimeError):
        db.in_transaction(add_then_fail)
    assert [r["label"] for r in db.query_all(f"SELECT label FROM {table}")] == ["z"]


def test_a_failed_write_leaves_the_pooled_connection_usable(real):
    _, table, build = real
    db = build()
    db.pool_size = 1
    db.insert(f"INSERT INTO {table} (label) VALUES ('a')")
    for _ in range(3):
        with pytest.raises(Exception, match="Duplicate"):
            db.insert(f"INSERT INTO {table} (label) VALUES ('a')")
    assert db.query_one(f"SELECT COUNT(*) AS c FROM {table}") == {"c": 1}


def test_a_named_lock_has_one_holder_and_is_released(real):
    db, _, build = real
    name = f"probe-{uuid.uuid4().hex[:8]}"
    with db.named_lock(name):
        with pytest.raises(TimeoutError):
            with build().named_lock(name, timeout=0):
                pass
    with build().named_lock(name, timeout=0):
        pass
