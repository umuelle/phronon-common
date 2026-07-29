"""Spreadsheet-export safety helpers (shared; audit item G2, 2026-07-29).

A cell that starts with ``=`` ``+`` ``-`` ``@`` (or tab/CR) is executed as a
live formula when an educator opens the export in Excel or LibreOffice — so a
participant-typed name can run code on the educator's machine. The OWASP
mitigation is to prefix such cells with a single quote, which forces them to be
read as text.

Numbers, dates and None pass through untouched; only strings are inspected.
For pandas/xlsxwriter exports use the engine option instead
(``strings_to_formulas=False`` — see Layoff), which fixes it at the writer.
"""
from __future__ import annotations

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value):
    """Return ``value`` neutralised for CSV export (strings only)."""
    if isinstance(value, str) and value[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def csv_safe_row(row: dict) -> dict:
    """``csv_safe`` applied to every value of a dict row (csv.DictWriter)."""
    return {k: csv_safe(v) for k, v in row.items()}
