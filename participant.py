"""One participant identity, resume and withdrawal mechanism for the fleet.

Owner's decision, 3 September 2026 — every participant tool uses:

  * a RANDOM PARTICIPANT ID (16 bytes, urlsafe) as the only credential a
    browser holds; never an auto-increment id, never an e-mail address;
  * a SIGNED, HttpOnly RESUME COOKIE carrying that id, timed server-side to
    PARTICIPANT_COOKIE_MAX_AGE (8 hours, fleet-wide);
  * e-mail required / optional / not collected exactly as each tool already
    decided — this module does not change that;
  * a WITHDRAWAL TOKEN (32 bytes) stored HASHED everywhere, on the teaching
    row and on whatever survives the retention transformation;
  * RECOVERY BY ROTATION where an address exists: a "send me my link" request
    (and the 7-day retention warning) mints a fresh token, stores its hash,
    mails the new link. Nothing raw is ever kept, and nothing is unrecoverable
    for someone who can read the mailbox they joined with;
  * a one-time, 30-minute e-mailed RESUME LINK for rejoining from a device
    that does not hold the cookie (Whiteout's design of 9 August 2026);
  * SELF-SERVICE DELETION at /withdraw before the transformation — the typed
    word on the page, refused server-side (README §3), CSRF enforced, rate
    limited 10 per 5 minutes — and the same route deleting the pseudonymous
    research row for as long as it exists.

WHY HASH + ROTATE rather than Whiteout's raw-on-the-teaching-row (15 August
2026): that rule existed because the warning mail had to COMPOSE a link, and
composing needs the raw. Rotation composes a new one instead. A database read
(backup, dump, injection, export) then hands an attacker nobody's deletion
credential, and a participant who lost a link asks for another.

The helpers here take the tool's own DB callables rather than a connection,
because the nine tools have four different DB modules. The contract:

    execute(sql, params) -> int     # rowcount of the statement
    query_one(sql, params) -> dict | None
"""
from __future__ import annotations

import hashlib
import re
import secrets
from typing import Callable, Optional

from .signing import CookieSigner

# ── The numbers ─────────────────────────────────────────────────────────────
PARTICIPANT_ID_BYTES = 16
TOKEN_BYTES = 32
PARTICIPANT_COOKIE_MAX_AGE = 8 * 60 * 60        # seconds; one class day
RESUME_LINK_MINUTES = 30
RESUME_LINKS_PER_WINDOW = 3                     # per participant …
RESUME_LINK_WINDOW_MINUTES = 15                 # … per this many minutes
WITHDRAW_RATE_LIMIT = (10, 300)                 # requests, seconds (RateLimitConfig)
TOKEN_MIN_LENGTH = 20
TOKEN_MAX_LENGTH = 128

# The typed confirmation word. Polarity Profiler accepts every locale's word,
# which is the better rule: a German reader should not have to know that the
# English page says DELETE. Since 6 October 2026 the set holds every word a
# fleet page shows (Layoff's ten languages, Polarity Profiler's WITHDRAWAL /
# WIDERRUF), so any tool accepts any of them (withdrawal_kit).
WITHDRAW_CONFIRM_WORDS = frozenset({
    "DELETE", "LÖSCHEN", "LOESCHEN", "WITHDRAWAL", "WIDERRUF",
    "SUPPRIMER", "ELIMINAR", "ELIMINA", "EXCLUIR", "УДАЛИТЬ", "删除", "حذف", "हटाएँ",
})

_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]+")


# ── Identity and tokens ─────────────────────────────────────────────────────

def new_participant_id() -> str:
    """The credential a browser holds. Unique-indexed per tool."""
    return secrets.token_urlsafe(PARTICIPANT_ID_BYTES)


def hash_token(raw: str) -> str:
    """SHA-256 hex of a bearer token — what the database stores."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_token() -> tuple[str, str]:
    """(raw, hash). The raw goes to the participant once; the hash to the row."""
    raw = secrets.token_urlsafe(TOKEN_BYTES)
    return raw, hash_token(raw)


def plausible_token(raw: Optional[str]) -> bool:
    """Shape check before touching the database: length floor and alphabet.

    Refusing short or odd strings early keeps the hashed lookup from being a
    free oracle for junk, and keeps `token=` garbage out of the logs.
    """
    return bool(raw) and TOKEN_MIN_LENGTH <= len(raw) <= TOKEN_MAX_LENGTH \
        and _TOKEN_RE.fullmatch(raw) is not None


def confirm_word_ok(typed: Optional[str], extra_words=()) -> bool:
    """The participant typed the confirmation word (any accepted locale)."""
    word = (typed or "").strip().upper()
    return bool(word) and (word in WITHDRAW_CONFIRM_WORDS or word in {w.upper() for w in extra_words})


# ── The resume cookie ───────────────────────────────────────────────────────

class ParticipantCookie:
    """The one participant cookie: signed, timed, HttpOnly, SameSite=Lax.

    `secure` is a constructor argument on purpose — pass the tool's PRODUCTION
    flag — rather than derived per request from X-Forwarded-Proto, which let a
    plain-HTTP request mint a non-Secure cookie in two tools.
    """

    def __init__(self, secret_key, name: str, *, secure: bool,
                 max_age: int = PARTICIPANT_COOKIE_MAX_AGE, salt: str = "participant"):
        self.name = name
        self.secure = bool(secure)
        self.max_age = int(max_age)
        self._signer = CookieSigner(secret_key, salt=salt, max_age=self.max_age)

    def mint(self, participant_id: str) -> str:
        """The signed cookie VALUE, without a response to put it on.

        `set` is what routes use. This exists because every tool's tests need
        to hand a TestClient a valid participant cookie, and the alternative
        was eight copies of a reach into the private signer — which is also
        eight tests that keep passing after the signing rule changes under
        them.
        """
        return self._signer.dumps(participant_id)

    def set(self, response, participant_id: str) -> None:
        response.set_cookie(
            self.name, self.mint(participant_id),
            max_age=self.max_age, httponly=True, samesite="lax",
            secure=self.secure, path="/",
        )

    def read(self, request) -> Optional[str]:
        value = self._signer.loads(request.cookies.get(self.name))
        return value if isinstance(value, str) and value else None

    def clear(self, response) -> None:
        response.delete_cookie(self.name, path="/")


# ── Resume links (cross-device rejoin) ──────────────────────────────────────
# One table per tool, same shape everywhere. `participant_ref` is the tool's
# participant id (the random one), so the table never learns a real name.
RESUME_TOKENS_TABLE = "participant_resume_tokens"
# NO `DEFAULT CHARSET` CLAUSE, AND THAT IS THE POINT (3 September 2026).
# The first version of this DDL ended `DEFAULT CHARSET=utf8mb4`, which on
# MySQL 8 silently means `utf8mb4_0900_ai_ci` — while the fleet's older
# databases are `utf8mb4_unicode_ci`. Naming the charset without its collation
# therefore OVERRIDES the database default and makes this table disagree with
# the very table it points at. Comparing the two columns then raises
# "Illegal mix of collations" (error 1267) — inside an hourly retention worker
# that catches its own exceptions, so anonymisation would simply stop, visible
# only as a stale heartbeat. Two tools' test suites caught it independently.
# Omitting the clause makes the table inherit its database's own collation,
# which is how every sibling table got theirs, in every tool, whatever the
# server default happens to be. Do not "tidy" a charset back in here.
#
# AND IF YOUR TOOL JOINS THIS TABLE TO ITS PARTICIPANT TABLE, name the
# collation in your own migration to match THAT TABLE — not the database.
# Inheriting is right only while the two agree, and in this fleet they do not
# always: an older table can carry a collation its database no longer
# defaults to. OrgDesignSim and Polarity Profiler both join (their sweeps
# delete a class's resume links through the participant row) and both name
# `COLLATE=utf8mb4_unicode_ci` for that reason. Tools that only ever compare
# participant_ref with a bound parameter — the helpers below all do — are safe
# either way, because a parameter takes the column's collation.
RESUME_TOKENS_DDL = f"""CREATE TABLE IF NOT EXISTS `{RESUME_TOKENS_TABLE}` (
  `id` int NOT NULL AUTO_INCREMENT,
  `participant_ref` varchar(64) NOT NULL,
  `token_hash` char(64) NOT NULL,
  `expires_at` datetime NOT NULL,
  `used` tinyint(1) NOT NULL DEFAULT 0,
  `created_at` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_resume_token_hash` (`token_hash`),
  KEY `idx_resume_participant` (`participant_ref`)
) ENGINE=InnoDB"""


def _resume_throttled(query_one: Callable, participant_ref: str) -> bool:
    """Three links per fifteen minutes per participant, so a stranger who
    knows an address cannot flood a mailbox."""
    recent = query_one(
        f"SELECT COUNT(*) AS n FROM {RESUME_TOKENS_TABLE} WHERE participant_ref = %s "
        f"AND created_at > DATE_SUB(NOW(), INTERVAL {RESUME_LINK_WINDOW_MINUTES} MINUTE)",
        (participant_ref,))
    return bool(recent) and int(recent["n"] or 0) >= RESUME_LINKS_PER_WINDOW


def _store_resume_token(execute: Callable, participant_ref: str, digest: str) -> None:
    """Retire any live link (one live link per participant), then store the
    new hash with a RESUME_LINK_MINUTES expiry."""
    execute(f"UPDATE {RESUME_TOKENS_TABLE} SET used = 1 WHERE participant_ref = %s AND used = 0",
            (participant_ref,))
    execute(f"INSERT INTO {RESUME_TOKENS_TABLE} (participant_ref, token_hash, expires_at) "
            f"VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL {RESUME_LINK_MINUTES} MINUTE))",
            (participant_ref, digest))


def send_resume_link(execute: Callable, query_one: Callable, participant_ref: str,
                     send: Callable[[str], object], logger, where: str) -> Optional[bool]:
    """Mail a one-time resume link, and store it only once the mail went out.

    `send(raw)` mails the link that carries the raw token and answers True
    once the mail server took it, False when nothing was sent (None, from a
    sender that does not say, counts as sent). Only then is the earlier link
    retired and the new one stored, so a mail that never left keeps the
    earlier link working: the rule `withdrawal_kit.send_fresh_links` follows
    for deletion links (TO DO FL-104, 26 October 2026). Until then the link
    was stored first and a failed send left the participant with no working
    link at all. A failed send also no longer counts against the throttle,
    which counts stored links.

    Answers None when throttled (nothing sent), True when the link was mailed
    and stored, False otherwise. Never raises for a failed send or store: the
    caller shows the same page either way, so this logs it. `where` names the
    session and the recipient DOMAIN (`emails.recipient_domain`), never the
    address (FL-022).
    """
    if _resume_throttled(query_one, participant_ref):
        return None
    raw, digest = new_token()
    try:
        sent = send(raw)
    except Exception:  # noqa: BLE001 - the page reads the same either way; logged with the traceback
        logger.exception("Resume link for %s failed; the earlier link still works", where)
        return False
    if sent is False:
        logger.warning("Resume link for %s not sent; the earlier link still works", where)
        return False
    try:
        _store_resume_token(execute, participant_ref, digest)
    except Exception:  # noqa: BLE001 - logged with the traceback; the mailed link cannot work
        logger.exception("Resume link for %s sent but not stored; the earlier link still "
                         "works, the mailed one does not", where)
        return False
    return True


def issue_resume_token(execute: Callable, query_one: Callable, participant_ref: str) -> Optional[str]:
    """Mint and store a one-time resume token; None if throttled.

    Stores before the caller sends, which `send_resume_link` replaced in
    1.89.0. Kept until every tool's live commit calls `send_resume_link`:
    a release's verify runs the live commits against it (TO DO FL-104).
    """
    if _resume_throttled(query_one, participant_ref):
        return None
    raw, digest = new_token()
    _store_resume_token(execute, participant_ref, digest)
    return raw


def peek_resume_token(query_one: Callable, raw: Optional[str]) -> Optional[dict]:
    """The live row for a raw token, WITHOUT spending it (the GET confirm page)."""
    if not plausible_token(raw):
        return None
    return query_one(
        f"SELECT id, participant_ref FROM {RESUME_TOKENS_TABLE} "
        "WHERE token_hash = %s AND used = 0 AND expires_at > NOW()",
        (hash_token(raw),))


def spend_resume_token(execute: Callable, row_id: int) -> bool:
    """Atomically mark one token used; False if someone else got there first."""
    return execute(
        f"UPDATE {RESUME_TOKENS_TABLE} SET used = 1 WHERE id = %s AND used = 0 AND expires_at > NOW()",
        (row_id,)) == 1


def forget_resume_tokens(execute: Callable, participant_ref: str) -> None:
    """On withdrawal or transformation: nothing may resume a deleted pass."""
    execute(f"DELETE FROM {RESUME_TOKENS_TABLE} WHERE participant_ref = %s", (participant_ref,))
