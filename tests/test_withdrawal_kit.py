"""withdrawal_kit: one flow for a participant's self-service deletion (6 October 2026)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytest.importorskip("fastapi", reason="requires the live server environment (fastapi)")
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from phronon_common import participant, rate_limit, routing, withdrawal_kit  # noqa: E402


class _Tool:
    """An in-memory tool: rows keyed by token hash."""

    def __init__(self, recovery=True, mail_ok=True):
        self.raw, digest = participant.new_token()
        self.rows = {digest: {"id": 1, "kind": "submission", "title": "Ethics",
                              "code": "AB12", "email": "p@example.org"}}
        self.mail, self.mail_ok, self.deletes, self.cleared = [], mail_ok, [], []
        self.recovery = recovery

    def kit(self):
        def lookup(h):
            return self.rows.get(h)

        def delete(row):
            self.deletes.append(row["id"])
            gone = [h for h, r in self.rows.items() if r["id"] == row["id"]]
            for h in gone:
                del self.rows[h]
            return len(gone)

        def render(request, template, ctx, lang, status):
            return HTMLResponse(json.dumps({"template": template, **ctx}, default=str), status_code=status)

        def forget(request, response, row):
            self.cleared.append(row["id"])

        recovery = {}
        if self.recovery:
            def link_rows(code, email):
                return [r for r in self.rows.values() if r["code"] == code and r["email"] == email]

            def store_token(row, digest):
                for h in [h for h, r in self.rows.items() if r["id"] == row["id"]]:
                    del self.rows[h]
                self.rows[digest] = row

            def send_link(row, to, url, lang):
                self.mail.append((to, url, lang))
                return self.mail_ok

            recovery = dict(link_rows=link_rows, store_token=store_token, send_link=send_link,
                            link_url=lambda raw, lang: f"https://tool.example/withdraw?token={raw}")
        return withdrawal_kit.WithdrawalKit(
            lookup=lookup, kind=lambda row: row["kind"], delete=delete, forget_browser=forget,
            describe=lambda row: {"session_title": row["title"]}, render=render,
            client_ip=lambda request: "203.0.113.9", **recovery)


def _client(tool):
    app = FastAPI()
    router = withdrawal_kit.build_withdrawal_router(tool.kit())
    routing.add_language_twins(router, ("en", "de"), [r.path for r in router.routes],
                               keep_prefix={"/withdraw"})
    app.include_router(routing.answer_head(router))
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_window():
    rate_limit._shared_window._hits.clear()
    yield
    rate_limit._shared_window._hits.clear()


def _page(r):
    return json.loads(r.text)


def test_the_page_never_writes_and_says_what_would_go():
    tool = _Tool()
    c = _client(tool)
    assert _page(c.get("/withdraw"))["state"] == "ask"
    assert _page(c.get("/withdraw?token=short"))["state"] == "not_found"
    page = _page(c.get(f"/withdraw?token={tool.raw}"))
    assert page["state"] == "confirm" and page["kind"] == "submission" and page["session_title"] == "Ethics"
    assert c.head(f"/withdraw?token={tool.raw}").status_code == 200
    assert tool.deletes == []


def test_a_wrong_word_deletes_nothing_and_the_right_one_deletes_once():
    tool = _Tool()
    c = _client(tool)
    page = _page(c.post("/withdraw", data={"token": tool.raw, "confirm": "yes"}))
    assert page["state"] == "confirm" and page["error"] == "confirm" and tool.deletes == []
    for word in ("delete", "Löschen", "WIDERRUF", "supprimer"):
        assert participant.confirm_word_ok(word), word
    page = _page(c.post("/withdraw", data={"token": tool.raw, "confirm": "delete"}))
    assert page["template"] == "withdraw_done.html" and page["removed"] is True
    assert tool.cleared == [1]
    again = _page(c.post("/withdraw", data={"token": tool.raw, "confirm": "DELETE"}))
    assert again["state"] == "not_found", "a deleted row is gone for its link too"


def test_the_language_reaches_the_page_and_its_links():
    tool = _Tool()
    c = _client(tool)
    page = _page(c.get(f"/de/withdraw?token={tool.raw}"))
    assert page["lang"] == "de" and page["state"] == "confirm"
    assert c.get(f"/en/withdraw?token={tool.raw}", follow_redirects=False).status_code == 200


def test_ten_tries_in_five_minutes_then_the_429_page():
    tool = _Tool()
    c = _client(tool)
    codes = [c.post("/withdraw", data={"token": "x" * 30, "confirm": "no"}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429
    assert _page(c.get(f"/withdraw?token={tool.raw}"))["state"] == "rate_limited", "GETs with a token count too"


def test_the_link_answer_is_the_same_whether_the_address_matches_or_not():
    tool = _Tool()
    c = _client(tool)
    hit = c.post("/withdrawal-link", data={"code": "ab12", "email": "P@example.org"})
    miss = c.post("/withdrawal-link", data={"code": "ZZ99", "email": "nobody@example.org"})
    assert hit.status_code == miss.status_code == 200 and hit.text == miss.text
    assert len(tool.mail) == 1, "the matching row got its mail, after the answer"
    to, url, lang = tool.mail[0]
    new_raw = url.split("token=")[1]
    assert _page(c.get(f"/withdraw?token={new_raw}"))["state"] == "confirm"
    assert _page(c.get(f"/withdraw?token={tool.raw}"))["state"] == "not_found", "rotation kills the old link"


def test_a_failed_mail_keeps_the_old_link_working():
    tool = _Tool(mail_ok=False)
    c = _client(tool)
    c.post("/withdrawal-link", data={"code": "AB12", "email": "p@example.org"})
    assert len(tool.mail) == 1
    assert _page(c.get(f"/withdraw?token={tool.raw}"))["state"] == "confirm"


def test_bad_fields_reshow_the_form_and_five_requests_per_fifteen_minutes():
    tool = _Tool()
    c = _client(tool)
    page = _page(c.post("/withdrawal-link", data={"code": "AB12", "email": "not-an-address"}))
    assert page["template"] == "withdrawal_link.html" and page["error"] == "fields"
    assert page["prefill_code"] == "AB12"
    codes = [c.post("/withdrawal-link", data={"code": "AB12", "email": "x@example.org"}).status_code
             for _ in range(5)]
    assert codes[-1] == 429 and tool.mail == []


def test_a_tool_without_addresses_serves_no_link_route():
    c = _client(_Tool(recovery=False))
    assert c.get("/withdrawal-link").status_code in (404, 405)
    assert _page(c.get("/withdraw"))["withdrawal_link_url"] is None


def test_recovery_needs_all_four_parts():
    tool = _Tool()
    with pytest.raises(ValueError, match="go together"):
        withdrawal_kit.WithdrawalKit(lookup=lambda h: None, kind=lambda r: "", delete=lambda r: 0,
                                     render=lambda *a: None, link_rows=lambda c, e: [])
    assert tool
