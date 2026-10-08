"""No e-mail address reaches the journal: every log record is redacted at birth.

WHY (8 October 2026). The fleet's rule is that a log names a recipient by
domain only (README §12, "An all-clear is a claim about a method and a moment";
`emails.recipient_domain`). Every log call the fleet writes on purpose follows
it. The leak that remained came from outside our own strings: when the mail
server refuses a recipient, smtplib raises `SMTPRecipientsRefused`, whose text
is the full address, and any handler that logs that exception (its message or
its traceback) writes the address to the journal, where no retention job ever
reaches it. The 8 October lint clean-up made more handlers log their
traceback, which made the hole wider.

Fixing each log call cannot hold: the README records three sweeps that each
missed a spelling. So the redaction sits where every record is made, for every
logger in the process: the tool's own, phronon_common's, uvicorn's and any
library's. `install_address_redaction()` wraps logging's record factory once;
each tool calls it first thing in `config.py` (the hub in `app.py`), and
`testing.log_privacy.assert_addresses_never_reach_the_log()` in each tool's
suite proves the call is there.

What it does to a record that contains an address (`name@domain.tld`):
  - the message, each string argument, and any argument whose text holds an
    address become `***@domain.tld`; argument tuples keep their shape, so
    formatters that read `record.args` (uvicorn's access log) still work;
  - an attached traceback is formatted once, redacted, and cached in
    `record.exc_text`, which every standard formatter uses instead of
    formatting the traceback again;
  - `stack_info` likewise.
A record without an address keeps its text. The domain survives on purpose:
it is what makes a mail log useful, and it identifies nobody.
"""
from __future__ import annotations

import logging
import re

ADDRESS = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_MARK = "_phronon_address_redaction"
_FORMATTER = logging.Formatter()


def redact_addresses(text: str) -> str:
    """`someone@example.org` -> `***@example.org`, everywhere in `text`."""
    return ADDRESS.sub(r"***@\1", text)


def _redact_value(value):
    if isinstance(value, str):
        return redact_addresses(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    try:
        text = str(value)
    except Exception:  # noqa: BLE001 - an unprintable argument cannot leak an address
        return value
    return redact_addresses(text) if ADDRESS.search(text) else value


def _redact_record(record: logging.LogRecord) -> logging.LogRecord:
    if isinstance(record.msg, str):
        record.msg = redact_addresses(record.msg)
    elif record.msg is not None and ADDRESS.search(str(record.msg)):
        record.msg = redact_addresses(str(record.msg))
    if isinstance(record.args, tuple):
        record.args = tuple(_redact_value(a) for a in record.args)
    elif isinstance(record.args, dict):
        record.args = {k: _redact_value(v) for k, v in record.args.items()}
    if record.exc_info and not record.exc_text:
        record.exc_text = redact_addresses(_FORMATTER.formatException(record.exc_info))
    if record.stack_info:
        record.stack_info = redact_addresses(record.stack_info)
    return record


def install_address_redaction() -> None:
    """Make every log record in this process address-free. Safe to call twice."""
    current = logging.getLogRecordFactory()
    if getattr(current, _MARK, False):
        return

    def factory(*args, **kwargs):
        return _redact_record(current(*args, **kwargs))

    setattr(factory, _MARK, True)
    logging.setLogRecordFactory(factory)


def is_installed() -> bool:
    return bool(getattr(logging.getLogRecordFactory(), _MARK, False))
