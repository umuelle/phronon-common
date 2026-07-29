"""Two-factor login for ADMIN accounts (TO DO A1) — standard library only.

WHAT THIS IS
TOTP, RFC 6238: the six-digit code an authenticator app shows (Google
Authenticator, 1Password, Aegis, Microsoft Authenticator…). The server and the
app share one secret, both compute a code from that secret and the current
30-second time step, and the codes match. Nothing is sent anywhere and it works
offline.

WHY NO LIBRARY
`pyotp` would be the obvious choice, but TOTP is ~20 lines of HMAC and this
fleet pins every dependency with a checksum in nine separate lock files. A new
package means nine lock rebuilds and nine more things to audit, for code that
is smaller than its own installation instructions. The same reasoning already
applied to the accessibility checker. Correctness is pinned by tests using the
published RFC 6238 test vectors, so this cannot silently drift from the spec.

SCOPE — ADMINS ONLY (the user's decision, 29 July 2026)
Educators are not asked for a second factor. They are numerous, often
first-time users on a teaching day, and a lockout mid-class is a worse outcome
than the risk it removes. Admins can change other people's accounts and see
every class, so they carry the requirement.

RECOVERY
Ten single-use backup codes are issued at enrolment and stored as bcrypt
hashes, never in clear. Losing the phone is the normal failure here, and
without them the only recovery is a database edit.

CLOCK DRIFT
`verify` accepts the previous and next 30-second step as well as the current
one (±30 s). That is the usual allowance; it costs one extra guess in 10^6 and
saves a support conversation with someone whose phone clock is slightly off.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30           # seconds per code, per RFC 6238
DRIFT_STEPS = 1       # accept ±1 step (±30 s) either side of now
BACKUP_CODE_COUNT = 10


def generate_secret() -> str:
    """A fresh base32 TOTP secret (160 bits, the RFC 4226 recommendation)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The `otpauth://` URI an authenticator app reads from a QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    return (f"otpauth://totp/{label}?secret={secret}"
            f"&issuer={quote(issuer, safe='')}&algorithm=SHA1"
            f"&digits={DIGITS}&period={PERIOD}")


def _code_at(secret: str, counter: int) -> str:
    """One HOTP value — the dynamic-truncation step of RFC 4226."""
    padding = "=" * (-len(secret) % 8)
    key = base64.b32decode(secret.upper() + padding, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def current_code(secret: str, at: float | None = None) -> str:
    """The code valid right now — used by tests and by enrolment confirmation."""
    return _code_at(secret, int((at if at is not None else time.time()) // PERIOD))


def verify(secret: str, code: str, at: float | None = None) -> bool:
    """True if `code` is valid now, or one step either side of now.

    Compared in constant time so a wrong code cannot be narrowed down by timing.
    """
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return False
    step = int((at if at is not None else time.time()) // PERIOD)
    for delta in range(-DRIFT_STEPS, DRIFT_STEPS + 1):
        if hmac.compare_digest(_code_at(secret, step + delta), code):
            return True
    return False


# ── recovery codes ───────────────────────────────────────────────────────────

def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> list[str]:
    """Human-transcribable single-use codes, shown once at enrolment."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1 — misread on paper
    codes = []
    for _ in range(count):
        raw = "".join(secrets.choice(alphabet) for _ in range(10))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def normalise_backup_code(code: str) -> str:
    return (code or "").strip().upper().replace(" ", "").replace("-", "")


def hash_backup_codes(codes: list[str], bcrypt_module) -> list[str]:
    """bcrypt hashes for storage. `bcrypt` is passed in so this module keeps
    importing nothing outside the standard library."""
    return [
        bcrypt_module.hashpw(normalise_backup_code(c).encode(), bcrypt_module.gensalt()).decode()
        for c in codes
    ]


def consume_backup_code(code: str, hashes: list[str], bcrypt_module):
    """Check a backup code against the stored hashes.

    Returns the remaining hashes with the used one removed, or None if the code
    does not match any. Single use is the point: a code that has been typed once
    is gone, so a written-down list that leaks is worth less over time.
    """
    candidate = normalise_backup_code(code).encode()
    if not candidate:
        return None
    for h in hashes:
        try:
            if bcrypt_module.checkpw(candidate, h.encode()):
                return [x for x in hashes if x != h]
        except (ValueError, TypeError):
            continue
    return None
