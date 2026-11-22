"""Messages inside a session: the teams and the educator write to each other
(owner, 22 November 2026; Peak Season first, TO DO FL-160).

WHO WRITES TO WHOM
A session's participants sit in PARTIES (Peak Season: a hotel's team), and the
parties sit in ROOMS (Peak Season: a valley). The educator is party 0 and sits
in every room. A message goes

  * to everyone in its room (recipient NULL),
  * to one party of its room (recipient = that party's number),
  * to the educator (recipient 0),

and the educator may also write to every room at once (room NULL). A party
never reaches a room it is not in. Whatever a party sends, the educator can
read: the panel says so under the box (owner, 22 November 2026).

WHAT A PARTY SEES (may_see, and the same rule as SQL in _PARTY_SQL)
Every message of its own room and every message to all rooms, when it was
written to everyone, to this party, or by this party; never a hidden one. The
educator sees everything, hidden messages too, marked as hidden.

THE TABLE (each tool's own database, one migration; CREATE_TABLE is the
contract, the tool adds its own foreign keys):

    id          the order of the messages
    session_id  the session
    room        the room it was written in; NULL: every room (educator only)
    sender      the party that wrote it; 0: the educator
    recipient   NULL: everyone in the room; 0: the educator; else one party
    author_ref  the participant row that wrote it, so that the message goes
                with the person (a foreign key ON DELETE CASCADE in the tool);
                NULL for the educator. Never shown.
    stage       the tool's moment, for the record (Peak Season: the season)
    body        the text, TEXT_MAX characters at most, plain text
    hidden_at   set when the educator hid it: the parties no longer see it
    created_at  UTC

WHEN THEY GO
With the session's other personal data: the tool deletes a session's messages
on the day its addresses and names are deleted (Peak Season: retention.py),
and a participant's own with their row. Nothing here keeps them longer.

WHAT THE PAGE GETS
messages.js polls the tool's route with the last `token` it had; the route
answers {"same": true} while nothing changed (state_token, one cheap query),
or the newest LIST_MAX messages the asker may see, shaped by as_json with
the names the tool gives its parties. Text is never HTML: the page writes it
with textContent.

The words of the panel are here in the fleet's ten languages (messages_words/,
words()); a tool passes them to the page as they are, with its own names for
its rooms and parties.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

#: The longest message, in characters.
TEXT_MAX = 300
#: The newest this many messages go to a page.
LIST_MAX = 200
#: A party may send this many messages in this many seconds (the educator is not limited).
BURST = (6, 30)
#: The educator's party number.
EDUCATOR = 0
#: The table's name in every tool.
TABLE = "messages"
#: The languages messages_words/ holds, as the fleet's participant pages speak them.
LANGUAGES = ("ar", "de", "en", "es", "fr", "hi", "it", "pt", "ru", "zh")
WORDS_DIR = Path(__file__).resolve().parent / "messages_words"

CREATE_TABLE = """CREATE TABLE `messages` (
  `id` int NOT NULL AUTO_INCREMENT,
  `session_id` int NOT NULL,
  `room` int DEFAULT NULL,
  `sender` int NOT NULL,
  `recipient` int DEFAULT NULL,
  `author_ref` int DEFAULT NULL,
  `stage` int DEFAULT NULL,
  `body` varchar(300) COLLATE utf8mb4_unicode_ci NOT NULL,
  `hidden_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_messages_session` (`session_id`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""

_COLUMNS = "id, session_id, room, sender, recipient, stage, body, hidden_at, created_at"
_PARTY_SQL = ("hidden_at IS NULL AND (room IS NULL OR room = %s) "
              "AND (recipient IS NULL OR recipient = %s OR sender = %s)")


class Database(Protocol):
    """What this module needs of a tool's database (phronon_common.database.Database)."""

    def query_one(self, sql: str, params: Any = ...) -> Optional[dict[str, Any]]: ...

    def query_all(self, sql: str, params: Any = ...) -> list[dict[str, Any]]: ...

    def insert(self, sql: str, params: Any = ...) -> int: ...

    def write(self, sql: str, params: Any = ...) -> int: ...


class Refused(Exception):
    """A message that is not stored. `reason`: "empty" (nothing left after
    cleaning), "too_fast" (more than BURST), "recipient" (not in the room)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_CONTROL = re.compile(r"[\u0000-\u0009\u000b-\u001f\u007f-\u009f​-‏‪-‮⁦-⁩]")
_BLANK_LINES = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t ]+")


def clean_text(text: object) -> str:
    """The text as it is stored: NFC, no control or direction characters, at
    most one empty line in a row, trimmed, TEXT_MAX characters at most."""
    value = unicodedata.normalize("NFC", str(text or "")).replace("\r\n", "\n").replace("\r", "\n")
    value = _CONTROL.sub("", value)
    lines = [_SPACES.sub(" ", line).strip() for line in value.split("\n")]
    value = _BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    return value[:TEXT_MAX].strip()


def may_see(row: Mapping[str, Any], party: Optional[int], room: Optional[int]) -> bool:
    """Whether `party` (None: the educator) in `room` sees this message. The
    SQL of messages_for says the same; each tool's suite compares the two."""
    if party is None:
        return True
    if row.get("hidden_at") is not None:
        return False
    if row.get("room") is not None and row.get("room") != room:
        return False
    return row.get("recipient") is None or row.get("recipient") == party or row.get("sender") == party


def state_token(db: Database, session_id: int) -> str:
    """Changes whenever a message of the session is written, hidden, shown
    again or deleted. One query on the session's index."""
    row = db.query_one(
        "SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS last, "
        "COALESCE(SUM(CASE WHEN hidden_at IS NULL THEN 0 ELSE id END), 0) AS hidden "
        "FROM " + TABLE + " WHERE session_id = %s", (session_id,))
    if not row:
        return "0.0.0"
    return "%d.%d.%d" % (int(row["n"] or 0), int(row["last"] or 0), int(row["hidden"] or 0))


def messages_for(db: Database, session_id: int, party: Optional[int], room: Optional[int],
                 limit: int = LIST_MAX) -> list[dict[str, Any]]:
    """The newest `limit` messages `party` may see, oldest first. party None:
    the educator, who sees all of them (room is then ignored)."""
    limit = max(1, min(int(limit), 1000))
    if party is None:
        rows = db.query_all("SELECT " + _COLUMNS + " FROM " + TABLE + " WHERE session_id = %s "
                            "ORDER BY id DESC LIMIT %s", (session_id, limit))
    else:
        rows = db.query_all("SELECT " + _COLUMNS + " FROM " + TABLE + " WHERE session_id = %s AND "
                            + _PARTY_SQL + " ORDER BY id DESC LIMIT %s",
                            (session_id, room, party, party, limit))
    return list(reversed(rows))


def send(db: Database, *, session_id: int, room: Optional[int], sender: int, recipient: Optional[int],
         text: object, author_ref: Optional[int] = None, stage: Optional[int] = None,
         recipients: Sequence[int] = ()) -> int:
    """Store one message; returns its id. `recipients`: the parties of the room
    the sender may write to (the tool knows them); the educator and "everyone"
    are always allowed. Raises Refused."""
    body = clean_text(text)
    if not body:
        raise Refused("empty")
    if sender != EDUCATOR:
        if room is None:
            raise Refused("recipient")
        if recipient is not None and recipient != EDUCATOR and (recipient == sender or recipient not in recipients):
            raise Refused("recipient")
        most, seconds = BURST
        row = db.query_one("SELECT COUNT(*) AS n FROM " + TABLE + " WHERE session_id = %s AND sender = %s "
                           "AND created_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s SECOND)",
                           (session_id, sender, seconds))
        if row and int(row["n"] or 0) >= most:
            raise Refused("too_fast")
    return db.insert("INSERT INTO " + TABLE + " (session_id, room, sender, recipient, author_ref, stage, body, "
                     "created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, UTC_TIMESTAMP())",
                     (session_id, room, sender, recipient, author_ref, stage, body))


def set_hidden(db: Database, session_id: int, message_id: int, hidden: bool) -> bool:
    """The educator hides a message from the parties, or shows it again. True if it changed."""
    if hidden:
        sql = "UPDATE " + TABLE + " SET hidden_at = UTC_TIMESTAMP() WHERE id = %s AND session_id = %s AND hidden_at IS NULL"
    else:
        sql = "UPDATE " + TABLE + " SET hidden_at = NULL WHERE id = %s AND session_id = %s AND hidden_at IS NOT NULL"
    return db.write(sql, (message_id, session_id)) == 1


def delete_session(db: Database, session_id: int) -> int:
    """Every message of a session (the day its personal data goes). Returns how many."""
    return db.write("DELETE FROM " + TABLE + " WHERE session_id = %s", (session_id,))


@dataclass(frozen=True)
class Names:
    """How the tool names things for one page. `party(n)` the name of a party
    (0 is never asked: the educator's name is in the words), `room(n)` the name
    of a room, `stage(n)` a moment (None: not shown). `rooms`: False when the
    session has one room, so the educator's list does not repeat its name."""

    party: Callable[[int], str]
    room: Callable[[int], str] = lambda n: ""
    stage: Callable[[Optional[int]], str] = lambda n: ""
    rooms: bool = True


def as_json(rows: Sequence[Mapping[str, Any]], names: Names, words: Mapping[str, str],
            party: Optional[int]) -> list[dict[str, Any]]:
    """The messages as the page draws them, for `party` (None: the educator).
    `from` and `to` are written out; `mine` marks the asker's own party's,
    `direct` one that only two sides see, `hidden` one the educator hid."""
    out = []
    for r in rows:
        sender, recipient, room = int(r["sender"]), r.get("recipient"), r.get("room")
        if sender == EDUCATOR:
            who = words.get("educator", "Educator")
        else:
            who = names.party(sender)
        if recipient is None:
            if room is None:
                to = words.get("to_all_rooms", "everyone")
            elif party is None:
                to = words.get("to_everyone_in", "everyone in {room}").replace("{room}", names.room(int(room)))
            else:
                to = words.get("to_everyone", "everyone")
        elif int(recipient) == EDUCATOR:
            to = words.get("to_educator", "the educator")
        elif party is not None and int(recipient) == party:
            to = words.get("to_you", "you")
        else:
            to = names.party(int(recipient))
        out.append({
            "id": int(r["id"]), "from": who, "to": to, "text": str(r["body"]),
            "mine": party is not None and sender == party,
            "direct": recipient is not None,
            "hidden": r.get("hidden_at") is not None,
            # the educator's list names the room where "to" does not already
            "room": names.room(int(room)) if (party is None and names.rooms and room is not None
                                              and recipient is not None) else "",
            "stage": names.stage(r.get("stage")),
            "sender": sender,
        })
    return out


_WORDS_CACHE: dict[str, dict[str, str]] = {}


def words(lang: Optional[str]) -> dict[str, str]:
    """The panel's words in `lang` (English for a language it does not have,
    and for a word a language lacks)."""
    code = lang if lang in LANGUAGES else "en"
    if code not in _WORDS_CACHE:
        english = _read("en")
        _WORDS_CACHE[code] = {**english, **(_read(code) if code != "en" else {})}
    return dict(_WORDS_CACHE[code])


def _read(code: str) -> dict[str, str]:
    data = json.loads((WORDS_DIR / (code + ".json")).read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}
