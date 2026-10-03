"""The repair-contract judges: each one passes the good case and catches the bad."""
from __future__ import annotations

import pytest

from phronon_common.testing import repair_contract as rc


def test_a_refusal_that_wrote_nothing_passes():
    rows = {"a": 1}
    resp = rc.assert_refusal_changes_nothing(lambda: dict(rows), lambda: 400, lambda r: r == 400)
    assert resp == 400


def test_a_refusal_that_wrote_something_fails():
    rows = {"a": 1}

    def attempt():
        rows["a"] = 2
        return 400

    with pytest.raises(AssertionError, match="still changed"):
        rc.assert_refusal_changes_nothing(lambda: dict(rows), attempt, lambda r: r == 400)


def test_an_attempt_that_was_not_refused_fails():
    with pytest.raises(AssertionError, match="not refused"):
        rc.assert_refusal_changes_nothing(lambda: 1, lambda: 200, lambda r: r >= 400)


def test_an_audit_row_naming_the_participant_fails_in_any_column():
    rows = [{"action": "participant_deleted", "subject": "AB12",
             "details": '{"class_code": "AB12", "email": "Ana@Example.org"}'}]
    with pytest.raises(AssertionError, match="ana@example.org"):
        rc.assert_audit_never_names(rows, ["ana@example.org"])


def test_the_educator_may_be_named_and_an_empty_trail_is_suspicious():
    rows = [{"admin_email": "teacher@example.org", "details": '{"participant_id": 7}'}]
    rc.assert_audit_never_names(rows, ["ana@example.org", "teacher@example.org"],
                                educator_address="teacher@example.org")
    with pytest.raises(AssertionError, match="no audit rows"):
        rc.assert_audit_never_names([], ["ana@example.org"])


def test_a_private_value_anywhere_in_the_page_fails():
    html = '<tr data-id="4"><input type="hidden" name="a_rationalist" value="37"></tr>'
    with pytest.raises(AssertionError, match="37"):
        rc.assert_page_never_shows(html, [37])
    rc.assert_page_never_shows("<p>137 and 3.7 and 370</p>", [37])  # whole tokens only
