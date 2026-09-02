"""The heartbeat must stamp UTC on the database clock and never raise."""
from phronon_common import retention_heartbeat


def test_the_upsert_is_one_statement_on_the_database_clock():
    """UTC_TIMESTAMP() in BOTH branches — app-host clock drift must not be
    able to fake freshness or staleness, and a second worker's concurrent
    upsert must stay a single-row race with no losers."""
    sql = retention_heartbeat._UPSERT
    assert sql.count("UTC_TIMESTAMP()") == 2
    assert "ON DUPLICATE KEY UPDATE" in sql
    assert "VALUES (1," in sql


def test_record_swallows_every_failure():
    """A monitoring write must not be able to kill the worker it monitors."""
    def broken_get_db():
        raise RuntimeError("db down")

    retention_heartbeat.record(broken_get_db, "pass complete")  # must not raise


def test_record_commits_and_closes():
    calls = []

    class Cursor:
        def execute(self, sql, params):
            calls.append(("execute", params[0]))

        def close(self):
            calls.append(("cursor_close", None))

    class Conn:
        def cursor(self):
            return Cursor()

        def commit(self):
            calls.append(("commit", None))

        def close(self):
            calls.append(("conn_close", None))

    retention_heartbeat.record(lambda: Conn(), "x" * 300)
    kinds = [k for k, _ in calls]
    assert kinds == ["execute", "commit", "cursor_close", "conn_close"]
    assert len(calls[0][1]) == 255  # detail truncated to the column
