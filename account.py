"""Self-service account management — the parts that must not differ per tool.

WHAT THIS IS FOR
Nine tools let a signed-in educator or admin manage their own account: name,
e-mail address, password, second factor. The ROUTES stay in each app, because
each has its own database layer, session mechanism and template wiring. What
lives here is the part where nine hand-written copies would quietly disagree:
what counts as a valid address, and how an address change is proved.

WHY AN ADDRESS CHANGE NEEDS PROVING (the owner's decision, 17 August 2026)
The e-mail address IS the login, and it is where a password reset is sent.
Changing it therefore hands over the account, twice over:

  * A typo locks the owner out permanently — they cannot sign in under an
    address that does not exist, and cannot reset a password to reach it.
  * Somebody sitting at an unlocked laptop could point the account at their own
    address and take it over at leisure, long after the session expired.

So the new address is only ever WRITTEN once a link mailed to it comes back.
That single rule answers both: an address nobody can receive mail at never
becomes the login, and an address swap needs access to the new mailbox rather
than a borrowed session. The old address is told separately, so the real owner
learns about a change they did not make while the link is still unused.

WHY THE TOKEN BINDS FOUR THINGS
The token carries the account id, the address it was issued FROM, the address
it points TO, and the account's `session_epoch`. The epoch is the one that does
the quiet work: it changes on a password change, a role change, a deactivation
and on an address change itself, so a pending link stops working the moment
anything about the account moves underneath it. Two links requested minutes
apart cannot both land, and a link requested before a password change cannot be
redeemed after it — which is what makes "I have reset my password because I
think somebody was in my account" actually close the door.

There is no `email_change_tokens` table on purpose: the token is signed and
carries its own payload, so an unredeemed change leaves nothing behind to
expire, sweep or forget about.
"""
from __future__ import annotations

import re
import unicodedata

from .emails import EMAIL_CHANGE_HOURS
from .signing import CookieSigner

# Two hours, matching the password-reset link. Long enough to walk to another
# machine and read mail there, short enough that a link found in a mailbox
# months later is worth nothing. The number itself lives in `emails.py`, next to
# the sentence in the mail that promises it.
EMAIL_CHANGE_MAX_AGE = EMAIL_CHANGE_HOURS * 60 * 60

#: Salt for the signer. Distinct from every session/cookie salt in the fleet, so
#: a session cookie can never be replayed as an address-change token or back.
EMAIL_CHANGE_SALT = "phronon-account-email-change"

#: Column length across all nine `admins` tables.
MAX_EMAIL_LENGTH = 255
MAX_NAME_LENGTH = 255

# LSR's rule, promoted: no whitespace anywhere, exactly one @, and a dot in the
# domain. Whiteout's copy allowed spaces and several @s, which is the sort of
# address that is accepted here and then rejected by the mail server, leaving an
# account nobody can reach. Promote the strictest copy, never the most
# convenient (harmonization wave 2, 29 July 2026).
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(value) -> str:
    """Trim and lower-case an address for storage and comparison.

    Lower-casing the whole address is technically wrong — the local part is
    case-sensitive per RFC 5321 — and right in practice: every provider the
    fleet actually meets treats it case-insensitively, the `admins.email`
    UNIQUE key is on a `utf8mb4_unicode_ci` (case-insensitive) column anyway,
    and without this "Urs@…" and "urs@…" would be one row that two different
    typings of the login form disagree about.
    """
    return str(value or "").strip().lower()


def validate_email(value, *, current: str = "") -> tuple[str, str | None]:
    """Return `(normalised_address, error_or_None)`.

    `current` is the address the account has now: changing nothing is reported
    as an error rather than silently mailing a confirmation link for a change
    that would not change anything.
    """
    email = normalise_email(value)
    if not email:
        return "", "Enter an e-mail address."
    if len(email) > MAX_EMAIL_LENGTH:
        return email, f"That address is too long (limit {MAX_EMAIL_LENGTH} characters)."
    if not _EMAIL_RE.match(email):
        return email, "That does not look like an e-mail address."
    if current and email == normalise_email(current):
        return email, "That is already your address."
    return email, None


def validate_name(value) -> tuple[str, str | None]:
    """Return `(cleaned_name, error_or_None)`.

    The name is shown to colleagues in the user list and in audit trails, so it
    is trimmed, stripped of control characters and required to be non-empty —
    an account displayed as a blank cell is one nobody can identify when it
    needs deactivating. Control characters are removed rather than rejected:
    they arrive by paste, not by intent, and a newline pasted into a name would
    otherwise break the line it is rendered on.
    """
    name = "".join(ch for ch in str(value or "")
                   if unicodedata.category(ch)[0] != "C").strip()
    if not name:
        return "", "Enter a name."
    if len(name) > MAX_NAME_LENGTH:
        return name, f"That name is too long (limit {MAX_NAME_LENGTH} characters)."
    return name, None


# ── the address-change link ──────────────────────────────────────────────────

def email_change_signer(secret_key: str | bytes) -> CookieSigner:
    """The signer for address-change links. One per app, built at import time."""
    return CookieSigner(secret_key, salt=EMAIL_CHANGE_SALT,
                        max_age=EMAIL_CHANGE_MAX_AGE)


def make_email_change_token(signer: CookieSigner, *, admin_id, old_email: str,
                            new_email: str, session_epoch) -> str:
    """Sign a pending address change. Nothing is written to the database."""
    return signer.dumps({
        "id": int(admin_id),
        "old": normalise_email(old_email),
        "new": normalise_email(new_email),
        "ep": int(session_epoch or 0),
    })


def read_email_change_token(signer: CookieSigner, raw, *, row) -> tuple[dict | None, str | None]:
    """Check a link against the account row it claims to be for.

    Returns `(payload, error_or_None)`. `row` is the `admins` row as the
    database has it NOW — the signature alone proves only that the fleet issued
    the link, not that it still describes reality. Every check below is one that
    a signature cannot make:

      * the account still exists and is the one the link names;
      * the address it was issued from is still the address on the row, so a
        second change cannot be undone by redeeming an older link;
      * the epoch still matches, so a password change, role change or
        deactivation in between cancels the pending change.

    The messages are deliberately identical in shape and say what to do next.
    They do not distinguish "expired" from "superseded", because the answer is
    the same in both cases and the difference is only useful to somebody
    probing links they did not receive.
    """
    # `_int(x, default)` rather than `x or default` throughout: a session_epoch
    # of 0 is the ordinary state of a brand-new account, and `0 or -1` is -1 —
    # which made every first-ever address change on an untouched account report
    # "the account changed after this was sent". Caught by driving the real flow;
    # the unit tests all happened to use a non-zero epoch.
    def _int(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    payload = signer.loads(raw)
    if not isinstance(payload, dict):
        return None, "That link has expired or has already been used. Request the change again."
    if not row or _int(row.get("id"), 0) != _int(payload.get("id"), -1):
        return None, "That link has expired or has already been used. Request the change again."
    if normalise_email(row.get("email")) != normalise_email(payload.get("old")):
        return None, "That link has expired or has already been used. Request the change again."
    if _int(row.get("session_epoch"), 0) != _int(payload.get("ep"), -1):
        return None, "That link is no longer valid — the account changed after it was sent. Request the change again."
    email, error = validate_email(payload.get("new"), current=row.get("email") or "")
    if error:
        return None, error
    payload["new"] = email
    return payload, None
