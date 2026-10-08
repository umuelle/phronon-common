"""Kit check: this tool's process writes no e-mail address to the log (8 October 2026).

Each tool calls `phronon_common.log_privacy.install_address_redaction()` first
thing in `config.py` (the hub in `app.py`). This check, run by each tool's own
`tests/test_fleet_baseline.py` after it has imported the app, proves the call is
there and does its job: a message argument and a refused-recipient traceback,
the shape that leaked, both come out with the domain only.

Plain assertions, no pytest import (see `testing/__init__.py`).
"""
from __future__ import annotations

import logging
import smtplib
import sys

from phronon_common import log_privacy

PROBE = "someone.probe@example.org"


def assert_addresses_never_reach_the_log() -> None:
    assert log_privacy.is_installed(), (
        "log records are not redacted in this process: call "
        "phronon_common.log_privacy.install_address_redaction() first thing in "
        "config.py (the hub: app.py). Without it an SMTP refusal writes the "
        "recipient's full address to the journal.")
    factory = logging.getLogRecordFactory()
    formatter = logging.Formatter()

    record = factory("fleet-kit", logging.ERROR, __file__, 1, "mail to %s refused", (PROBE,), None)
    text = formatter.format(record)
    assert PROBE not in text and "***@example.org" in text, text

    try:
        raise smtplib.SMTPRecipientsRefused({PROBE: (550, b"5.1.1 no such user")})
    except smtplib.SMTPRecipientsRefused:
        exc_info = sys.exc_info()
    record = factory("fleet-kit", logging.ERROR, __file__, 1, "send failed", (), exc_info)
    text = formatter.format(record)
    assert PROBE not in text, text
    assert "SMTPRecipientsRefused" in text and "***@example.org" in text, text
