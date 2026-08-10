"""Shared password policy — one definition used by every tool (harmonization).

Policy (decided June 14, 2026): minimum 12 characters, NO composition rules.
This follows NIST SP 800-63B — length beats forced upper/lower/digit complexity,
which only pushes users toward predictable patterns (e.g. "Password1!") and more
reset requests. Change the policy here and the whole fleet follows.

Upper bound added 10 August 2026 (owner's decision, re-audit item V1). bcrypt
cannot hash more than 72 BYTES: the library refuses a longer input outright, so
every tool sliced the password to 72 before hashing. That slice is what let a
longer password through at all — and therefore what made **two passwords sharing
their first 72 bytes open the same account**. Someone setting a 100-character
passphrase was really protected by 72 of them, and was never told.

Three remedies were considered. Hashing to a fixed length first (bcrypt-SHA256)
or moving to Argon2id would remove the limit entirely, but both need a versioned
hash format and a re-hash of every existing account on next login. The owner
chose the honest, small one: **refuse what we cannot hash, at the moment it is
set.** No migration, nobody locked out, and a limit that was silent becomes
visible.

The slicing at the hashing sites STAYS, and deliberately: an account whose
password was set before today may have a hash built from a truncated password,
and removing the slice from verification alone would lock that person out.

Apply `validate_password()` everywhere a password is set: create-user, admin
set-password, self-service reset, and change-password. Show `PASSWORD_HINT` next
to password inputs so the requirement is stated consistently.
"""
from __future__ import annotations

MIN_LENGTH = 12
# bcrypt's hard limit, in BYTES. Not characters: "ü" is two bytes in UTF-8 and
# an emoji is four, so a 40-character passphrase can exceed this. The check
# below measures the encoded length for that reason — counting characters would
# accept a password bcrypt then silently truncates, which is the whole bug.
MAX_BYTES = 72
# Both bounds, and they are in DIFFERENT units. The minimum is characters; the
# maximum is bytes, because that is bcrypt's actual limit. "Between 12 and 72
# characters" was wrong the other way from the original bug — it now UNDER-states
# the ceiling for accented or emoji-heavy passphrases, which reach 72 bytes well
# before 72 visible characters (a "ü" is two bytes, an emoji four). The hint says
# both in their own units; the validator's error message spells out the byte
# count when it is what actually bites.
PASSWORD_HINT = f"At least {MIN_LENGTH} characters, up to {MAX_BYTES} bytes."


def validate_password(password: str) -> tuple[bool, str]:
    """Return (ok, message). `message` is empty when ok, else a human reason."""
    pw = password or ""
    if len(pw) < MIN_LENGTH:
        return False, f"Password must be at least {MIN_LENGTH} characters."
    n = len(pw.encode("utf-8"))
    if n > MAX_BYTES:
        # Say it in characters where that is the truth, and explain the byte
        # count only when it is doing the work — otherwise "72 bytes" reads as
        # a riddle to someone who typed 60 accented characters.
        if len(pw) > MAX_BYTES:
            return False, (
                f"Password must be at most {MAX_BYTES} characters. Longer "
                f"passwords cannot be stored securely and everything past "
                f"{MAX_BYTES} would be ignored."
            )
        return False, (
            f"Password is too long to store securely ({n} bytes; the limit is "
            f"{MAX_BYTES}). Accented characters and emoji count more than one "
            f"byte each — shortening it by a few characters will fix this."
        )
    return True, ""
