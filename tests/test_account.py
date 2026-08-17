"""The shared parts of self-service account management.

The address-change link is the piece worth testing hardest: it is the one place
in the fleet where a signed-in person can change WHO the account is, and every
check below stands for a way that could go wrong quietly.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import account  # noqa: E402

SECRET = "test-secret-key-not-used-anywhere-real"


def signer():
    return account.email_change_signer(SECRET)


def row(**over):
    base = {"id": 7, "email": "old@example.org", "session_epoch": 3}
    base.update(over)
    return base


def token_for(r, new_email="new@example.org"):
    return account.make_email_change_token(
        signer(), admin_id=r["id"], old_email=r["email"], new_email=new_email,
        session_epoch=r["session_epoch"])


# ── addresses ────────────────────────────────────────────────────────────────

class TestValidateEmail:

    @pytest.mark.parametrize("raw,expected", [
        ("  Urs@Example.ORG ", "urs@example.org"),
        ("a.b+tag@sub.example.co.uk", "a.b+tag@sub.example.co.uk"),
    ])
    def test_accepts_and_normalises(self, raw, expected):
        email, error = account.validate_email(raw)
        assert error is None
        assert email == expected

    @pytest.mark.parametrize("raw", [
        "", "   ", "no-at-sign", "no@domain", "two@@example.org",
        "spaces in@example.org", "trailing@example.org extra",
    ])
    def test_rejects(self, raw):
        _, error = account.validate_email(raw)
        assert error, f"{raw!r} should not be accepted as an address"

    def test_rejects_an_address_longer_than_the_column(self):
        long = ("x" * 250) + "@example.org"
        _, error = account.validate_email(long)
        assert error and "too long" in error

    def test_the_current_address_is_not_a_change(self):
        """Otherwise a confirmation mail goes out for a change that would do
        nothing, and the account is told its address is being taken over."""
        _, error = account.validate_email("URS@example.org", current="urs@example.org")
        assert error and "already" in error


class TestValidateName:

    def test_trims_and_accepts(self):
        name, error = account.validate_name("  Urs Müller  ")
        assert error is None and name == "Urs Müller"

    def test_strips_control_characters_rather_than_rejecting(self):
        name, error = account.validate_name("Urs\r\n\tMüller")
        assert error is None
        assert name == "Urs\tMüller".replace("\t", "") or "\n" not in name
        assert "\r" not in name and "\n" not in name

    def test_a_blank_name_is_refused(self):
        """A user list with an unnamed row is a list nobody can act on."""
        for raw in ("", "   ", "\n\n"):
            _, error = account.validate_name(raw)
            assert error


# ── the link ─────────────────────────────────────────────────────────────────

class TestEmailChangeToken:

    def test_a_fresh_token_round_trips(self):
        payload, error = account.read_email_change_token(
            signer(), token_for(row()), row=row())
        assert error is None
        assert payload["new"] == "new@example.org"
        assert payload["id"] == 7

    def test_an_epoch_of_zero_is_an_epoch(self):
        """A brand-new account has session_epoch 0, and `0 or -1` is -1 — which
        rejected the first address change every untouched account ever made."""
        fresh = row(session_epoch=0)
        payload, error = account.read_email_change_token(
            signer(), token_for(fresh), row=fresh)
        assert error is None and payload["new"] == "new@example.org"

    def test_a_tampered_or_missing_token_is_refused(self):
        for raw in (None, "", "not-a-token", token_for(row()) + "x"):
            payload, error = account.read_email_change_token(signer(), raw, row=row())
            assert payload is None and error

    def test_a_token_signed_with_another_key_is_refused(self):
        other = account.email_change_signer("a-different-key-entirely-0000000")
        raw = account.make_email_change_token(
            other, admin_id=7, old_email="old@example.org",
            new_email="new@example.org", session_epoch=3)
        payload, error = account.read_email_change_token(signer(), raw, row=row())
        assert payload is None and error

    def test_it_expires(self):
        raw = token_for(row())
        stale = account.email_change_signer(SECRET)
        stale._max_age = -1          # every signature is now "too old"
        payload, error = account.read_email_change_token(stale, raw, row=row())
        assert payload is None and error

    def test_it_dies_when_the_epoch_moves(self):
        """A password change, role change or deactivation cancels a pending
        address change — that is what makes "I changed my password because I
        think somebody was in my account" actually close the door."""
        raw = token_for(row())
        payload, error = account.read_email_change_token(
            signer(), raw, row=row(session_epoch=4))
        assert payload is None
        assert "changed after it was sent" in error

    def test_it_dies_when_the_address_already_moved(self):
        """Otherwise redeeming an older link would silently undo a newer
        change, and the account would land on an address nobody chose last."""
        raw = token_for(row())
        payload, error = account.read_email_change_token(
            signer(), raw, row=row(email="somewhere-else@example.org"))
        assert payload is None and error

    def test_a_token_for_another_account_is_refused(self):
        raw = token_for(row())
        payload, error = account.read_email_change_token(
            signer(), raw, row=row(id=8))
        assert payload is None and error

    def test_the_target_address_is_validated_on_the_way_back_in(self):
        """The payload is signed, not trusted: a link issued before the rule
        tightened must not be able to write an address the rule now rejects."""
        raw = account.make_email_change_token(
            signer(), admin_id=7, old_email="old@example.org",
            new_email="not-an-address", session_epoch=3)
        payload, error = account.read_email_change_token(signer(), raw, row=row())
        assert payload is None and error

    def test_the_expiry_matches_what_the_mail_promises(self):
        from phronon_common import emails
        assert account.EMAIL_CHANGE_MAX_AGE == emails.EMAIL_CHANGE_HOURS * 3600


# ── what the journal is allowed to see ───────────────────────────────────────

class TestTheNewMailsKeepTheJournalClean:
    """A confirm link is a live credential — it changes who owns an account.
    It is held to the rule the reset link was put under on 16 August 2026:
    never in the journal, and never the full address either."""

    LINK = "https://example.org/backoffice/account/email/confirm?token=SECRET-TOKEN"

    def _send(self, caplog, monkeypatch, fn, *args):
        import logging
        from phronon_common import emails
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.delenv("LOG_RESET_LINKS", raising=False)
        monkeypatch.setenv("PRODUCTION", "1")
        with caplog.at_level(logging.WARNING, logger=emails.logger.name):
            fn(*args)
        return " ".join(r.getMessage() for r in caplog.records)

    def test_the_confirm_link_is_withheld(self, caplog, monkeypatch):
        from phronon_common import emails
        joined = self._send(caplog, monkeypatch, emails.send_email_change_confirm,
                            "Test Tool", "info@example.org", "new@example.org", self.LINK)
        assert "SECRET-TOKEN" not in joined
        assert "withheld" in joined
        assert "new@example.org" not in joined, "the address is reduced to its domain"

    def test_the_notice_to_the_old_address_names_no_address(self, caplog, monkeypatch):
        from phronon_common import emails
        joined = self._send(caplog, monkeypatch, emails.send_email_change_notice,
                            "Test Tool", "info@example.org", "old@example.org",
                            "new@example.org")
        assert "old@example.org" not in joined and "new@example.org" not in joined
        assert "@example.org" in joined, "the domain is kept — it is what makes a mail log useful"

    def test_the_two_factor_reset_notice_names_no_address(self, caplog, monkeypatch):
        from phronon_common import emails
        joined = self._send(caplog, monkeypatch, emails.send_two_factor_reset_notice,
                            "Test Tool", "info@example.org", "who@example.org",
                            "https://example.org/backoffice/account")
        assert "who@example.org" not in joined

    def test_the_link_is_logged_only_when_explicitly_switched_on(self, caplog, monkeypatch):
        import logging
        from phronon_common import emails
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.setenv("LOG_RESET_LINKS", "1")
        with caplog.at_level(logging.WARNING, logger=emails.logger.name):
            emails.send_email_change_confirm("Test Tool", "info@example.org",
                                             "new@example.org", self.LINK)
        assert "SECRET-TOKEN" in " ".join(r.getMessage() for r in caplog.records)
