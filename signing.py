"""
Signed-cookie helpers wrapping itsdangerous URLSafeSerializer, matching the pattern
used in Drawbridge (`_admin_signer`, `_signer`). One serializer per salt/purpose.
"""
from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer


class CookieSigner:
    """Sign/verify small JSON-serialisable payloads for cookies."""

    def __init__(self, secret_key: str | bytes, salt: str):
        if isinstance(secret_key, bytes):
            secret_key = secret_key.decode("utf-8")
        self._serializer = URLSafeSerializer(secret_key, salt=salt)

    def dumps(self, data) -> str:
        return self._serializer.dumps(data)

    def loads(self, raw: str | None):
        """Return the payload, or None if missing/tampered."""
        if not raw:
            return None
        try:
            return self._serializer.loads(raw)
        except BadSignature:
            return None
