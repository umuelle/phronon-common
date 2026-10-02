"""Passkey ceremonies (FL-065, 2 October 2026), end to end against py_webauthn.

The software authenticator signs with a real P-256 key, so these run the real
verification; only the fingerprint is simulated.
"""
import json

import pytest

from phronon_common import passkeys as pk
from phronon_common.testing.soft_authenticator import SoftAuthenticator

BASE = "https://whiteout-exercise.org"
SECRET = "test-secret-0000000000000000000000000000"


def _register(auth, base=BASE, user_verified=True, existing=()):
    options, challenge = pk.registration_options(
        base_url=base, tool_name="Whiteout Exercise",
        user_handle=pk.user_handle_for(SECRET, 7), user_name="a@example.org",
        existing=list(existing))
    return options, challenge, auth.create(options, user_verified=user_verified)


def test_register_then_sign_in():
    auth = SoftAuthenticator(origin=BASE)
    _opts, challenge, cred = _register(auth)
    new = pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)
    options, challenge = pk.authentication_options(base_url=BASE)
    assertion = auth.get(options)
    assert pk.credential_id_of(assertion) == new.credential_id
    count = pk.verify_authentication(credential_json=assertion, challenge=challenge,
                                     base_url=BASE, public_key=new.public_key,
                                     sign_count=new.sign_count)
    assert count == 1


def test_the_options_demand_a_discoverable_verified_passkey():
    opts = json.loads(_register(SoftAuthenticator(origin=BASE))[0])
    sel = opts["authenticatorSelection"]
    assert sel["residentKey"] == "required" and sel["userVerification"] == "required"
    assert opts["rp"]["id"] == "whiteout-exercise.org"
    login = json.loads(pk.authentication_options(base_url=BASE)[0])
    assert login["userVerification"] == "required"
    assert login.get("allowCredentials", []) == []


def test_a_passkey_without_user_verification_is_refused_at_both_steps():
    """Touch alone is one factor; a passkey replaces password AND code."""
    auth = SoftAuthenticator(origin=BASE)
    _o, challenge, cred = _register(auth, user_verified=False)
    with pytest.raises(pk.PasskeyError):
        pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)

    auth = SoftAuthenticator(origin=BASE)
    _o, challenge, cred = _register(auth)
    new = pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)
    options, challenge = pk.authentication_options(base_url=BASE)
    with pytest.raises(pk.PasskeyError):
        pk.verify_authentication(credential_json=auth.get(options, user_verified=False),
                                 challenge=challenge, base_url=BASE,
                                 public_key=new.public_key, sign_count=0)


def test_a_bad_signature_a_wrong_challenge_and_a_wrong_site_are_refused():
    auth = SoftAuthenticator(origin=BASE)
    _o, challenge, cred = _register(auth)
    new = pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)
    options, challenge = pk.authentication_options(base_url=BASE)
    kw = dict(base_url=BASE, public_key=new.public_key, sign_count=0)
    with pytest.raises(pk.PasskeyError):
        pk.verify_authentication(credential_json=auth.get(options, tamper=True),
                                 challenge=challenge, **kw)
    with pytest.raises(pk.PasskeyError):
        pk.verify_authentication(credential_json=auth.get(options),
                                 challenge=b"x" * 32, **kw)
    # A page on another tool's domain asking this tool to accept its assertion.
    other = SoftAuthenticator(origin="https://evil.example")
    other.credentials = auth.credentials
    with pytest.raises(pk.PasskeyError):
        pk.verify_authentication(credential_json=other.get(options), challenge=challenge, **kw)


def test_a_counter_that_goes_backwards_is_refused():
    """A cloned authenticator shows up as a counter that does not move forward."""
    auth = SoftAuthenticator(origin=BASE)
    _o, challenge, cred = _register(auth)
    new = pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)
    options, challenge = pk.authentication_options(base_url=BASE)
    with pytest.raises(pk.PasskeyError):
        pk.verify_authentication(credential_json=auth.get(options), challenge=challenge,
                                 base_url=BASE, public_key=new.public_key, sign_count=50)


def test_synced_passkeys_that_keep_no_counter_still_sign_in():
    auth = SoftAuthenticator(origin=BASE, counts_signatures=False)
    _o, challenge, cred = _register(auth)
    new = pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)
    for _ in range(2):
        options, challenge = pk.authentication_options(base_url=BASE)
        assert pk.verify_authentication(credential_json=auth.get(options), challenge=challenge,
                                        base_url=BASE, public_key=new.public_key,
                                        sign_count=0) == 0


def test_the_challenge_cookie_is_bound_to_its_purpose_and_expires(monkeypatch):
    sealed = pk.seal_challenge(SECRET, b"c" * 32, "register:7")
    assert pk.open_challenge(SECRET, sealed, "register:7") == b"c" * 32
    assert pk.open_challenge(SECRET, sealed, "register:8") is None
    assert pk.open_challenge(SECRET, sealed, "login") is None
    assert pk.open_challenge("another-key-000000000000000000000000000", sealed, "register:7") is None
    assert pk.open_challenge(SECRET, None, "login") is None
    import time
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + pk.CHALLENGE_SECONDS + 5)
    assert pk.open_challenge(SECRET, sealed, "register:7") is None


def test_the_user_handle_is_opaque_and_stable():
    h = pk.user_handle_for(SECRET, 7)
    assert h == pk.user_handle_for(SECRET, 7) != pk.user_handle_for(SECRET, 8)
    assert b"7" not in h and len(h) == 32


def test_names_are_trimmed_and_never_empty():
    assert pk.clean_name("  My   MacBook  ", "x") == "My MacBook"
    assert pk.clean_name("", "Passkey") == "Passkey"
    assert len(pk.clean_name("a" * 500, "x")) == pk.NAME_MAX


def test_rp_id_and_origins():
    assert pk.rp_id_for("https://moral-mirror.org/") == "moral-mirror.org"
    assert pk.rp_id_for("https://www.drawbridge-drama.org") == "drawbridge-drama.org"
    assert pk.origins_for("https://drawbridge-drama.org") == [
        "https://drawbridge-drama.org", "https://www.drawbridge-drama.org"]
    assert pk.origins_for("https://testserver") == ["https://testserver"]
    assert pk.origins_for("http://localhost:8000/x") == ["http://localhost:8000"]


def test_one_passkey_works_on_the_bare_and_the_www_address():
    """Every site answers on both; a passkey made on one must sign in on the other."""
    bare = SoftAuthenticator(origin="https://drawbridge-drama.org")
    options, challenge = pk.registration_options(
        base_url="https://www.drawbridge-drama.org", tool_name="Drawbridge Drama",
        user_handle=pk.user_handle_for(SECRET, 1), user_name="a@example.org")
    new = pk.verify_registration(credential_json=bare.create(options), challenge=challenge,
                                 base_url="https://www.drawbridge-drama.org")
    www = SoftAuthenticator(origin="https://www.drawbridge-drama.org")
    www.credentials = bare.credentials
    options, challenge = pk.authentication_options(base_url="https://drawbridge-drama.org")
    assert pk.verify_authentication(credential_json=www.get(options), challenge=challenge,
                                    base_url="https://drawbridge-drama.org",
                                    public_key=new.public_key, sign_count=0) == 1
