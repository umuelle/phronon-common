"""The fleet's one way to reach MySQL: a connection pool and the query helpers.

WHY (TO DO FL-113, 13 November 2026). Each tool had its own db.py: ten files in
four dialects, where a fix made in one reached the others only by hand. The
wait for a free connection went into three tools on 27 October and into the
other seven on 12 November; a fixed time zone was in two, a rollback on a
failed write in five. This module is built from the strictest copy of each
piece, and a tool's db.py keeps its own function names on top of it, so the
pages that call them do not change when a tool adopts it.

WHAT EVERY TOOL GETS, without a setting to turn it off:

  * a request waits up to POOL_WAIT_SECONDS for a free pooled connection
    (mysql-connector's pool refuses at once when it is empty, and handlers run
    side by side in worker threads since 27 October 2026);
  * a connection is pinged when it is handed out and revived if MySQL
    restarted underneath the pool;
  * the session time zone is UTC ("+00:00"), so NOW() and the times a tool
    stores do not move with the server's clock setting;
  * a failed write is rolled back before the error goes on;
  * a transaction is opened with start_transaction(): `autocommit = False` set
    on a pooled connection reaches only the pool's wrapper object, and the
    server goes on committing each statement (Moral Mirror, 1 October 2026);
  * every connection is handed back in a `finally`.

WHAT A TOOL CHOOSES: its pool's name and size, its settings, its connection
collation, and `autocommit`. Four tools (Layoff, Moral Mirror, the hub,
Polarity Profiler) run with autocommit on and have pages that write through a
raw connection without committing, so the default cannot be changed under them
when they adopt this module.

THE TWO WRITE HELPERS say what they answer. `insert` returns the new row's id
(0 when nothing was inserted with an AUTO_INCREMENT key); `write` returns the
number of rows the statement CHANGED, which is what a conditional UPDATE used as
a claim needs ("mint this only if nobody has yet"). A tool's own names keep
their meaning on top: Drawbridge's `execute` is `insert`, its
`execute_rowcount` is `write`.

The pool is built on first use, from the settings the tool's callable returns
at that moment, so a test that names its own database before the first query
gets it.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, TypeVar, Union

from mysql.connector import pooling
from mysql.connector.errors import PoolError

logger = logging.getLogger(__name__)

#: How long a request waits for a free pooled connection, in seconds.
POOL_WAIT_SECONDS = 10.0

#: The session time zone of every connection: UTC.
TIME_ZONE = "+00:00"

#: The character set of every connection.
CHARSET = "utf8mb4"

Params = Union[Sequence[Any], Mapping[str, Any]]
Row = dict[str, Any]
T = TypeVar("T")


@dataclass(frozen=True)
class DatabaseSettings:
    """Where the database is and who signs in to it."""

    host: str
    port: int
    user: str
    password: str
    name: str

    @classmethod
    def from_env(cls, *, name: str, user: str, host: str = "localhost",
                 environ: Mapping[str, str] | None = None) -> DatabaseSettings:
        """DB_HOST, DB_PORT, DB_USER, DB_PASSWORD and DB_NAME from the
        environment, read when called; the arguments are the defaults for a
        variable that is not set."""
        env = os.environ if environ is None else environ
        return cls(host=env.get("DB_HOST", host), port=int(env.get("DB_PORT", "3306")),
                   user=env.get("DB_USER", user), password=env.get("DB_PASSWORD", ""),
                   name=env.get("DB_NAME", name))


class Database:
    """One tool's connection pool and the helpers every page uses."""

    def __init__(self, *, pool_name: str, settings: Callable[[], DatabaseSettings],
                 pool_size: int = 10, autocommit: bool = False,
                 collation: str | None = None,
                 wait_seconds: float = POOL_WAIT_SECONDS) -> None:
        self.pool_name = pool_name
        self.pool_size = pool_size
        self.autocommit = autocommit
        self.collation = collation
        self.wait_seconds = wait_seconds
        self._settings = settings
        self._pool: pooling.MySQLConnectionPool | None = None
        self._lock = threading.Lock()

    def settings(self) -> DatabaseSettings:
        return self._settings()

    def pool(self) -> pooling.MySQLConnectionPool:
        """The pool, built once on first use, even when threads ask together."""
        if self._pool is None:
            with self._lock:
                if self._pool is None:
                    s = self._settings()
                    options: dict[str, Any] = {
                        "pool_name": self.pool_name, "pool_size": self.pool_size,
                        "host": s.host, "port": s.port, "user": s.user,
                        "password": s.password, "database": s.name,
                        "autocommit": self.autocommit, "charset": CHARSET,
                        "time_zone": TIME_ZONE,
                    }
                    if self.collation:
                        options["collation"] = self.collation
                    self._pool = pooling.MySQLConnectionPool(**options)
        return self._pool

    def connect(self) -> Any:
        """A pooled connection: waited for while the pool is empty, revived if
        MySQL restarted. The caller closes it, which hands it back."""
        pool = self.pool()
        deadline = time.monotonic() + self.wait_seconds
        while True:
            try:
                conn = pool.get_connection()
                break
            except PoolError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.02)
        try:
            conn.ping(reconnect=True, attempts=2, delay=0)
        except Exception:
            try:
                conn.close()
            except Exception:  # noqa: BLE001 - the ping's own error is the one raised below
                logger.debug("closing a connection whose ping failed also failed", exc_info=True)
            raise
        return conn

    # ── Reading ──────────────────────────────────────────────────────────────

    def query_one(self, sql: str, params: Params = ()) -> Row | None:
        """The first row as a dict, or None. The cursor reads the whole result,
        so a query that matches more rows still hands back a clean connection."""
        conn = self.connect()
        try:
            cur = conn.cursor(dictionary=True, buffered=True)
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def query_all(self, sql: str, params: Params = ()) -> list[Row]:
        """Every row, each as a dict."""
        conn = self.connect()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    # ── Writing ──────────────────────────────────────────────────────────────

    def insert(self, sql: str, params: Params = ()) -> int:
        """One write in its own transaction; returns the new row's id."""
        return self._write(sql, params)[0]

    def write(self, sql: str, params: Params = ()) -> int:
        """One write in its own transaction; returns the rows it CHANGED."""
        return self._write(sql, params)[1]

    def _write(self, sql: str, params: Params) -> tuple[int, int]:
        """(new row id, rows changed), both read before the connection goes back."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            answer = (int(cur.lastrowid or 0), int(cur.rowcount))
            conn.commit()
            return answer
        except BaseException:
            _rollback(conn)
            raise
        finally:
            conn.close()

    def transaction(self, statements: Iterable[tuple[str, Params | None]]) -> None:
        """[(sql, params), ...] in ONE transaction: all of them or none."""
        conn = self.connect()
        try:
            conn.start_transaction()
            cur = conn.cursor()
            for sql, params in statements:
                cur.execute(sql, params if params is not None else ())
            conn.commit()
        except BaseException:
            _rollback(conn)
            raise
        finally:
            conn.close()

    def in_transaction(self, work: Callable[[Any], T]) -> T:
        """Run `work(cursor)` in ONE transaction and return what it returns.

        For writes that depend on an earlier statement's outcome in the same
        transaction (a total raised only when an INSERT IGNORE inserted), or a
        row read FOR UPDATE and then changed. The cursor answers rows as dicts.
        """
        conn = self.connect()
        try:
            conn.start_transaction()
            result = work(conn.cursor(dictionary=True))
            conn.commit()
            return result
        except BaseException:
            _rollback(conn)
            raise
        finally:
            conn.close()

    @contextmanager
    def named_lock(self, name: str, timeout: int = 30) -> Iterator[None]:
        """Hold MySQL's GET_LOCK for the block: one holder across every worker
        process, also where there is no row to lock. The name is prefixed with
        the database's name, so a test database on the same server never waits
        on production. Raises TimeoutError if the lock is not had in time; the
        server releases it anyway if the holding connection dies."""
        full = f"{self._settings().name}.{name}"[:64]
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT GET_LOCK(%s, %s)", (full, timeout))
            got = cur.fetchone()
            if not got or got[0] != 1:
                raise TimeoutError(f"could not take lock {full!r} in {timeout}s")
            try:
                yield
            finally:
                cur.execute("SELECT RELEASE_LOCK(%s)", (full,))
                cur.fetchall()
        finally:
            conn.close()


def _rollback(conn: Any) -> None:
    """Roll back after a failure; a rollback that fails too is logged, and the
    original error is the one that goes on."""
    try:
        conn.rollback()
    except Exception:
        logger.exception("rollback after a failed statement also failed")
