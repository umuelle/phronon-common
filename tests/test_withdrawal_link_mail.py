"""emails.send_withdrawal_link says whether the mail left (6 October 2026).

The withdrawal kit stores a link's new token only after the mail went out, so
a mail that could not be sent keeps the old link working. That needs the
sender to say so: it returned None whether it sent or not.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import emails  # noqa: E402


def test_no_smtp_is_not_sent(monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert emails.send_withdrawal_link("Tool", "noreply@tool.example", "p@example.org",
                                       "https://tool.example/withdraw?token=x") is False


def test_a_mail_handed_to_the_server_is_sent(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "test-only")
    handed = []
    monkeypatch.setattr(emails, "_smtp_send", lambda sender, to, msg: handed.append(to))
    assert emails.send_withdrawal_link("Tool", "noreply@tool.example", "p@example.org",
                                       "https://tool.example/withdraw?token=x") is True
    assert handed == ["p@example.org"]
