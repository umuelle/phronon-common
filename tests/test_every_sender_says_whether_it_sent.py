"""Five more shared senders say whether the mail left (TO DO FL-104, 26 October 2026).

The address-change confirmation and notice, the two two-factor mails and the
participant resume link answered None whether they sent or not, so a test-mail
sample of them counted as delivered on a machine without SMTP, and the resume
link could not be stored only after its mail went out. They now answer as
`send_password_reset` and `send_withdrawal_link` do: True once the mail server
took the mail, False when nothing was sent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import emails, mail_diagnostics  # noqa: E402

SENDERS = {
    "email_change_confirm": lambda: emails.send_email_change_confirm(
        "Tool", "noreply@tool.example", "a@example.org", "https://tool.example/confirm?t=x"),
    "email_change_notice": lambda: emails.send_email_change_notice(
        "Tool", "noreply@tool.example", "a@example.org", "new@example.org"),
    "two_factor_reset": lambda: emails.send_two_factor_reset_notice(
        "Tool", "noreply@tool.example", "a@example.org", "https://tool.example/account"),
    "two_factor_confirmation": lambda: emails.send_two_factor_confirmation(
        "Tool", "noreply@tool.example", "a@example.org", "https://tool.example/account"),
    "participant_resume": lambda: emails.send_participant_resume(
        "Tool", "noreply@tool.example", "p@example.org", "https://tool.example/resume?token=x"),
}


@pytest.mark.parametrize("key", SENDERS)
def test_no_smtp_is_not_sent(monkeypatch, key):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    handed = []
    monkeypatch.setattr(emails, "_smtp_send", lambda sender, to, msg: handed.append(to))
    assert SENDERS[key]() is False
    assert not handed


@pytest.mark.parametrize("key", SENDERS)
def test_a_mail_handed_to_the_server_is_sent(monkeypatch, key):
    monkeypatch.setenv("SMTP_PASSWORD", "test-only")
    handed = []
    monkeypatch.setattr(emails, "_smtp_send", lambda sender, to, msg: handed.append(to))
    assert SENDERS[key]() is True
    assert len(handed) == 1


def test_a_failed_two_factor_confirmation_is_logged_and_says_so(monkeypatch, caplog):
    """It never raises (the change is saved and the codes are on screen), so
    the answer is the only way a caller can learn the mail did not leave."""
    monkeypatch.setenv("SMTP_PASSWORD", "test-only")

    def refused(sender, to, msg):
        raise OSError("connection refused")

    monkeypatch.setattr(emails, "_smtp_send", refused)
    assert SENDERS["two_factor_confirmation"]() is False
    assert "two-factor confirmation to @example.org failed" in caplog.text


@pytest.mark.parametrize("answer", [True, None])
def test_a_sample_counts_as_sent_unless_its_sender_says_false(answer):
    mail_diagnostics.raise_if_not_sent(answer, "the sample")


def test_a_sample_whose_sender_says_false_fails_with_both_wordings():
    """The tools' tests match "Not sent" (four tools) or "not sent" (three)."""
    with pytest.raises(RuntimeError) as error:
        mail_diagnostics.raise_if_not_sent(False, "the reset sample")
    assert "Not sent" in str(error.value) and "the reset sample was not sent" in str(error.value)
