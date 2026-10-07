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


def test_the_research_sentence_only_where_the_tool_keeps_research(monkeypatch):
    """TO DO FL-091: the mail promised a research record in tools that keep none."""
    url = "https://tool.example/withdraw?token=x"
    sentence = "pseudonymous research record"
    for body in emails.withdrawal_link_bodies("Tool", url, "2026-11-01"):
        assert sentence in body                                # the default: as before
    for body in emails.withdrawal_link_bodies("Tool", url, "2026-11-01", research=False):
        assert sentence not in body and "until 2026-11-01" in body
    for body in emails.withdrawal_link_bodies("Tool", url, research=False):
        assert "for as long as we hold data" in body
    monkeypatch.setenv("SMTP_PASSWORD", "test-only")
    sent = []
    monkeypatch.setattr(emails, "_smtp_send", lambda sender, to, msg: sent.append(msg.as_string()))
    for research in (True, False):
        emails.send_withdrawal_link("Tool", "noreply@tool.example", "p@example.org", url,
                                    deadline="2026-11-01", research=research)
    assert "research" in sent[0] and "research" not in sent[1]
