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


def test_the_full_set_goes_once_a_day_and_a_canary_after_that(tmp_path):
    """The owner's rule, 18 September 2026.

    Live sending is never muted — one real delivery has to succeed on every
    run, because receiving it is the proof that delivery works. What changed is
    that deploying one tool repeatedly can no longer spend the provider's whole
    daily budget: on 18 September that is exactly what happened, and every
    further deploy of that tool failed on `450 Mail send limit exceeded`.
    """
    sent = []
    samples = tuple((f"k{i}", f"Sample {i}", lambda r, i=i: sent.append(i))
                    for i in range(4))

    first = mail_harness.send_all(samples, "test@phronon.org", project_root=tmp_path)
    assert len(first) == 4 and sent == [0, 1, 2, 3], "the first run of the day sends everything"

    sent.clear()
    second = mail_harness.send_all(samples, "test@phronon.org", project_root=tmp_path)
    assert len(second) == 1 and sent == [0], "a later run the same day sends one canary"

    (tmp_path / mail_harness.FULL_SEND_STAMP).write_text("2020-01-01\n", encoding="utf-8")
    sent.clear()
    assert len(mail_harness.send_all(samples, "test@phronon.org", project_root=tmp_path)) == 4, \
        "a new day sends the full set again"


def test_a_failed_full_send_is_not_recorded_as_done(tmp_path):
    """Otherwise one bad day would leave the tool on canaries until tomorrow,
    with nothing having proved that the other nineteen messages can be sent."""
    def boom(_recipient):
        raise RuntimeError("SMTP said no")

    samples = (("a", "Works", lambda r: None), ("b", "Fails", boom))
    results = mail_harness.send_all(samples, "test@phronon.org", project_root=tmp_path)
    assert any(err is not None for _k, _l, err in results)
    assert not (tmp_path / mail_harness.FULL_SEND_STAMP).exists()
    assert mail_harness.full_set_due(tmp_path) is True


def test_without_a_project_root_nothing_is_throttled(tmp_path):
    """A hand-run of a tool's own script keeps its old behaviour."""
    sent = []
    samples = tuple((f"k{i}", f"S{i}", lambda r, i=i: sent.append(i)) for i in range(3))
    mail_harness.send_all(samples, "test@phronon.org")
    mail_harness.send_all(samples, "test@phronon.org")
    assert sent == [0, 1, 2, 0, 1, 2]
