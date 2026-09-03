"""The fleet participant mechanism (3 September 2026): ids, tokens, cookie, resume links."""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from phronon_common import participant as p


def test_the_numbers_are_the_owners():
    assert p.PARTICIPANT_COOKIE_MAX_AGE == 8 * 3600
    assert p.RESUME_LINK_MINUTES == 30
    assert p.WITHDRAW_RATE_LIMIT == (10, 300)
    assert p.PARTICIPANT_ID_BYTES == 16 and p.TOKEN_BYTES == 32


def test_ids_and_tokens_are_random_and_hashed():
    a, b = p.new_participant_id(), p.new_participant_id()
    assert a != b and len(a) >= 20
    raw, digest = p.new_token()
    assert p.plausible_token(raw)
    assert digest == p.hash_token(raw) and len(digest) == 64
    assert raw not in digest


@pytest.mark.parametrize("bad", [None, "", "short", "x" * 129, "has space here and more", "semi;colon;tokens;xx"])
def test_implausible_tokens_are_refused_before_the_database(bad):
    assert not p.plausible_token(bad)


def test_confirmation_word_accepts_locales_and_refuses_the_rest():
    assert p.confirm_word_ok(" delete ")
    assert p.confirm_word_ok("löschen")
    assert p.confirm_word_ok("supprimer", extra_words=("SUPPRIMER",))
    assert not p.confirm_word_ok("yes")
    assert not p.confirm_word_ok("")
    assert not p.confirm_word_ok(None)


class _Resp:
    def __init__(self):
        self.cookies = {}
        self.deleted = []

    def set_cookie(self, key, value, **kw):
        self.cookies[key] = (value, kw)

    def delete_cookie(self, key, path="/"):
        self.deleted.append(key)


def test_the_cookie_is_signed_httponly_lax_timed_and_secure_in_production():
    c = p.ParticipantCookie("s" * 64, "tool_p", secure=True)
    resp = _Resp()
    c.set(resp, "pid-123")
    value, kw = resp.cookies["tool_p"]
    assert "pid-123" not in value or "." in value, "the id must be signed, not bare"
    assert kw == {"max_age": 8 * 3600, "httponly": True, "samesite": "lax", "secure": True, "path": "/"}
    req = SimpleNamespace(cookies={"tool_p": value})
    assert c.read(req) == "pid-123"
    assert c.read(SimpleNamespace(cookies={"tool_p": value + "x"})) is None
    assert c.read(SimpleNamespace(cookies={})) is None
    c.clear(resp)
    assert resp.deleted == ["tool_p"]


def test_mint_is_the_value_set_puts_on_the_response():
    """The tests of eight tools mint cookies; they must mint the real thing."""
    c = p.ParticipantCookie("s" * 64, "tool_p", secure=False)
    resp = _Resp()
    c.set(resp, "pid-9")
    assert c.read(SimpleNamespace(cookies={"tool_p": c.mint("pid-9")})) == "pid-9"
    # Same signer, so a minted value is accepted exactly like a set one.
    assert c.read(SimpleNamespace(cookies={"tool_p": resp.cookies["tool_p"][0]})) == "pid-9"


def test_a_cookie_signed_by_another_tool_is_refused():
    a = p.ParticipantCookie("a" * 64, "p", secure=False)
    b = p.ParticipantCookie("b" * 64, "p", secure=False)
    resp = _Resp(); a.set(resp, "pid")
    assert b.read(SimpleNamespace(cookies={"p": resp.cookies["p"][0]})) is None


class _Db:
    """A minimal fake of the two callables the resume helpers take."""

    def __init__(self, recent=0):
        self.recent = recent
        self.rows = []
        self.statements = []

    def query_one(self, sql, params):
        self.statements.append(sql)
        if "COUNT(*)" in sql:
            return {"n": self.recent}
        if "token_hash = %s" in sql:
            for r in self.rows:
                if r["token_hash"] == params[0] and not r["used"] and r["expires_at"] > datetime.now():
                    return {"id": r["id"], "participant_ref": r["participant_ref"]}
            return None
        return None

    def execute(self, sql, params):
        self.statements.append(sql)
        if sql.startswith("INSERT"):
            self.rows.append({"id": len(self.rows) + 1, "participant_ref": params[0],
                              "token_hash": params[1], "used": 0,
                              "expires_at": datetime.now() + timedelta(minutes=30)})
            return 1
        if "SET used = 1 WHERE participant_ref" in sql:
            n = 0
            for r in self.rows:
                if r["participant_ref"] == params[0] and not r["used"]:
                    r["used"] = 1; n += 1
            return n
        if "SET used = 1 WHERE id" in sql:
            for r in self.rows:
                if r["id"] == params[0] and not r["used"]:
                    r["used"] = 1
                    return 1
            return 0
        if sql.startswith("DELETE"):
            before = len(self.rows)
            self.rows = [r for r in self.rows if r["participant_ref"] != params[0]]
            return before - len(self.rows)
        return 0


def test_resume_link_is_one_live_link_one_use_and_throttled():
    db = _Db()
    first = p.issue_resume_token(db.execute, db.query_one, "pid")
    second = p.issue_resume_token(db.execute, db.query_one, "pid")
    assert first and second and first != second
    assert p.peek_resume_token(db.query_one, first) is None, "issuing a new link must kill the old one"
    row = p.peek_resume_token(db.query_one, second)
    assert row and row["participant_ref"] == "pid"
    assert p.peek_resume_token(db.query_one, second) is not None, "peek must not spend"
    assert p.spend_resume_token(db.execute, row["id"])
    assert not p.spend_resume_token(db.execute, row["id"]), "a token spends once"
    assert p.peek_resume_token(db.query_one, second) is None
    throttled = _Db(recent=p.RESUME_LINKS_PER_WINDOW)
    assert p.issue_resume_token(throttled.execute, throttled.query_one, "pid") is None
    assert not any(s.startswith("INSERT") for s in throttled.statements)


def test_the_table_ddl_has_the_hash_unique_and_never_a_raw_token():
    ddl = p.RESUME_TOKENS_DDL
    assert "token_hash" in ddl and "UNIQUE KEY" in ddl and "raw" not in ddl.lower()
    assert "participant_ref" in ddl and "email" not in ddl.lower()


def test_the_shared_mails_render_the_link_and_the_rotation_sentence():
    from phronon_common import emails
    text, html = emails.withdrawal_link_bodies("Tool", "https://t.example/withdraw?token=abc", "2026-10-03")
    assert "https://t.example/withdraw?token=abc" in text and "token=abc" in html
    assert "replaces any earlier deletion link" in text
    assert "2026-10-03" in text
    text, html = emails.participant_resume_bodies("Tool", "https://t.example/resume?token=abc", 30)
    assert "once" in text and "30 minutes" in text and "token=abc" in html
