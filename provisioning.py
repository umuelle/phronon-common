"""Shared helpers for the hub → tool account-provisioning API (harmonization I1).

Every tool exposes ONE identical endpoint:

    POST /api/internal/provision-account
    Header:  X-Provision-Secret: <shared secret>   (same value in the hub and the tool)
    Body (JSON):
        {
          "email":       "educator@uni.edu",   # required
          "name":        "Dr. Jane Doe",         # optional display name
          "sector":      "academic",             # optional: "academic" | "corporate"
          "external_id": "hub-user-123",         # optional: hub user id (linking / audit)
          "send_invite": true                     # optional: email a set-password link (default true)
        }
    Response (JSON):
        200  {"status": "ok", "created": true|false, "account_id": 42}
        401  {"status": "error", "detail": "unauthorized"}
        400  {"status": "error", "detail": "..."}      # bad / missing fields
        500  {"status": "error", "detail": "..."}

Contract rules:
  * IDEMPOTENT — look up by email; create if absent, otherwise ensure the account
    is active/entitled and update name/sector. Never duplicate.
  * Each tool supplies a tiny ADAPTER mapping this contract onto its own account
    table (admins / users / educators — see N5). The external contract is identical
    everywhere and hides those table differences.
  * No plaintext password is ever set or returned. When send_invite is true the tool
    issues a one-time password-reset token and emails the branded "set your password"
    link (the same flow as a normal reset), so the educator chooses their own password.

Security: the secret is the in-app guard (constant-time compare below). Deployment
should ALSO restrict /api/internal/ to localhost in nginx as defence-in-depth, since
hub→tool calls are same-host.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

PROVISION_HEADER = "X-Provision-Secret"


def verify_secret(provided: str | None, expected: str | None) -> bool:
    """Constant-time comparison of the shared provisioning secret."""
    if not provided or not expected:
        return False
    return hmac.compare_digest(str(provided), str(expected))


@dataclass
class ProvisionRequest:
    email: str
    name: str = ""
    sector: str = "academic"
    external_id: str = ""
    send_invite: bool = True


def parse_request(payload: dict) -> ProvisionRequest:
    """Validate + normalise an incoming provisioning payload.

    Raises ValueError (with a human-readable message) if the payload is invalid.
    """
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    email = str(payload.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("a valid 'email' is required")
    sector = str(payload.get("sector") or "academic").strip().lower()
    if sector not in ("academic", "corporate"):
        raise ValueError("'sector' must be 'academic' or 'corporate'")
    return ProvisionRequest(
        email=email,
        name=str(payload.get("name") or "").strip(),
        sector=sector,
        external_id=str(payload.get("external_id") or "").strip(),
        send_invite=bool(payload.get("send_invite", True)),
    )


def secret_env_var(tool) -> str:
    """The environment variable holding THIS tool's provisioning secret.

    Derived from the registry's entitlement key, which is what the hub already
    uses to look the secret up (`Phronon/fleet_client.py`). Seven tools spelled
    the name out by hand — `PROVISION_SECRET_DRAWBRIDGE_DRAMA` and so on — and a
    name typed twice is a name that can be typed differently once.
    """
    return f"PROVISION_SECRET_{tool.entitlement_key.upper()}"


def require_internal_secret(request, tool):
    """`None` if the caller presented this tool's secret; a 401 response if not.

        denied = require_internal_secret(request, TOOL)
        if denied:
            return denied

    THIS tool's own secret, and only its own (G4 / FL-028, completed 20 August
    2026). The shared PROVISION_SECRET fallback is gone: while it existed, one
    credential opened all nine over the server's internal network, and a
    fallback that works is a fallback nobody removes. An empty value fails
    closed — every request 401s until the .env has it.

    The response import is lazy so this module keeps working without the `web`
    extra; the seven copies of this guard imported it inside the route for the
    same reason.
    """
    from fastapi.responses import JSONResponse

    expected = os.getenv(secret_env_var(tool), "")
    provided = request.headers.get(PROVISION_HEADER, "")
    if expected and verify_secret(provided, expected):
        return None
    return JSONResponse({"status": "error", "detail": "unauthorized"}, status_code=401)
