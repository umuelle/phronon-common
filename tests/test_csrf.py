"""CSRF middleware: exemptions, session binding, and the catch-all guard.

Background (2026-07-28): Polarity Profiler and ControversyGenerator both shipped a
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


# ── Binding to the stable part of a rolling cookie (1.93.0, TO DO FL-090 (b)) ──
#
# Controversy Generator's session cookie is "<account>:<expiry>:<epoch>-<sig>"
# and its expiry is rewritten on every response, so binding to the raw value
# never matched and the tool ran unbound. session_id_of lets it bind to the
# part that stays: the account and its epoch.

def _account_of(request):
    raw = request.cookies.get("backoffice")
    if not raw:
        return None
    account, _expiry, epoch = raw.split(":")
    return f"{account}:{epoch}"


def test_session_id_of_survives_the_cookie_rolling():
    client, protection = _build(session_cookie=None, session_id_of=_account_of)
    client.cookies.set("backoffice", "7:1000:0")
    token = protection.generate_token("7:0")
    client.cookies.set("backoffice", "7:2000:0")       # the next response rolled it
    assert client.post("/backoffice", data={"csrf_token": token}).status_code == 200


def test_session_id_of_refuses_a_token_minted_for_another_account_or_epoch():
    client, protection = _build(session_cookie=None, session_id_of=_account_of)
    client.cookies.set("backoffice", "7:1000:0")
    for other in ("8:0", "7:1", None):
        token = protection.generate_token(other)
        assert client.post("/backoffice", data={"csrf_token": token}).status_code == 403, other


def test_session_id_of_leaves_a_visitor_unbound():
    client, protection = _build(session_cookie=None, session_id_of=_account_of)
    assert client.post("/backoffice", data={"csrf_token": protection.generate_token(None)}).status_code == 200


def test_get_csrf_token_with_session_id_of_matches_the_middleware():
    from starlette.requests import Request

    protection = CSRFProtection(secret_key=SECRET)
    request = Request({"type": "http", "method": "GET", "path": "/",
                       "headers": [(b"cookie", b"backoffice=7:1000:3")]})
    token = get_csrf_token(request, protection, session_id_of=_account_of)
    assert protection.validate_token(token, "7:3")
    assert not protection.validate_token(token, None)


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


def test_the_handler_still_receives_the_form_body():
    """The middleware must put the body back after reading the token out of it.

    Regression (2026-07-28, found in production): BaseHTTPMiddleware hands the
    route handler the same receive stream the middleware reads from, so calling
    request.form() here consumed the body and the handler saw nothing — every
    backoffice login answered 422 "Field required" instead of logging in.

    The stand-in route in the other tests takes no arguments, so it could not
    catch this. This one reads the fields the way a real handler does.
    """
    from fastapi import Form

    app = FastAPI()
    protection = CSRFProtection(secret_key=SECRET)
    app.add_middleware(CSRFMiddleware, csrf_protection=protection, session_cookie=None)

    @app.post("/backoffice")
    async def login(email: str = Form(...), password: str = Form(...)):
        return {"email": email, "password_len": len(password)}

    client = TestClient(app)
    r = client.post("/backoffice", data={
        "email": "educator@example.org",
        "password": "hunter2hunter2",
        "csrf_token": protection.generate_token(None),
    })
    assert r.status_code == 200, f"handler did not receive the form: {r.text[:300]}"
    assert r.json() == {"email": "educator@example.org", "password_len": 14}


def test_the_handler_still_receives_a_json_body():
    """Same re-injection, non-form content type: the token comes from the header."""
    app = FastAPI()
    protection = CSRFProtection(secret_key=SECRET)
    app.add_middleware(CSRFMiddleware, csrf_protection=protection, session_cookie=None)

    @app.post("/backoffice/api")
    async def api(payload: dict):
        return {"got": payload}

    client = TestClient(app)
    r = client.post(
        "/backoffice/api",
        json={"ids": [1, 2, 3]},
        headers={"X-CSRF-Token": protection.generate_token(None)},
    )
    assert r.status_code == 200, f"handler did not receive the JSON body: {r.text[:300]}"
    assert r.json() == {"got": {"ids": [1, 2, 3]}}


def test_safe_methods_are_never_checked():
    app = FastAPI()
    protection = CSRFProtection(secret_key=SECRET)
    app.add_middleware(CSRFMiddleware, csrf_protection=protection)

    @app.get("/backoffice")
    async def page():  # pragma: no cover - trivial
        return {"ok": True}

    assert TestClient(app).get("/backoffice").status_code == 200


# ── What a person sees when a form is refused (1.112.0) ──────────────────────
# Owner, 20 November 2026: a form sent after the three-hour sign-in had ended
# showed "403 Forbidden. CSRF validation failed", which read as a breakdown.

def _explaining(**kwargs):
    return _build(explain_refusals=True, session_cookie="sess", **kwargs)


def test_without_the_switch_the_answer_is_the_bare_403_of_before():
    client, _ = _build(session_cookie="sess")
    r = client.post("/backoffice/users/1/send-link", data={"csrf_token": "old"})
    assert r.status_code == 403 and "CSRF validation failed" in r.text


def test_a_backoffice_form_after_the_sign_in_ended_goes_to_the_sign_in_page():
    client, _ = _explaining()
    r = client.post("/backoffice/users/1/send-link", data={"csrf_token": "old"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/backoffice/login?msg=signed_out"


@pytest.mark.parametrize("path", ["/backoffice/login", "/backoffice/login/passkey",
                                  "/backoffice/verify", "/backoffice/password-reset"])
def test_a_stale_sign_in_form_goes_back_to_the_sign_in_page(path):
    """Whoever sends it, signed in or not: the sign-in page sends a signed-in
    person on to the dashboard."""
    client, _ = _explaining()
    client.cookies.set("sess", "someone")
    r = client.post(path, data={"csrf_token": "old"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/backoffice/login?msg=form_expired"


def test_a_signed_in_form_left_open_too_long_says_nothing_was_changed():
    client, _ = _explaining()
    client.cookies.set("sess", "someone")
    r = client.post("/backoffice/sessions/7/close", data={"csrf_token": "old"},
                    headers={"Referer": "https://testserver/backoffice/sessions/7?tab=game"})
    assert r.status_code == 403
    assert "<h1>This page has expired</h1>" in r.text and "Nothing was changed." in r.text
    assert 'href="/backoffice/sessions/7?tab=game"' in r.text
    assert "CSRF" not in r.text and '<html lang="en">' in r.text and 'class="ph-footer"' in r.text


@pytest.mark.parametrize("referer, back", [
    ("https://elsewhere.example/phish", "/backoffice/dashboard"),
    ("//elsewhere.example/x", "/backoffice/dashboard"),
    ("javascript:alert(1)", "/backoffice/dashboard"),
    ("", "/backoffice/dashboard"),
    ('https://testserver/backoffice/x?a="><script>', '/backoffice/x?a=&quot;&gt;&lt;script&gt;'),
])
def test_the_link_back_never_leaves_this_site_and_is_escaped(referer, back):
    client, _ = _explaining()
    client.cookies.set("sess", "someone")
    r = client.post("/backoffice/sessions/7/close", data={"csrf_token": "old"}, headers={"Referer": referer})
    assert f'<a href="{back}">' in r.text


def test_a_participant_form_gets_the_page_with_a_link_to_its_own_page():
    client, _ = _explaining()
    r = client.post("/join", data={"csrf_token": "old"}, headers={"Referer": "https://testserver/join?code=AB12"})
    assert r.status_code == 403 and 'href="/join?code=AB12"' in r.text
    r = client.post("/join", data={"csrf_token": "old"})
    assert 'href="/"' in r.text


def test_a_script_still_gets_json_and_learns_whether_it_is_signed_out():
    client, _ = _explaining()
    r = client.post("/backoffice/x", headers={"Accept": "application/json"})
    assert r.status_code == 403 and r.json()["success"] is False and r.json()["signed_out"] is True
    client.cookies.set("sess", "someone")
    assert client.post("/backoffice/x", headers={"Accept": "application/json"}).json()["signed_out"] is False


def test_a_valid_token_still_goes_through_with_the_switch_on():
    client, protection = _explaining()
    client.cookies.set("sess", "someone")
    r = client.post("/backoffice/x", data={"csrf_token": protection.generate_token("someone")})
    assert r.status_code == 200 and r.json() == {"reached": True}


def test_a_tool_that_checks_tokens_itself_answers_the_same_way():
    """FormExpired, raised where a tool's own check refuses, through the
    shared handler; a session that cannot be read counts as signed out."""
    from phronon_common.csrf import FormExpired, install_refusal_handler
    for signed_in, where in ((lambda r: False, "/backoffice/login?msg=signed_out"),
                             (lambda r: 1 / 0, "/backoffice/login?msg=signed_out")):
        app = FastAPI()
        install_refusal_handler(app, signed_in)

        @app.post("/backoffice/users/1/deactivate")
        def refused():
            raise FormExpired()
        r = TestClient(app, follow_redirects=False).post("/backoffice/users/1/deactivate")
        assert r.status_code == 303 and r.headers["location"] == where
    app = FastAPI()
    install_refusal_handler(app, lambda r: True)

    @app.post("/backoffice/users/1/deactivate")
    def refused_signed_in():
        raise FormExpired()
    r = TestClient(app).post("/backoffice/users/1/deactivate")
    assert r.status_code == 403 and "Nothing was changed." in r.text
