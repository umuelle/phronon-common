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


# ── replay (review of 3 October 2026) ────────────────────────────────────────
# Deleting the challenge cookie after a sign-in does not stop someone holding a
# copy of the cookie and the signed answer from sending both again. py_webauthn
# cannot catch it for synced passkeys, whose counter stays 0:

def test_verification_alone_accepts_the_same_answer_twice():
    """Why record_sign_in exists. If this ever starts failing, py_webauthn has
    begun refusing replays itself; record_sign_in is still needed across
    workers, so do not delete it on that evidence alone."""
    auth = SoftAuthenticator(origin=BASE, counts_signatures=False)
    _o, challenge, cred = _register(auth)
    new = pk.verify_registration(credential_json=cred, challenge=challenge, base_url=BASE)
    options, challenge = pk.authentication_options(base_url=BASE)
    cookie = pk.seal_challenge(SECRET, challenge, "login")
    assertion = auth.get(options)
    for _ in range(2):
        sealed = pk.open_sealed_challenge(SECRET, cookie, "login")
        assert pk.verify_authentication(credential_json=assertion, challenge=sealed.value,
                                        base_url=BASE, public_key=new.public_key,
                                        sign_count=0) == 0


def test_the_cookie_says_when_the_challenge_was_issued(monkeypatch):
    import time
    monkeypatch.setattr(time, "time", lambda: 1_790_000_000.7)
    sealed = pk.seal_challenge(SECRET, b"c" * 32, "login")
    got = pk.open_sealed_challenge(SECRET, sealed, "login")
    assert got == pk.SealedChallenge(b"c" * 32, 1_790_000_000)
    assert pk.open_challenge(SECRET, sealed, "login") == b"c" * 32


def test_a_cookie_without_an_issue_time_is_refused():
    """Cookies sealed by the release before this one carry no "t". They live
    five minutes; refusing them costs one retry during a deploy."""
    from webauthn.helpers import bytes_to_base64url
    old = pk._signer(SECRET).dumps({"c": bytes_to_base64url(b"c" * 32), "p": "login"})
    assert pk.open_sealed_challenge(SECRET, old, "login") is None
    assert pk.open_challenge(SECRET, old, "login") is None


def _test_db():
    """A connection factory for the tool's disposable *_test schema, or a skip.
    This package's CI has no MySQL; every tool's suite proves the same rule
    through its real login route (test_a_replayed_sign_in_is_refused)."""
    import os
    name = os.environ.get("DB_NAME", "")
    if not (os.environ.get("DB_HOST") and name.endswith("_test")):
        pytest.skip("requires a disposable test database")
    mysql = pytest.importorskip("mysql.connector")

    def get_db():
        return mysql.connect(host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
                             password=os.environ.get("DB_PASSWORD", ""), database=name)
    return get_db


@pytest.fixture
def passkey_row():
    import secrets
    get_db = _test_db()
    table = f"passkeys_replay_{secrets.token_hex(4)}"

    def run(sql, params=()):
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.with_rows else None
            conn.commit()
            return rows
        finally:
            conn.close()

    run(f"CREATE TABLE {table} (id INT PRIMARY KEY, sign_count BIGINT UNSIGNED NOT NULL "
        f"DEFAULT 0, last_used_at DATETIME DEFAULT NULL)")
    run(f"INSERT INTO {table} (id) VALUES (1)")
    try:
        yield get_db, table, run
    finally:
        run(f"DROP TABLE {table}")


def test_a_challenge_signs_in_once(passkey_row):
    import time
    get_db, table, run = passkey_row
    issued = int(time.time())
    assert pk.record_sign_in(get_db, 1, 0, issued, table=table) is True
    assert pk.record_sign_in(get_db, 1, 0, issued, table=table) is False   # the replay
    # An older challenge (another tab) is refused too; a newer one is fine.
    assert pk.record_sign_in(get_db, 1, 0, issued - 60, table=table) is False
    assert pk.record_sign_in(get_db, 1, 0, int(time.time()) + 1, table=table) is True
    assert run(f"SELECT sign_count FROM {table} WHERE id=1") == [(0,)]


def test_the_first_use_stores_the_counter(passkey_row):
    import time
    get_db, table, run = passkey_row
    assert pk.record_sign_in(get_db, 1, 7, int(time.time()), table=table) is True
    assert run(f"SELECT sign_count, last_used_at IS NOT NULL FROM {table} WHERE id=1") == [(7, 1)]


def test_two_workers_handed_the_same_replay_let_one_in(passkey_row):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    get_db, table, _run = passkey_row
    issued = int(time.time())
    start = threading.Barrier(8)

    def worker(_):
        start.wait()
        return pk.record_sign_in(get_db, 1, 0, issued, table=table)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, range(8)))
    assert results.count(True) == 1


def test_record_sign_in_refuses_a_table_name_that_is_not_an_identifier():
    with pytest.raises(ValueError):
        pk.record_sign_in(lambda: None, 1, 0, 0, table="passkeys; DROP TABLE x")
