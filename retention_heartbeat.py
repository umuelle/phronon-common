"""Last-successful-run heartbeat for the fleet's retention workers (FL-050).

Every tool's retention sweep is a daemon thread inside its uvicorn process —
no timer, no cron — so a dead worker used to look exactly like a quiet week:
the 2 Sep 2026 MySQL upgrade proved a whole SERVICE can stop and only the
service monitor notices; a thread dying inside a healthy service had nothing
watching it at all, and DELETION-JOBS.md's own open question admitted the
inventory was verified by reading code, not by monitoring.

The shape: after each SUCCESSFUL pass the worker upserts the single row of
`retention_runs` (id = 1, `finished_at` in UTC, a short human `detail`), and
the server's alert timer (server-ops/alert_check.py) mails when a tool's row
is older than its sweep interval allows. A pass that raises records nothing —
the point is that silence goes stale and stale gets mailed.

The table is created by each tool's own migration (and lives in its
schema.sql); SCHEMA below is the reference definition the migrations copy, in
the audit.py tradition. record() NEVER raises: a monitoring write must not be
able to kill the worker it monitors.
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE retention_runs (
  id TINYINT NOT NULL,
  finished_at DATETIME NOT NULL,
  detail VARCHAR(255) NOT NULL DEFAULT '',
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

# One statement, UTC on the DATABASE clock — the alert compares against
# UTC_TIMESTAMP() too, so app-host clock drift cannot fake staleness.
_UPSERT = (
    "INSERT INTO retention_runs (id, finished_at, detail) "
    "VALUES (1, UTC_TIMESTAMP(), %s) "
    "ON DUPLICATE KEY UPDATE finished_at = UTC_TIMESTAMP(), detail = VALUES(detail)"
)


def record(get_db: Callable, detail: str = "") -> None:
    """Stamp a successful retention pass. Call AFTER the pass, inside its try.

    `get_db` is the tool's connection factory (the same callable the tools
    already hand to audit.prune). Failures are logged and swallowed.
    """
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(_UPSERT, [detail[:255]])
            conn.commit()
            cur.close()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — must never kill the worker
        logger.warning("retention heartbeat not recorded: %s", exc)
