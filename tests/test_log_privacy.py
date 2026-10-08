"""log_privacy: no e-mail address reaches the journal (8 October 2026)."""
from __future__ import annotations

import io
import logging
import smtplib

import pytest

from phronon_common import log_privacy
from phronon_common.testing.log_privacy import assert_addresses_never_reach_the_log

ADDR = "jane.doe+class7@uni-example.de"


@pytest.fixture(autouse=True)
def fresh_factory():
    original = logging.getLogRecordFactory()
    logging.setLogRecordFactory(logging.LogRecord)
    yield
    logging.setLogRecordFactory(original)


def _capture(name="lp-test"):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger = logging.getLogger(name)
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, stream


def test_the_domain_survives_and_the_person_does_not():
    assert log_privacy.redact_addresses(f"to {ADDR}, cc x@y.org") == \
        "to ***@uni-example.de, cc ***@y.org"


def test_message_arguments_and_exception_text_are_redacted():
    log_privacy.install_address_redaction()
    logger, stream = _capture()
    logger.warning("mail to %s failed: %s", ADDR, ValueError(f"bad {ADDR}"))
    out = stream.getvalue()
    assert ADDR not in out
    assert out.count("***@uni-example.de") == 2


def test_a_refused_recipient_traceback_is_redacted():
    log_privacy.install_address_redaction()
    logger, stream = _capture()
    try:
        raise smtplib.SMTPRecipientsRefused({ADDR: (550, b"no such user")})
    except smtplib.SMTPRecipientsRefused:
        logger.exception("retention mail failed for class %s", 7)
    out = stream.getvalue()
    assert ADDR not in out
    assert "SMTPRecipientsRefused" in out and "***@uni-example.de" in out


def test_argument_tuples_keep_their_shape_for_formatters_that_read_them():
    """uvicorn's access formatter unpacks record.args; it must still work."""
    log_privacy.install_address_redaction()
    record = logging.getLogRecordFactory()(
        "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", f"/join?email={ADDR}", "1.1", 200), None)
    assert isinstance(record.args, tuple) and len(record.args) == 5
    assert record.args[4] == 200
    assert ADDR not in record.getMessage()


def test_a_record_without_an_address_keeps_its_text():
    log_privacy.install_address_redaction()
    record = logging.getLogRecordFactory()(
        "x", logging.INFO, __file__, 1, "sweep anonymised %d of %d", (3, 9), None)
    assert record.getMessage() == "sweep anonymised 3 of 9"
    assert record.args == (3, 9)


def test_installing_twice_wraps_once():
    log_privacy.install_address_redaction()
    first = logging.getLogRecordFactory()
    log_privacy.install_address_redaction()
    assert logging.getLogRecordFactory() is first
    assert log_privacy.is_installed()


def test_the_kit_check_fails_without_the_install_and_passes_with_it():
    with pytest.raises(AssertionError, match="install_address_redaction"):
        assert_addresses_never_reach_the_log()
    log_privacy.install_address_redaction()
    assert_addresses_never_reach_the_log()
