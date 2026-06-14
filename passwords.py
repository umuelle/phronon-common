"""Shared password policy — one definition used by every tool (harmonization).

Policy (decided June 14, 2026): minimum 12 characters, NO composition rules.
This follows NIST SP 800-63B — length beats forced upper/lower/digit complexity,
which only pushes users toward predictable patterns (e.g. "Password1!") and more
reset requests. Change the policy here and the whole fleet follows.

Apply `validate_password()` everywhere a password is set: create-user, admin
set-password, self-service reset, and change-password. Show `PASSWORD_HINT` next
to password inputs so the requirement is stated consistently.
"""
from __future__ import annotations

MIN_LENGTH = 12
PASSWORD_HINT = f"At least {MIN_LENGTH} characters."


def validate_password(password: str) -> tuple[bool, str]:
    """Return (ok, message). `message` is empty when ok, else a human reason."""
    pw = password or ""
    if len(pw) < MIN_LENGTH:
        return False, f"Password must be at least {MIN_LENGTH} characters."
    return True, ""
