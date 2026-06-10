"""
Collision-checked join-code generation (matches Inequality.generate_session_code /
Drawbridge join codes). Short, uppercase, human-legible from the back of a room.
"""
from __future__ import annotations

import secrets
import string
from typing import Callable

# Avoid visually ambiguous characters (0/O, 1/I) for codes read off a projector.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_join_code(
    length: int = 6,
    exists: Callable[[str], bool] | None = None,
    max_attempts: int = 100,
) -> str:
    """Generate a unique join code.

    `exists(code)` should return True if the code is already taken; if omitted, the
    first generated code is returned (no uniqueness guarantee).
    """
    for _ in range(max_attempts):
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if exists is None or not exists(code):
            return code
    raise RuntimeError("Could not generate a unique join code")
