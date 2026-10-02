"""The two-factor confirmation mail (2 October 2026).

Sent when an account holder switches two-factor on, moves it to a new
authenticator, or makes new recovery codes. These tests drive the real send
path against a fake SMTP and read what would have gone out.
"""
import email
import smtplib
from email.header import decode_header, make_header

import pytest

from phronon_common import emails

ACCOUNT_URL = "https://example.org/backoffice/account"


class _FakeSMTP:
    sent: list = []

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self, *a, **kw):
        pass

    def starttls(self, *a, **kw):
        pass

    def login(self, *a, **kw):
        pass

    def sendmail(self, sender, recipients, raw):
        _FakeSMTP.sent.append((sender, recipients, raw))


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.sent = []
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    return _FakeSMTP.sent


def _parts(raw):
    msg = email.message_from_string(raw)
    out = {"subject": str(make_header(decode_header(msg["Subject"])))}
    for part in msg.walk():
        ctype = part.get_content_type()
        if ctype in ("text/plain", "text/html"):
            out[ctype] = part.get_payload(decode=True).decode()
    return out


@pytest.mark.parametrize("event", sorted(emails.TWO_FACTOR_EVENTS))
def test_each_event_sends_one_mail_naming_the_tool(smtp, event):
    emails.send_two_factor_confirmation("Whiteout Exercise", "info@x.org",
                                        "someone@example.org", ACCOUNT_URL, event)
    assert len(smtp) == 1
    sender, recipients, raw = smtp[0]
    assert recipients == ["someone@example.org"]
    p = _parts(raw)
    assert p["subject"].startswith("Whiteout Exercise — ")
    for body in (p["text/plain"], p["text/html"]):
        assert "Whiteout Exercise" in body
        assert ACCOUNT_URL in body
        assert "If this was not you" in body
        # The codes reminder belongs to the code events; a passkey mail says
        # what a passkey can do instead.
        if event.startswith("passkey"):
            assert "recovery codes" not in body and "without your password" in body
        else:
            assert "recovery codes" in body


def test_only_a_replacement_says_the_old_codes_are_dead(smtp):
    text, _ = emails.two_factor_confirmation_bodies("T", ACCOUNT_URL, "enabled")
    assert "previous recovery codes" not in text
    for event in ("replaced", "codes_regenerated"):
        text, html = emails.two_factor_confirmation_bodies("T", ACCOUNT_URL, event)
        assert "previous recovery codes no longer work" in text
        assert "previous recovery codes no longer work" in html


def test_subjects_differ_per_event():
    tails = [subject for subject, _ in emails.TWO_FACTOR_EVENTS.values()]
    assert len(set(tails)) == len(tails)


def test_unknown_event_is_a_programming_error(smtp):
    with pytest.raises(ValueError):
        emails.send_two_factor_confirmation("T", "a@x.org", "b@x.org", ACCOUNT_URL, "disabled")


def test_no_smtp_password_sends_nothing(monkeypatch, smtp):
    monkeypatch.delenv("SMTP_PASSWORD")
    emails.send_two_factor_confirmation("T", "a@x.org", "b@x.org", ACCOUNT_URL)
    assert smtp == []


def test_a_failing_server_is_logged_not_raised(monkeypatch, caplog):
    """The change is already saved and the user is reading their codes; a mail
    outage must not turn that page into an error."""
    class Broken(_FakeSMTP):
        def sendmail(self, *a):
            raise smtplib.SMTPException("down")
    monkeypatch.setenv("SMTP_PASSWORD", "x")
    monkeypatch.setattr(smtplib, "SMTP", Broken)
    emails.send_two_factor_confirmation("T", "a@x.org", "someone@example.org", ACCOUNT_URL)
    assert "two-factor confirmation" in caplog.text
    assert "someone@" not in caplog.text      # the domain only, never the address
