"""
Collision-checked join-code generation — the fleet's one definition of what a
join code may contain. Short, uppercase, human-legible from the back of a room.

Used by every tool that hands a code to participants: ControversyGenerator
(survey codes), Drawbridge, Inequality, LSR Profiler, Layoff, Moral Mirror and
OrgDesignSim (class/session/scenario codes). Whiteout keeps its own copy of the
alphabet because it pairs it with a look-alike rescue lookup; the two must stay
in step.
"""
from __future__ import annotations

import secrets
from typing import Callable

# O/0 and I/1 are indistinguishable in most sans-serif faces, and a join code is
# read off a projected slide at the back of a room, then typed on a phone. This
# governs GENERATION only — an educator may still type a custom code containing
# them, and codes already in the database keep working.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I, O, 0, 1


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
