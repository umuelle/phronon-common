"""
Signed-cookie helpers wrapping itsdangerous, matching the pattern used across the
fleet (`_admin_signer`, `_fac_signer`, …). One serializer per salt/purpose.

WHY THIS IS *TIMED* (changed 2026-07-27)
This used to wrap `URLSafeSerializer`, whose signature never expires. The cookie
carried `Max-Age=8h`, but that is only an instruction to the browser — it is not
a security boundary. Anyone who copied a session cookie (from a shared machine,
a backup, a proxy log) could replay it indefinitely, because the server had no
way to tell an hour-old cookie from a year-old one.

It now wraps `URLSafeTimedSerializer`, and every `loads()` enforces a maximum age
server-side. An expired cookie is refused exactly like a tampered one.

Changing this invalidates existing sessions once, which is the intended effect.
"""
from __future__ import annotations

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .sessions import MAX_SESSION_AGE

# The CEILING for a backoffice session, not the whole answer: since 2026-08-19
# the fleet's session length depends on the role holding it (educators 6 h,
# admins 3 h — see `sessions.max_age_for`). A signer can only enforce the age
# it was built with, and it is built before anyone has logged in, so it
# enforces the longest of the two; the caller narrows it once it has read the
# account row. Was a flat 4 h from 2026-07-29 (and 8 h before that).
DEFAULT_MAX_AGE = MAX_SESSION_AGE


class CookieSigner:
    """Sign/verify small JSON-serialisable payloads for cookies, with an age limit."""

    def __init__(self, secret_key: str | bytes, salt: str, max_age: int = DEFAULT_MAX_AGE):
        if isinstance(secret_key, bytes):
            secret_key = secret_key.decode("utf-8")
        self._serializer = URLSafeTimedSerializer(secret_key, salt=salt)
        self._max_age = max_age

    def dumps(self, data) -> str:
        return self._serializer.dumps(data)

    def loads(self, raw: str | None, max_age: int | None = None):
        """Return the payload, or None if missing, tampered with, or too old.

        `max_age=0` means "do not enforce an age" — used only for cookies that
        are deliberately long-lived, such as a participant's link into a class
        that may legitimately span weeks.
        """
        if not raw:
            return None
        limit = self._max_age if max_age is None else max_age
        try:
            if not limit:
                return self._serializer.loads(raw)
            return self._serializer.loads(raw, max_age=limit)
        except (BadSignature, SignatureExpired):
            # SignatureExpired subclasses BadSignature; both named for clarity.
            return None
