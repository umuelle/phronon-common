"""CSRF middleware: exemptions, session binding, and the catch-all guard.

Background (2026-07-28): LSR-profiler and ControversyGenerator both shipped a
bare "/" in the middleware's prefix exempt list. Matching is
`path.startswith(entry)` and every path starts with "/", so every request was
exempt — backoffice login, class management, user administration, the lot. It
survived because nothing fails visibly when CSRF is off.

The constructor now refuses a catch-all prefix, so the whole fleet is protected
from repeating it. `exempt_exact` is the supported way to exempt a site root
that genuinely accepts a POST.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.csrf import (  # noqa: E402
    CSRFMiddleware,
    CSRFProtection,
    get_csrf_token,
)

SECRET = b"phronon-common-unit-test-secret-key"


def _build(**kwargs):
    """A stand-in app: the catch-all route reports whether CSRF let it through."""
    app = FastAPI()
    protection = CSRFProtection(secret_key=SECRET, token_expiry=3600)
    app.state.csrf_protection = protection
    app.add_middleware(CSRFMiddleware, csrf_protection=protection, **kwargs)

    @app.post("/{full_path:path}")
    async def catch_all(full_path: str):  # pragma: no cover - trivial
        return {"reached": True}

    return TestClient(app), protection


# ── The guard ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["/", ""])
def test_catch_all_prefix_is_refused(bad):
    with pytest.raises(ValueError) as excinfo:
        CSRFMiddleware(
            app=None,
            csrf_protection=CSRFProtection(secret_key=SECRET),
            exempt_paths=[bad],
        )
    assert "exempt_exact" in str(excinfo.value), "the error must name the fix"


def test_a_catch_all_prefix_stops_the_app_booting():
    """add_middleware is lazy — Starlette builds the stack on the first ASGI
    call, which for a real server is lifespan startup. So the bad config takes
    the app down at boot rather than silently disabling CSRF in production."""
    app = FastAPI()
    app.add_middleware(
        CSRFMiddleware,
        csrf_protection=CSRFProtection(secret_key=SECRET),
        exempt_paths=["/"],
    )
    with pytest.raises(ValueError):
        with TestClient(app):  # runs startup, which builds the middleware stack
            pass


def test_a_normal_prefix_is_accepted():
    client, _ = _build(exempt_paths=["/join"])
    assert client.post("/join").status_code == 200


# ── Prefix vs exact ──────────────────────────────────────────────────────────

def test_exempt_exact_covers_the_site_root_only():
    """The tools whose participant flow POSTs to "/" need exactly this."""
    client, _ = _build(exempt_exact={"/"})
    assert client.post("/").status_code == 200, "POST / should be exempt"
    assert client.post("/backoffice").status_code == 403, (
        "exempt_exact must not leak to any other path"
    )
    assert client.post("/anything").status_code == 403


def test_prefix_exemption_covers_the_subtree():
    client, _ = _build(exempt_paths=["/withdraw/"])
    assert client.post("/withdraw/token123").status_code == 200
    assert client.post("/withdrawal-elsewhere").status_code == 403


def test_static_is_exempt_by_default():
    client, _ = _build()
    assert client.post("/static/x.css").status_code == 200


# ── Token handling ───────────────────────────────────────────────────────────

def test_protected_path_rejects_a_missing_token():
    client, _ = _build()
    r = client.post("/backoffice/users/1/delete")
    assert r.status_code == 403
    assert "CSRF validation failed" in r.text


def test_protected_path_accepts_a_valid_token_in_the_form():
    client, protection = _build()
    r = client.post("/backoffice", data={"csrf_token": protection.generate_token()})
    assert r.status_code == 200


def test_protected_path_accepts_a_valid_token_in_the_header():
    client, protection = _build()
    r = client.post("/backoffice", headers={"X-CSRF-Token": protection.generate_token()})
    assert r.status_code == 200


def test_a_forged_token_is_rejected():
    client, _ = _build()
    assert client.post("/backoffice", data={"csrf_token": "a:1:bad"}).status_code == 403


def test_an_expired_token_is_rejected():
    """Expiry is enforced by the validating instance, so it is the middleware's
    own CSRFProtection that must carry the short lifetime."""
    app = FastAPI()
    protection = CSRFProtection(secret_key=SECRET, token_expiry=-1)
    app.add_middleware(CSRFMiddleware, csrf_protection=protection)

    @app.post("/backoffice")
    async def page():  # pragma: no cover - trivial
        return {"ok": True}

    client = TestClient(app)
    assert client.post(
        "/backoffice", data={"csrf_token": protection.generate_token()}
    ).status_code == 403


# ── Session binding is opt-out ───────────────────────────────────────────────

def test_unbound_middleware_accepts_an_unbound_token():
    """session_cookie=None: for tools whose cookie value rolls on every response."""
    client, protection = _build(session_cookie=None)
    r = client.post("/backoffice", data={"csrf_token": protection.generate_token(None)})
    assert r.status_code == 200


def test_bound_middleware_rejects_a_token_signed_for_another_session():
    client, protection = _build(session_cookie="backoffice")
    client.cookies.set("backoffice", "session-A")
    r = client.post("/backoffice", data={"csrf_token": protection.generate_token("session-B")})
    assert r.status_code == 403


def test_get_csrf_token_matches_what_the_middleware_expects():
    """The helper and the middleware must agree on binding, or nothing validates."""
    from starlette.requests import Request

    protection = CSRFProtection(secret_key=SECRET)
    scope = {
        "type": "http", "method": "POST", "path": "/", "headers": [(b"cookie", b"backoffice=sess-1")],
    }
    token = get_csrf_token(Request(scope), protection, session_cookie="backoffice")
    assert protection.validate_token(token, "sess-1")
    assert not protection.validate_token(token, "other-session")


# ── Failure mode ─────────────────────────────────────────────────────────────

def test_failure_is_a_403_not_a_500():
    """Raising HTTPException here would bypass the app's handlers and 500.

    User middleware runs outside Starlette's ExceptionMiddleware, so the
    middleware has to return the response itself.
    """
    client, _ = _build()
    assert client.post("/backoffice").status_code == 403


def test_ajax_callers_get_json():
    client, _ = _build()
    r = client.post("/backoffice", headers={"Accept": "application/json"})
    assert r.status_code == 403
    assert r.json()["success"] is False


def test_safe_methods_are_never_checked():
    app = FastAPI()
    protection = CSRFProtection(secret_key=SECRET)
    app.add_middleware(CSRFMiddleware, csrf_protection=protection)

    @app.get("/backoffice")
    async def page():  # pragma: no cover - trivial
        return {"ok": True}

    assert TestClient(app).get("/backoffice").status_code == 200
