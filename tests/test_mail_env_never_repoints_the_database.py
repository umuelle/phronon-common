"""Loading a project's .env must fill gaps, never overwrite the caller.

WHY THIS FILE EXISTS

`load_project_env` gives a hand-run pytest on the server the SMTP credentials
systemd would otherwise have injected. It used to write EVERY key of `.env`
into `os.environ`, `DB_NAME` among them — and `server-ops/run_tests.py`
deliberately sets `DB_NAME=<db>_test` before starting pytest, precisely so the
suite cannot touch production.

So on the server the first live-mail test silently repointed the whole process
at the live database. Polarity Profiler's per-fixture guards then refused to
run seventeen database-backed tests on every deploy, for months, inside a green
result; the tools whose guards run at collection kept running, and were spared
writing to production only because their connection pool had already been built
against the test schema. Found 18 September 2026.
"""
from __future__ import annotations

import os

from phronon_common.testing import mail_harness


def test_it_fills_what_is_missing(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("SMTP_PASSWORD=from-the-file\n", encoding="utf-8")
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert mail_harness.load_project_env(tmp_path) is True
    assert os.environ["SMTP_PASSWORD"] == "from-the-file"


def test_it_never_overwrites_the_database_the_caller_chose(tmp_path, monkeypatch):
    """The regression itself: the deploy gate's `<db>_test` must survive."""
    (tmp_path / ".env").write_text(
        "DB_NAME=the_live_database\nDB_USER=live_user\nSMTP_PASSWORD=x\n", encoding="utf-8")
    monkeypatch.setenv("DB_NAME", "something_test")
    monkeypatch.setenv("DB_USER", "something_user")
    mail_harness.load_project_env(tmp_path)
    assert os.environ["DB_NAME"] == "something_test", (
        "the .env repointed the running process at the live database — every "
        "disposable-schema guard after this point sees the production name, and "
        "any test that writes without one writes to production")
    assert os.environ["DB_USER"] == "something_user"


def test_no_env_file_is_not_an_error(tmp_path):
    assert mail_harness.load_project_env(tmp_path) is False
