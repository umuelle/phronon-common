"""The admin audit trail — one implementation for the whole fleet.

WHY (owner's decision, 12 August 2026 — TO DO FL-002).

Every tool has backoffice accounts that can delete a class, anonymise
responses, create or delete an educator and change a role. The fleet already
answers *who got in* — two-factor, lockout, revocable sessions. Nothing
answered *what they then did*. Two tools had a trail (Orgsim in a table since
1 August, Layoff in a rotating file since 30 July) and seven had none, so after
a compromised account there was nothing to reconstruct.

**A table, not a file.** It is queryable, which is exactly what an educator's
Art. 15 request asks for; it prunes with the retention jobs each tool already
runs; and it is inside the database backup. A file needs its own rotation and
answers none of those.

**Twelve months**, matching what Orgsim and Layoff already used and the ceiling
set for the system log the same day. One number for the fleet is the point: it
is one line in each privacy notice and one period for the legitimate-interest
balance (FL-007) rather than nine.

**This is personal data about educators** — e-mail and IP address — held on
Art. 6(1)(f). That is why it expires, and why every tool's notice says so.

The connection factory is passed in because the tools' db modules do NOT share
an interface: some expose `get_db`, one `get_connection`, another `execute`.
The one thing they all have is a way to hand out a connection.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Twelve months. Change here, in every tool's privacy notice, and in the
# Art. 30 record together — never one alone.
RETENTION_DAYS = 365

# `admin_email` is stored alongside `admin_id` on purpose: the id is a foreign
# key that goes away when an account is deleted, and "who deleted this account"
# is precisely the question an audit trail exists to answer. The row must still
# make sense after its subject is gone, so no FK constraint either.
SCHEMA = """
CREATE TABLE IF NOT EXISTS `audit_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `action` varchar(50) NOT NULL,
  `admin_id` int DEFAULT NULL,
  `admin_email` varchar(255) DEFAULT NULL,
  `subject` varchar(120) DEFAULT NULL,
  `details` json DEFAULT NULL,
  `ip_address` varchar(45) DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audit_log_admin` (`admin_id`),
  KEY `idx_audit_log_action` (`action`),
  KEY `idx_audit_log_created` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

# The events worth a row. Keeping the vocabulary in one place is what makes the
# nine trails comparable — "login_failed" must not be "failed_login" elsewhere.
ACTIONS = (
    "login_success", "login_failed", "login_locked",
    "password_changed", "password_reset_requested", "password_reset_completed",
    "two_factor_enrolled", "two_factor_disabled",
    "admin_created", "admin_deleted", "admin_role_changed",
    "class_deleted", "class_anonymised", "class_archived", "responses_deleted",
    "data_exported",
    # Added 16 August 2026, after an external review found each of them already
    # happening in a tool with no row to show for it.
    #
    # `class_edited` covers the CONFIGURATION of a class/session/survey — its
    # code, date, mode, and the items it asks. Editing those after responses
    # exist changes what the collected answers mean, so "who changed the
    # questions" is exactly the sort of question the trail is for.
    #
    # `participant_email_corrected` was already being written verbatim by
    # Layoff; naming it here is what stops the second tool to need it from
    # inventing "participant_email_fixed".
    "class_edited", "participant_email_corrected",
)


# The trail prunes itself: at most once per process per day, a write also
# deletes rows past the retention window. This is what lets four tools that
# have no background retention worker (Whiteout, Moral Mirror, Drawbridge, the
# hub) keep the 12-month promise without growing one — every deploy's live
# login round-trip writes a row, so every tool prunes at least on deploy, and
# any real sign-in does too. Tools that DO have a worker also call prune()
# there, belt and braces.
_PRUNE_EVERY_SECONDS = 24 * 3600
_last_prune_monotonic: Optional[float] = None


def record(get_conn: Callable[[], Any], action: str, *,
           admin_id: Optional[int] = None, admin_email: Optional[str] = None,
           subject: Optional[str] = None, details: Optional[dict] = None,
           ip: Optional[str] = None) -> None:
    """Write one audit row. Never raises.

    An audit write must not be able to break the action it is recording: a
    failed INSERT here would turn "the class was deleted" into a 500 the
    educator sees, which is a worse outcome than a missing row. Failures are
    logged instead.
    """
    global _last_prune_monotonic
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_log (action, admin_id, admin_email, subject, details, ip_address) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (action, admin_id, admin_email, subject,
             json.dumps(details) if details else None, ip),
        )
        now = time.monotonic()
        if _last_prune_monotonic is None or now - _last_prune_monotonic >= _PRUNE_EVERY_SECONDS:
            _last_prune_monotonic = now
            cur.execute(
                "DELETE FROM audit_log WHERE created_at < (NOW() - INTERVAL %s DAY)",
                (RETENTION_DAYS,),
            )
        conn.commit()
        cur.close()
    except Exception as exc:  # noqa: BLE001 — see the docstring
        logger.warning("audit row not written for %s: %s", action, exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def prune(get_conn: Callable[[], Any], days: int = RETENTION_DAYS) -> int:
    """Delete audit rows older than the retention window; return how many.

    Called from each tool's existing retention worker.
    """
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM audit_log WHERE created_at < (NOW() - INTERVAL %s DAY)",
            (days,),
        )
        deleted = cur.rowcount
        conn.commit()
        cur.close()
        return deleted or 0
    except Exception as exc:  # noqa: BLE001
        logger.error("audit prune failed: %s", exc)
        return 0
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


# There is deliberately NO client_ip() here. phronon_common.rate_limit.client_ip
# already answers "whose address is this request really from", including the
# trusted-proxy rule that stops a caller writing its own address into the log.
# A second copy in this module is how the fleet ends up with two answers — the
# same way it ended up with four copies of one e-mail design.
from phronon_common.rate_limit import client_ip  # noqa: E402,F401 — re-export
