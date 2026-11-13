"""The full-mail-set stamp in a folder of its own (TO DO FL-131).

deploy.sh names /var/lib/phronon-mail/<key> in PHRONON_MAIL_STAMP_DIR so that
the server's test run can later run as the tool's service user, who may not
write the checkout. What must hold: the stamp goes to that folder; while the
folder has none, the old stamp beside the code still counts (no second full
set the day the stamp moves); a stamp another user wrote is replaced, not
written into; and without the variable nothing changes.
"""
import os
import stat

import pytest

from phronon_common import mail_diagnostics as md

TODAY = "2026-11-13"


@pytest.fixture
def folders(tmp_path, monkeypatch):
    code, stamps = tmp_path / "checkout", tmp_path / "stamps"
    code.mkdir()
    stamps.mkdir()
    monkeypatch.setenv(md.STAMP_DIR_ENV, str(stamps))
    return code, stamps


def test_the_stamp_is_written_to_the_named_folder(folders):
    code, stamps = folders
    assert md.full_set_due(code, TODAY) is True
    md.record_full_send(code, TODAY)
    assert (stamps / md.FULL_SEND_STAMP).read_text().strip() == TODAY
    assert not (code / md.FULL_SEND_STAMP).exists()
    assert md.full_set_due(code, TODAY) is False
    assert [p.name for p in stamps.iterdir()] == [md.FULL_SEND_STAMP], "a temporary file was left"


def test_the_old_stamp_beside_the_code_still_counts_until_the_new_one_exists(folders):
    code, stamps = folders
    (code / md.FULL_SEND_STAMP).write_text(TODAY + "\n")
    assert md.full_set_due(code, TODAY) is False
    (stamps / md.FULL_SEND_STAMP).write_text("2026-11-12\n")
    assert md.full_set_due(code, TODAY) is True, "the new folder's stamp must win"


def test_a_read_only_stamp_of_another_user_is_replaced(folders):
    """root writes it today; the service user, who may write the folder but
    not that file, must still be able to move the day on."""
    code, stamps = folders
    old = stamps / md.FULL_SEND_STAMP
    old.write_text("2026-11-12\n")
    old.chmod(stat.S_IRUSR)
    md.record_full_send(code, TODAY)
    assert old.read_text().strip() == TODAY


def test_without_the_variable_the_stamp_stays_beside_the_code(tmp_path, monkeypatch):
    monkeypatch.delenv(md.STAMP_DIR_ENV, raising=False)
    md.record_full_send(tmp_path, TODAY)
    assert (tmp_path / md.FULL_SEND_STAMP).read_text().strip() == TODAY
    assert md.full_set_due(tmp_path, TODAY) is False
    assert os.environ.get(md.STAMP_DIR_ENV) is None
