"""Reading a published cookie lifetime: `lifetime_seconds()`.

Until 25 October 2026 this file also held `TOOLS`, all nine tools' notice
content in one table. Each tool publishes from its own
`legal_content/notice.json` since 4 October 2026 (phronon_common/legal_content.py
says why), and the frozen table stayed only for tool versions older than that,
which a rollback might have restored. It went with FL-079, together with
`get_tool()` and the router's call without `config=`. The fleet-wide
side-by-side view it used to give is server-ops/legal_table.py; git keeps
the history of every notice sentence that was written here.

The parser stays: every reader of the published lifetimes uses it (each
tool's legal-content tests, server-ops/closing_audit.py).
"""

import re

# ── Reading a published lifetime cell ────────────────────────────────────────
# The cookie tables state a lifetime in prose, in whichever language the page is
# in. `server-ops/closing_audit.py` compares those words with the `max_age` the
# app actually sets, and its parser used to live over there and know only
# English — which was fine while the German pages printed the English cells and
# became a hole the day they stopped (19 August 2026).
#
# It moved here because this file held the sentences then (until FL-079). A tool
# gaining a new locale adds its unit words to ONE table, and every reader of the
# published text — the deploy gate and the fleet tests — learns them together.
#
# A unit this table does not know reads as "no number published", which SKIPS
# the row rather than failing it. That is the safe direction for prose like
# "browser session", and the reason both languages are spelled out in full
# rather than matched loosely: a missing word disables a check silently.
LIFETIME_SECONDS = {
    "second": 1, "seconds": 1, "sekunde": 1, "sekunden": 1,
    "minute": 60, "minutes": 60, "minuten": 60,
    "hour": 3600, "hours": 3600, "stunde": 3600, "stunden": 3600,
    "day": 86400, "days": 86400, "tag": 86400, "tage": 86400, "tagen": 86400,
}

#: Longest first, so "stunden" is not matched as "stunde" plus a stray "n".
_UNIT_ALT = "|".join(sorted(LIFETIME_SECONDS, key=len, reverse=True))


def lifetime_seconds(text: str) -> list:
    """Every duration in a published lifetime cell, in seconds.

    "5-15 minutes", "5–15 Minuten" and "browser session / 2 hours" all yield a
    RANGE; a cookie is fine if its real max_age matches any value in it.
    """
    # "5-15 minutes" / "5–15 Minuten": the first number carries no unit of its
    # own, so give it the one that follows before scanning. Both the ASCII
    # hyphen and the en dash appear in the tables.
    text = re.sub(r"(\d+)\s*[-–]\s*(\d+)(\s*)(" + _UNIT_ALT + r")",
                  r"\1 \4 \2\3\4", text, flags=re.I)
    return [int(num) * LIFETIME_SECONDS[unit.lower()]
            for num, unit in re.findall(r"(\d+)\s*(" + _UNIT_ALT + r")", text, re.I)]
