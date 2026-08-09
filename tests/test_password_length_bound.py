"""The upper bound on passwords (re-audit V1, owner's decision 10 August 2026).

bcrypt cannot hash more than 72 BYTES — the library refuses a longer input — so
every tool sliced to 72 before hashing. The slice is what let a longer password
through at all, and therefore what made two passwords sharing their first 72
bytes open the same account. The owner chose to refuse what cannot be hashed,
at the moment it is set, rather than migrate every stored hash.
"""
from __future__ import annotations

import bcrypt
import pytest

from phronon_common.passwords import (MAX_BYTES, MIN_LENGTH, validate_password)


def test_the_bound_is_the_one_bcrypt_actually_has():
    """Asserted, not trusted: the whole fix rests on this being 72."""
    with pytest.raises(ValueError):
        bcrypt.hashpw(b'x' * (MAX_BYTES + 1), bcrypt.gensalt())
    bcrypt.hashpw(b'x' * MAX_BYTES, bcrypt.gensalt())      # must not raise


def test_a_password_at_the_limit_is_accepted():
    ok, why = validate_password('x' * MAX_BYTES)
    assert ok, why


def test_a_password_over_the_limit_is_refused():
    ok, why = validate_password('x' * (MAX_BYTES + 1))
    assert not ok
    assert str(MAX_BYTES) in why


def test_the_limit_is_measured_in_BYTES_not_characters():
    """The trap. "ü" is two bytes in UTF-8 and an emoji is four, so a password
    well under 72 CHARACTERS can still exceed what bcrypt will take. Counting
    characters would accept it and bcrypt would then truncate — which is the
    exact bug this bound exists to end."""
    pw = 'ü' * 40                     # 40 characters, 80 bytes
    assert len(pw) < MAX_BYTES < len(pw.encode('utf-8'))
    ok, why = validate_password(pw)
    assert not ok, 'a 40-character password can still be over the byte limit'
    assert 'byte' in why.lower(), 'and the message should explain why'


def test_the_message_names_the_rule_that_failed():
    """A too-LONG password told "must be at least 12 characters" sends the user
    in precisely the wrong direction."""
    _, too_short = validate_password('x' * (MIN_LENGTH - 1))
    _, too_long = validate_password('x' * (MAX_BYTES + 1))
    assert 'at least' in too_short
    assert 'at least' not in too_long
    assert 'at most' in too_long or 'too long' in too_long.lower()


def test_the_ordinary_case_still_passes():
    ok, why = validate_password('a-perfectly-ordinary-passphrase')
    assert ok, why


def test_two_passwords_sharing_72_bytes_can_no_longer_both_be_set():
    """The collision itself. Both of these hash to the same value once sliced;
    the policy now refuses to let either be stored."""
    a, b = 'x' * 72 + 'AAAA', 'x' * 72 + 'ZZZZ'
    assert bcrypt.checkpw(b.encode()[:72],
                          bcrypt.hashpw(a.encode()[:72], bcrypt.gensalt()))
    assert not validate_password(a)[0]
    assert not validate_password(b)[0]
