"""TOTP correctness, pinned to the published RFC 6238 test vectors.

This module implements the algorithm itself rather than depending on `pyotp`
(see the module docstring for why), so it MUST be checked against the
specification's own numbers. If these pass, an authenticator app will agree
with us; if they fail, every admin is locked out.
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common import twofactor as tf  # noqa: E402

# RFC 6238 Appendix B uses the ASCII secret "12345678901234567890" with SHA-1.
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")

# (unix time, expected 8-digit code) straight from the RFC table; we compare the
# last 6 digits because this implementation is 6-digit like every phone app.
RFC_VECTORS = [
    (59,          "94287082"),
    (1111111109,  "07081804"),
    (1111111111,  "14050471"),
    (1234567890,  "89005924"),
    (2000000000,  "69279037"),
    (20000000000, "65353130"),
]


@pytest.mark.parametrize("when,expected8", RFC_VECTORS)
def test_matches_the_rfc6238_published_vectors(when, expected8):
    assert tf.current_code(RFC_SECRET, at=when) == expected8[-6:]


def test_a_code_verifies_within_its_own_time_step():
    secret = tf.generate_secret()
    assert tf.verify(secret, tf.current_code(secret, at=1000), at=1000)


def test_clock_drift_of_one_step_either_side_is_accepted():
    secret = tf.generate_secret()
    code = tf.current_code(secret, at=1000)
    assert tf.verify(secret, code, at=1000 + tf.PERIOD), "phone 30s fast must still work"
    assert tf.verify(secret, code, at=1000 - tf.PERIOD), "phone 30s slow must still work"


def test_a_code_two_steps_away_is_refused():
    secret = tf.generate_secret()
    code = tf.current_code(secret, at=1000)
    assert not tf.verify(secret, code, at=1000 + 3 * tf.PERIOD)


def test_rubbish_is_refused_without_raising():
    secret = tf.generate_secret()
    for bad in ["", None, "abcdef", "12345", "1234567", "  ", "12 34 56"]:
        assert not tf.verify(secret, bad)
    assert not tf.verify("", "123456")


def test_two_secrets_do_not_share_codes():
    a, b = tf.generate_secret(), tf.generate_secret()
    assert not tf.verify(b, tf.current_code(a, at=1000), at=1000)


def test_provisioning_uri_is_well_formed_and_escaped():
    uri = tf.provisioning_uri("ABC234", "urs@example.org", "LSR Profiler")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC234" in uri and "period=30" in uri and "digits=6" in uri
    assert " " not in uri, "spaces must be percent-encoded or the QR breaks"


# ── recovery codes ───────────────────────────────────────────────────────────

class _FakeBcrypt:
    """Enough bcrypt to test the flow without the real cost factor."""
    @staticmethod
    def gensalt():
        return b"salt"
    @staticmethod
    def hashpw(pw, salt):
        return b"h:" + pw
    @staticmethod
    def checkpw(pw, h):
        return h == b"h:" + pw


def test_backup_codes_are_distinct_and_readable():
    codes = tf.generate_backup_codes()
    assert len(codes) == tf.BACKUP_CODE_COUNT == len(set(codes))
    for c in codes:
        assert "-" in c
        assert not set(c) & set("IO01"), "characters that get misread on paper"


def test_a_backup_code_works_once_and_is_then_gone():
    codes = tf.generate_backup_codes()
    hashes = tf.hash_backup_codes(codes, _FakeBcrypt)
    remaining = tf.consume_backup_code(codes[0], hashes, _FakeBcrypt)
    assert remaining is not None and len(remaining) == len(hashes) - 1
    assert tf.consume_backup_code(codes[0], remaining, _FakeBcrypt) is None, "single use"


def test_backup_codes_are_accepted_however_they_are_typed():
    codes = tf.generate_backup_codes()
    hashes = tf.hash_backup_codes(codes, _FakeBcrypt)
    typed = codes[0].lower().replace("-", " ")
    assert tf.consume_backup_code(typed, hashes, _FakeBcrypt) is not None


def test_a_wrong_backup_code_changes_nothing():
    hashes = tf.hash_backup_codes(tf.generate_backup_codes(), _FakeBcrypt)
    assert tf.consume_backup_code("NOPE1-NOPE2", hashes, _FakeBcrypt) is None
