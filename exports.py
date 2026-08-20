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


# ── The four things a CSV download must do (FL-022, 20 August 2026) ──────────
#
# Export is where the same mistakes keep recurring together: authenticate,
# check ownership, write the audit row, and tell caches not to keep it. Layoff's
# download route was missing two of them until 16 August — any signed-in
# educator could pull another class's participants, e-mail addresses included,
# and nothing was written down when they did. Orgdesignsim's results export
# wrote no audit row until today.
#
# A helper cannot authenticate for the caller; the route knows who is signed in
# and whose data this is. What it CAN do is refuse to build a response without
# the evidence that those checks happened — an actor and a working audit writer
# — and then get the parts nobody should have to remember right: formula
# neutralisation on every cell, and `Cache-Control: no-store` on a file full of
# participant data.

def csv_download(*, filename, header, rows, audit, actor,
                 action="data_exported", subject=None, details=None,
                 request=None, admin_id=None):
    """Build an audited, non-cached CSV download.

    `audit` is the tool's own `_audit` — the same keyword signature in all nine
    since FL-021, which is what makes one helper possible. It is called BEFORE
    the body is built: a row that describes an export that then failed is a
    smaller problem than an export nobody can see.

    Raises ValueError rather than emitting an unattributed file. That is the
    point: a missing audit row is a review finding today and a shape error here.
    """
    import csv as _csv
    import io as _io
    from fastapi.responses import StreamingResponse

    if not actor:
        raise ValueError(
            "csv_download needs the signed-in actor — an export with no named "
            "exporter cannot be audited, and an unaudited export of participant "
            "data is the finding this helper exists to prevent")
    if audit is None:
        raise ValueError("csv_download needs the tool's _audit writer")

    audit(action, request=request, subject=subject, details=details,
          admin_id=admin_id, admin_email=actor)

    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(list(header))
    for row in rows:
        writer.writerow([csv_safe(v) for v in row])
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # Participant data must not sit in a shared or browser cache: the
            # educator's laptop is often the classroom machine.
            "Cache-Control": "no-store",
        },
    )
