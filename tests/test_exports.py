"""csv_safe: the formula-injection escape must fire on exactly the OWASP set."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from phronon_common.exports import csv_safe, csv_safe_row  # noqa: E402


def test_dangerous_prefixes_are_quoted():
    for prefix in ("=", "+", "-", "@", "\t", "\r"):
        assert csv_safe(prefix + "cmd") == "'" + prefix + "cmd"


def test_harmless_values_pass_through():
    assert csv_safe("hello") == "hello"
    assert csv_safe("") == ""
    assert csv_safe(None) is None
    assert csv_safe(42) == 42
    assert csv_safe(-3.5) == -3.5  # numbers stay numbers, only strings are escaped
    assert csv_safe(True) is True


def test_row_helper_touches_only_string_values():
    row = {"name": "=SUM(A1)", "score": -5, "note": "ok"}
    assert csv_safe_row(row) == {"name": "'=SUM(A1)", "score": -5, "note": "ok"}
