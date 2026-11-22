"""messages.py: who sees what, what is stored, what a page draws.

This package's CI has no MySQL: the database below answers the statements
messages.py writes from a list of rows. Each tool proves the SQL against its
real database (Peak Season: tests/test_messages.py compares messages_for with
may_see on every combination).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import jinja2
import pytest

from phronon_common import messages

ROOT = Path(messages.__file__).resolve().parent


class FakeDb:
    def __init__(self, recent=0):
        self.recent = recent
        self.inserted = []

    def query_one(self, sql, params=()):
        if "COUNT(*) AS n FROM messages WHERE session_id = %s AND sender" in sql:
            return {"n": self.recent}
        return None

    def query_all(self, sql, params=()):
        return []

    def insert(self, sql, params=()):
        self.inserted.append(params)
        return len(self.inserted)

    def write(self, sql, params=()):
        return 1


def test_clean_text_keeps_words_and_drops_what_could_hide_or_turn_text():
    assert messages.clean_text("  Hello \t  there  ") == "Hello there"
    assert messages.clean_text("a‮b​c\x07d") == "abcd"
    assert messages.clean_text("one\r\n\r\n\r\n\r\ntwo") == "one\n\ntwo"
    assert messages.clean_text(None) == ""
    assert len(messages.clean_text("x" * 1000)) == messages.TEXT_MAX


ROWS = [
    {"id": 1, "room": 7, "sender": 0, "recipient": None, "hidden_at": None},    # educator to the valley
    {"id": 2, "room": None, "sender": 0, "recipient": None, "hidden_at": None},  # educator to every valley
    {"id": 3, "room": 7, "sender": 11, "recipient": None, "hidden_at": None},   # hotel 11 to its valley
    {"id": 4, "room": 7, "sender": 11, "recipient": 12, "hidden_at": None},     # 11 to 12 only
    {"id": 5, "room": 7, "sender": 13, "recipient": 0, "hidden_at": None},      # 13 to the educator
    {"id": 6, "room": 8, "sender": 21, "recipient": None, "hidden_at": None},   # another valley
    {"id": 7, "room": 7, "sender": 11, "recipient": None, "hidden_at": "x"},    # hidden
    {"id": 8, "room": 7, "sender": 0, "recipient": 13, "hidden_at": None},      # educator to 13 only
]


@pytest.mark.parametrize("party, room, ids", [
    (11, 7, [1, 2, 3, 4]),
    (12, 7, [1, 2, 3, 4]),
    (13, 7, [1, 2, 3, 5, 8]),
    (21, 8, [2, 6]),
    (None, None, [1, 2, 3, 4, 5, 6, 7, 8]),
])
def test_a_party_sees_its_room_what_it_wrote_and_what_was_written_to_it(party, room, ids):
    assert [r["id"] for r in ROWS if messages.may_see(r, party, room)] == ids


def test_a_party_writes_only_inside_its_room_and_not_too_fast():
    db = FakeDb()
    assert messages.send(db, session_id=1, room=7, sender=11, recipient=12, text="hi", recipients=[12, 13]) == 1
    assert messages.send(db, session_id=1, room=7, sender=11, recipient=0, text="hi", recipients=[12]) == 2
    for recipient, room in ((21, 7), (11, 7), (None, None)):
        with pytest.raises(messages.Refused) as refused:
            messages.send(db, session_id=1, room=room, sender=11, recipient=recipient, text="hi", recipients=[12, 13])
        assert refused.value.reason == "recipient"
    with pytest.raises(messages.Refused) as refused:
        messages.send(db, session_id=1, room=7, sender=11, recipient=None, text="  ​ ")
    assert refused.value.reason == "empty"
    with pytest.raises(messages.Refused) as refused:
        messages.send(FakeDb(recent=messages.BURST[0]), session_id=1, room=7, sender=11, recipient=None, text="hi")
    assert refused.value.reason == "too_fast"
    # the educator writes to every room and is not limited
    assert messages.send(FakeDb(recent=99), session_id=1, room=None, sender=0, recipient=None, text="hi") == 1


def test_a_page_gets_names_in_place_of_numbers():
    names = messages.Names(party=lambda n: "Hotel %d" % n, room=lambda n: "Valley %d" % n,
                           stage=lambda n: "Season %s" % n if n else "")
    w = messages.words("en")
    rows = [dict(r, body="t%d" % r["id"], stage=3) for r in ROWS]
    seen = messages.as_json([r for r in rows if messages.may_see(r, 13, 7)], names, w, 13)
    assert [(m["from"], m["to"]) for m in seen] == [
        ("Educator", "everyone"), ("Educator", "everyone"), ("Hotel 11", "everyone"),
        ("Hotel 13", "the educator"), ("Educator", "you")]
    assert [m["mine"] for m in seen] == [False, False, False, True, False]
    assert seen[0]["room"] == "" and seen[0]["stage"] == "Season 3"
    everything = messages.as_json(rows, names, w, None)
    assert everything[0]["to"] == "everyone in Valley 7" and everything[0]["room"] == "", "said once"
    assert everything[3]["room"] == "Valley 7", "a message to one hotel names its room"
    one = messages.Names(party=names.party, room=names.room, rooms=False)
    assert messages.as_json(rows, one, w, None)[3]["room"] == "", "a session with one room never names it"
    assert everything[3]["to"] == "Hotel 12" and everything[6]["hidden"] is True


def test_every_language_has_every_word_and_keeps_the_placeholders():
    english = json.loads((ROOT / "messages_words" / "en.json").read_text(encoding="utf-8"))
    educator_only = {"hide", "show_again", "hidden"}
    for lang in messages.LANGUAGES:
        words = json.loads((ROOT / "messages_words" / (lang + ".json")).read_text(encoding="utf-8"))
        assert set(english) - educator_only <= set(words), lang
        for key, text in words.items():
            assert set(re.findall(r"\{\w+\}", text)) == set(re.findall(r"\{\w+\}", english[key])), (lang, key)
    assert messages.words("xx")["send"] == "Send"
    assert messages.words("de")["send"] == "Senden" and messages.words("de")["hide"] == "Hide"


def test_the_panel_carries_its_data_escaped_and_hides_the_form_when_off():
    env = jinja2.Environment(loader=jinja2.PrefixLoader({"account_kit": jinja2.FileSystemLoader(str(ROOT / "account_templates"))}),
                             autoescape=True)
    tpl = env.from_string('{% from "account_kit/messages.html" import messages_panel %}'
                          '{{ messages_panel(mode="participant", words=w, poll_url="/api/messages", send_url="/play/message",'
                          ' recipients=[("all", "Everyone"), ("0", "The educator")], initial=initial, token="1.2.0",'
                          ' can_send=can_send, state="off") }}')
    html = tpl.render(w=messages.words("en"), can_send=False,
                      initial=[{"id": 1, "from": '<b>"x"</b>', "to": "everyone", "text": "<script>"}])
    assert "<script>" not in html and "<b>" not in html
    assert 'data-messages-form hidden' in html and "The educator has turned messages off." in html
    assert "The educator can read every message." in html
    on = tpl.render(w=messages.words("en"), can_send=True, initial=[])
    assert 'data-messages-form>' in on and 'data-messages-state hidden' in on


def test_the_table_contract_has_the_columns_the_statements_use():
    for column in ("session_id", "room", "sender", "recipient", "author_ref", "stage", "body", "hidden_at", "created_at"):
        assert "`%s`" % column in messages.CREATE_TABLE
    assert "varchar(%d)" % messages.TEXT_MAX in messages.CREATE_TABLE
