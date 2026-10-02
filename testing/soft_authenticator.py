"""A software passkey authenticator, for tests that execute the real routes.

It does what a phone or a security key does, with a real P-256 key: answers a
registration request with an attestation (format "none") and a sign-in request
with a signature over the authenticator data and the client data. The server
side under test is the real py_webauthn verification, so a route test that
signs in with this has exercised the whole ceremony except the fingerprint.

Usage:

    auth = SoftAuthenticator(origin="https://testserver")
    cred_json = auth.create(options_json)          # registration
    assertion_json = auth.get(options_json)        # sign-in

`user_verified=False` produces a credential or assertion without the UV flag,
which the fleet must refuse; `tamper=True` on `get` breaks the signature.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

_UP, _UV, _AT = 0x01, 0x04, 0x40


@dataclass
class _Credential:
    credential_id: bytes
    key: ec.EllipticCurvePrivateKey
    rp_id: str
    user_handle: bytes
    sign_count: int = 0


@dataclass
class SoftAuthenticator:
    origin: str
    #: Most synced passkeys keep no counter and always report 0.
    counts_signatures: bool = True
    credentials: list[_Credential] = field(default_factory=list)

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin,
                           "crossOrigin": False}).encode()

    def create(self, options_json: str, user_verified: bool = True) -> str:
        opts = json.loads(options_json)
        rp_id = opts["rp"]["id"]
        key = ec.generate_private_key(ec.SECP256R1())
        cred = _Credential(os.urandom(16), key, rp_id, base64url_to_bytes(opts["user"]["id"]))
        nums = key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: nums.x.to_bytes(32, "big"),
                            -3: nums.y.to_bytes(32, "big")})
        flags = _UP | _AT | (_UV if user_verified else 0)
        auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags])
                     + (0).to_bytes(4, "big") + bytes(16)
                     + len(cred.credential_id).to_bytes(2, "big") + cred.credential_id + cose)
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        self.credentials.append(cred)
        return json.dumps({
            "id": bytes_to_base64url(cred.credential_id),
            "rawId": bytes_to_base64url(cred.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(
                    self._client_data("webauthn.create", opts["challenge"])),
                "attestationObject": bytes_to_base64url(attestation),
                "transports": ["internal"],
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        })

    def get(self, options_json: str, credential: _Credential | None = None,
            user_verified: bool = True, tamper: bool = False) -> str:
        opts = json.loads(options_json)
        rp_id = opts.get("rpId") or urlsplit(self.origin).hostname
        cred = credential or next(c for c in reversed(self.credentials) if c.rp_id == rp_id)
        if self.counts_signatures:
            cred.sign_count += 1
        flags = _UP | (_UV if user_verified else 0)
        auth_data = (hashlib.sha256(rp_id.encode()).digest() + bytes([flags])
                     + cred.sign_count.to_bytes(4, "big"))
        client_data = self._client_data("webauthn.get", opts["challenge"])
        signature = cred.key.sign(auth_data + hashlib.sha256(client_data).digest(),
                                  ec.ECDSA(hashes.SHA256()))
        if tamper:
            signature = signature[:-1] + bytes([signature[-1] ^ 1])
        return json.dumps({
            "id": bytes_to_base64url(cred.credential_id),
            "rawId": bytes_to_base64url(cred.credential_id),
            "type": "public-key",
            "response": {
                "clientDataJSON": bytes_to_base64url(client_data),
                "authenticatorData": bytes_to_base64url(auth_data),
                "signature": bytes_to_base64url(signature),
                "userHandle": bytes_to_base64url(cred.user_handle),
            },
            "clientExtensionResults": {},
            "authenticatorAttachment": "platform",
        })
