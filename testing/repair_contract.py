"""The repair contract's behaviour, as assertions each tool runs on its own routes.

README "Repair and Add a participant by hand" (25 September 2026) is the
contract Whiteout, Layoff and Polarity Profiler follow. It is shared on
purpose as BEHAVIOUR, not as code: the tools' data, scoring and privacy rules
differ, so each keeps its own routes, SQL and audit actions. What every one of
them must guarantee is the same, and that is what lives here:

  * a refusal writes NOTHING (no half-applied change);
  * an audit row never names the participant, because the audit log outlives
    their data by up to twelve months (the privacy notices promise only the
    educator's address and IP there);
  * a value the participant was promised the educator never sees appears
    nowhere in the educator's page, hidden fields included.

Each tool supplies the adapters (how to read its rows back, how to call its
route, which values are private); these functions only judge. No pytest
import, like the rest of the kit: a failure is an AssertionError.

Found when this was written (3 October 2026): Layoff wrote the participant's
address into three audit actions, and its tests asserted that it did. Whiteout
and Polarity Profiler checked a refusal on one route each.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterable

#: The README section this implements. Bump it with the section.
CONTRACT_VERSION = "2026-09-25"


def assert_refusal_changes_nothing(snapshot: Callable[[], Any], attempt: Callable[[], Any],
                                   refused: Callable[[Any], bool], what: str = "") -> Any:
    """`attempt()` must be refused, and `snapshot()` must read the same after.

    `snapshot` reads back every row the route could touch (all of them, not
    the one the attempt aimed at: a wrong WHERE clause writes somewhere else).
    `refused(response)` says what a refusal looks like in this tool (a 4xx, a
    303 with ?err=, or {"success": false}). Returns the response."""
    before = snapshot()
    response = attempt()
    assert refused(response), f"{what or 'the attempt'} was not refused: {response!r}"
    after = snapshot()
    assert after == before, (f"{what or 'a refused attempt'} still changed the data:\n"
                             f"before={before!r}\nafter={after!r}")
    return response


def _texts(row: Any) -> Iterable[str]:
    if isinstance(row, dict):
        for v in row.values():
            yield from _texts(v)
    elif isinstance(row, (list, tuple, set)):
        for v in row:
            yield from _texts(v)
    elif isinstance(row, (bytes, bytearray)):
        yield row.decode("utf-8", errors="replace")
    elif row is not None:
        yield str(row)


def assert_audit_never_names(audit_rows: Iterable[Any], addresses: Iterable[str],
                             educator_address: str | None = None) -> None:
    """No audit row carries a participant's address, in ANY column.

    Pass every audit row the test produced (the details JSON, subject and all
    other columns are searched, case-insensitively). `educator_address` is
    allowed: it is the actor, and the notices say it is recorded."""
    wanted = [a.lower() for a in addresses if a]
    assert wanted, "give the participant addresses the test used"
    if educator_address:
        wanted = [a for a in wanted if a != educator_address.lower()]
    rows = list(audit_rows)
    assert rows, "no audit rows: either the route wrote none, or the test read the wrong ones"
    for row in rows:
        blob = "\n".join(_texts(row)).lower()
        for address in wanted:
            assert address not in blob, (f"an audit row names participant {address}: "
                                         f"{row!r}. The audit log outlives their data.")


def assert_page_never_shows(html: str, private_values: Iterable[Any], where: str = "") -> None:
    """None of `private_values` appears in `html`: text, attributes, hidden
    inputs, embedded JSON. Values are matched as whole tokens, so pass
    distinctive ones (a test can choose scores no page would print by chance,
    such as 37, 63, 71, 29)."""
    for v in private_values:
        token = json.dumps(v) if not isinstance(v, str) else v
        pattern = r"(?<![\w.])" + re.escape(token) + r"(?![\w.])"
        hit = re.search(pattern, html)
        assert not hit, (f"{where or 'the page'} shows a private value {token!r}: "
                         f"...{html[max(0, hit.start() - 80):hit.end() + 80]}...")
