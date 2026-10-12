"""send_password_reset tells its caller whether the mail went out (FL-096 (d)).

Until 12 October 2026 it returned None whether or not anything was sent, so an
admin's "send reset link" button reported success on a box without
SMTP_PASSWORD. Offline: the SMTP conversation is replaced.
"""
from phronon_common import emails


def test_without_smtp_nothing_is_sent_and_it_says_so(monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    sent = []
    monkeypatch.setattr(emails, "_smtp_send", lambda *a: sent.append(a))
    assert emails.send_password_reset("Tool", "a@phronon.org", "x@example.org",
                                      "https://example.org/r/t") is False
    assert sent == []


def test_with_smtp_it_sends_and_says_so(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "test-only")
    sent = []
    monkeypatch.setattr(emails, "_smtp_send", lambda *a: sent.append(a))
    assert emails.send_password_reset("Tool", "a@phronon.org", "x@example.org",
                                      "https://example.org/r/t") is True
    assert len(sent) == 1
