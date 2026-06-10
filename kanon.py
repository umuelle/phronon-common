"""
k-anonymity display decisions.

Moral Mirror's corrected privacy model (see MoralMirror-Development-Concept.md §4):

  * WHOLE-CLASS / SESSION totals  → always displayed (an undifferentiated aggregate
    points to no individual), even for a class of 5 or fewer.
  * RANDOMIZED condition / variant cells → always displayed, regardless of cell size.
    Condition is randomly assigned, not a personal attribute, so nobody can tell who
    answered which version. Small cells are a *statistical-noise* concern, never a
    privacy one.
  * DEMOGRAPHIC segment breakdowns → suppressed when the segment has < threshold
    participants. A demographic + small n is the only real re-identification surface.

This module is pure (no DB, no framework) so it is trivially unit-testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# In-class live view threshold; exports use a higher bar.
LIVE_DEMOGRAPHIC_MIN = 5
EXPORT_DEMOGRAPHIC_MIN = 10


class CellKind(str, Enum):
    CLASS_TOTAL = "class_total"
    CONDITION = "condition"          # randomized between-subjects variant
    DEMOGRAPHIC = "demographic"      # segment by program / role / boss-status / ...


@dataclass(frozen=True)
class DisplayDecision:
    show: bool
    reason: str


def demographic_threshold(*, export: bool = False) -> int:
    return EXPORT_DEMOGRAPHIC_MIN if export else LIVE_DEMOGRAPHIC_MIN


def decide(kind: CellKind, n: int, *, export: bool = False) -> DisplayDecision:
    """Return whether a result cell of `kind` with `n` participants may be displayed.

    Only DEMOGRAPHIC cells are ever suppressed. Class totals and randomized condition
    cells always display.
    """
    if kind in (CellKind.CLASS_TOTAL, CellKind.CONDITION):
        return DisplayDecision(True, "non-identifying aggregate")
    if kind is CellKind.DEMOGRAPHIC:
        threshold = demographic_threshold(export=export)
        if n >= threshold:
            return DisplayDecision(True, f"demographic cell n={n} ≥ {threshold}")
        return DisplayDecision(
            False,
            f"demographic cell n={n} < {threshold} — not enough participants to break down safely",
        )
    raise ValueError(f"unknown cell kind: {kind!r}")


def suppress_message() -> str:
    return "Not enough participants to break this down safely."
