"""Passkeys: sign in with Touch ID, Face ID, Windows Hello or a security key.

Added 2 October 2026 at the owner's request (FL-065), after GitHub offered him
one. Owner's decisions:

- A passkey signs in ON ITS OWN: no password, no six-digit code. It is two
  factors in one (the device you hold, plus the fingerprint, face or PIN that
  unlocks it), which is why every ceremony here REQUIRES user verification. A
  passkey that only proves "somebody touched the key" would be one factor, and
  is refused.
- Password + authenticator code stays as the fallback. Administrators still
  have to enrol an authenticator app (the recovery path when a phone is lost);
  a passkey lets them in without typing its code.

The cryptography is py_webauthn's (Duo Labs), not ours. This module fixes the
fleet's choices around it and is the only place that calls it:

- `userVerification: required`, `residentKey: required` (a discoverable
  credential, so the login page needs no e-mail address first), attestation
  `none` (we do not care which brand of authenticator it is).
- The challenge travels in a signed, HTTP-only cookie that lives five minutes
  (`CHALLENGE_COOKIE`), bound to its purpose ("login", or "register:<account
  id>"), and is deleted once used. The server keeps no challenge table.
- The relying-party id is the tool's own domain without "www.", and both the
  bare and the "www." address are accepted. Each tool is its own domain, so a
  passkey belongs to one tool, exactly as the TOTP entries do today.

What a tool stores per passkey (its `passkeys` table): the credential id, the
public key, the signature counter, a name the user chose, and when it was added
and last used. Nothing biometric ever leaves the user's device; the server never
sees it and could not ask for it.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from webauthn import (base64url_to_bytes, generate_authentication_options,
                      generate_registration_options, options_to_json,
                      verify_authentication_response, verify_registration_response)
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import (InvalidAuthenticationResponse,
                                         InvalidRegistrationResponse)
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                      PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement,
                                      UserVerificationRequirement)

from .signing import CookieSigner

#: The one cookie the ceremonies need. Listed in every tool's cookie table.
CHALLENGE_COOKIE = "passkey_challenge"
#: Five minutes: long enough to find the phone, short enough to be useless later.
CHALLENGE_SECONDS = 300
#: The most passkeys one account may hold. A person has a phone, a laptop and
#: perhaps a key; ten is generous and keeps a stolen session from piling them up.
MAX_PER_ACCOUNT = 10
NAME_MAX = 60


class PasskeyError(Exception):
    """A ceremony that must be refused. The message is safe to show the user."""


@dataclass(frozen=True)
class NewPasskey:
    credential_id: bytes
    public_key: bytes
    sign_count: int


def rp_id_for(base_url: str) -> str:
    """The relying-party id: the tool's host WITHOUT a leading "www.".

    Every site answers on both drawbridge-drama.org and www.drawbridge-drama.org
    (found while porting, 2 October 2026). Browsers let a page use a passkey
    whose rp id is a parent of its own host, so naming the bare domain makes one
    passkey work on both addresses; naming "www." would lock the bare one out."""
    host = urlsplit(base_url if "://" in base_url else f"https://{base_url}").hostname
    if not host:
        raise ValueError(f"no host in {base_url!r}")
    return host[4:] if host.startswith("www.") else host


def origins_for(base_url: str) -> list[str]:
    """The origins the browser may report: the bare host and its "www."
    twin, with the scheme and any port of `base_url`. A local address
    ("localhost", "testserver") has no twin."""
    parts = urlsplit(base_url if "://" in base_url else f"https://{base_url}")
    host = rp_id_for(base_url)
    port = f":{parts.port}" if parts.port else ""
    hosts = [host] if "." not in host else [host, f"www.{host}"]
    return [f"{parts.scheme}://{h}{port}" for h in hosts]


# ── the challenge cookie ─────────────────────────────────────────────────────

def _signer(secret_key) -> CookieSigner:
    return CookieSigner(secret_key, salt="phronon-passkey-challenge",
                        max_age=CHALLENGE_SECONDS)


def seal_challenge(secret_key, challenge: bytes, purpose: str) -> str:
    """The cookie value carrying `challenge` for one `purpose`."""
    return _signer(secret_key).dumps({"c": bytes_to_base64url(challenge), "p": purpose})


def open_challenge(secret_key, cookie_value: str | None, purpose: str) -> bytes | None:
    """The challenge, if the cookie is genuine, fresh and for this purpose."""
    data = _signer(secret_key).loads(cookie_value)
    if not isinstance(data, dict) or data.get("p") != purpose:
        return None
    try:
        return base64url_to_bytes(data["c"])
    except Exception:
        return None


def cookie_kwargs(secure: bool = True) -> dict:
    """How every tool sets the challenge cookie (pass to response.set_cookie)."""
    return {"key": CHALLENGE_COOKIE, "httponly": True, "samesite": "strict",
            "max_age": CHALLENGE_SECONDS, "secure": secure, "path": "/"}


# ── registering a passkey (signed in, from the account page) ─────────────────

def registration_options(*, base_url: str, tool_name: str, user_handle: bytes,
                         user_name: str, existing: list[bytes] = ()) -> tuple[str, bytes]:
    """(options JSON for the browser, challenge to seal in the cookie).

    `user_handle` is an opaque per-account id the authenticator stores and
    hands back at sign-in; see `user_handle_for`. `existing` are the account's
    credential ids, so the same device is not registered twice.
    """
    challenge = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=rp_id_for(base_url), rp_name=tool_name,
        user_id=user_handle, user_name=user_name, user_display_name=user_name,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=c) for c in existing],
    )
    return options_to_json(options), challenge


def verify_registration(*, credential_json: str, challenge: bytes,
                        base_url: str) -> NewPasskey:
    try:
        v = verify_registration_response(
            credential=credential_json, expected_challenge=challenge,
            expected_rp_id=rp_id_for(base_url), expected_origin=origins_for(base_url),
            require_user_verification=True)
    except (InvalidRegistrationResponse, ValueError, KeyError, TypeError) as e:
        raise PasskeyError("That passkey could not be added. Please try again.") from e
    return NewPasskey(v.credential_id, v.credential_public_key, v.sign_count)


# ── signing in with a passkey (from the login page, nobody signed in) ────────

def authentication_options(*, base_url: str) -> tuple[str, bytes]:
    """(options JSON, challenge). No allowCredentials: the browser offers every
    passkey it holds for this site, so the login page needs no address first."""
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=rp_id_for(base_url), challenge=challenge,
        user_verification=UserVerificationRequirement.REQUIRED)
    return options_to_json(options), challenge


def credential_id_of(credential_json: str) -> bytes:
    """The credential id a sign-in assertion claims, to look its row up by."""
    try:
        data = json.loads(credential_json)
        return base64url_to_bytes(data["rawId"])
    except Exception as e:
        raise PasskeyError("That passkey could not be read. Please try again.") from e


def verify_authentication(*, credential_json: str, challenge: bytes, base_url: str,
                          public_key: bytes, sign_count: int) -> int:
    """Check a sign-in assertion against the stored key. Returns the new
    signature counter to store. Raises PasskeyError when it must be refused.

    A counter that fails to move forward means the credential may have been
    cloned; py_webauthn refuses it. Authenticators that keep no counter (most
    synced passkeys) report 0 every time, which is allowed."""
    try:
        v = verify_authentication_response(
            credential=credential_json, expected_challenge=challenge,
            expected_rp_id=rp_id_for(base_url), expected_origin=origins_for(base_url),
            credential_public_key=public_key, credential_current_sign_count=sign_count,
            require_user_verification=True)
    except (InvalidAuthenticationResponse, ValueError, KeyError, TypeError) as e:
        raise PasskeyError("That passkey was not accepted.") from e
    return v.new_sign_count


def user_handle_for(secret_key, account_id: int) -> bytes:
    """A stable, opaque per-account handle for the authenticator to store.

    The spec asks for one that reveals nothing (no e-mail, no row number in
    clear), so it is an HMAC of the account id under the tool's own key."""
    import hashlib
    import hmac
    key = secret_key.encode() if isinstance(secret_key, str) else secret_key
    return hmac.new(key, f"passkey-user:{account_id}".encode(), hashlib.sha256).digest()


def clean_name(name: str | None, fallback: str) -> str:
    """The label a user gave a passkey, trimmed to something a list can show."""
    name = " ".join((name or "").split())[:NAME_MAX]
    return name or fallback
