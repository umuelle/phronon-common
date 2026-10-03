"""Shared fixtures for this package's own tests.

`test_db` is the ONE way a test here reaches MySQL. Off CI, with no disposable
*_test schema named, it skips (a laptop without a database is a real gap, not
a defect). Where PHRONON_REQUIRE_DB=1 (this package's CI, since 3 October
2026) it FAILS instead: the tests behind it prove the passkey one-use rule and
once()'s ownership under real row locks, and a fake table cannot. Until that
day CI had no MySQL and they skipped on every run.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def test_db():
    name = os.environ.get("DB_NAME", "")
    required = os.environ.get("PHRONON_REQUIRE_DB") == "1"
    missing = None
    if not (os.environ.get("DB_HOST") and name.endswith("_test")):
        missing = "requires a disposable test database"
    else:
        try:
            import mysql.connector as mysql
        except ImportError:
            missing = "mysql-connector-python is not installed"
    if missing:
        if required:
            pytest.fail(f"{missing} (PHRONON_REQUIRE_DB=1: this run must exercise MySQL)")
        pytest.skip(missing)

    def get_db():
        return mysql.connect(host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
                             password=os.environ.get("DB_PASSWORD", ""), database=name)
    return get_db
