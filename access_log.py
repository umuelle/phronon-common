"""Keep bearer tokens out of the access log — one implementation for the fleet.

WHY (external review, 16 August 2026).

Several tools put a credential in the URL PATH, because that is what makes a
link work from an inbox without a password:

    LSR         /report/<token>          /withdraw/<token>
    Controversy /withdraw/<token>
    Inequality  /results/<code>/<token>
    Whiteout    /resume?token=…          /backoffice/postpone/<id>?token=…

Each of those is a bearer credential: whoever holds it can read one
participant's report, or withdraw their response, or move a deletion date. And
every one of them was being written out twice — into nginx's access log, and
into uvicorn's, which goes to journald with a twelve-month ceiling. An
access-log disclosure would therefore have been a report disclosure too, months
after the response itself was deleted.

THE JOURNAL COPY IS THE WORSE ONE. nginx keeps 14 days; the journal keeps a
year, is read routinely while debugging, and is included in the system backup.
Switching uvicorn's access log off entirely would take the request line with
it — and that line is how an operator sees traffic at all — so the path is
rewritten instead: the token segment becomes `<redacted>` and everything else
about the request survives, including the status and the timing.

DENY BY DEFAULT WOULD BE WRONG HERE. A filter that redacted every path segment
that "looks like" a token would quietly mangle join codes and class codes,
which operators genuinely need to read. The rules are therefore explicit and
per-tool: name the routes that carry a credential. A route added later without
a rule is not silently protected — which is why `assert_credential_paths_are_covered`
exists for the tools' own test suites.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable

# `token=` in a query string, whatever the tool. Query strings are the one place
# a generic rule is safe: nothing else in this fleet uses that parameter name.
_QUERY_TOKEN = re.compile(r"([?&]token=)[^&\s\"]+")


class RedactingAccessFilter(logging.Filter):
    """Rewrites credential-bearing paths in uvicorn's access records.

    uvicorn formats its access line from `record.args`, not from a preformatted
    message: `(client, method, path, http_version, status)`. Rewriting the path
    argument in place therefore leaves the format string, the status and the
    timing exactly as they were — this filter cannot change what an operator
    sees except for the credential itself.
    """

    def __init__(self, patterns: Iterable[str]):
        super().__init__()
        # Compiled once. Each pattern must capture the part to KEEP in group 1;
        # everything matched after it is replaced.
        self._patterns = [re.compile(p) for p in patterns]

    def _redact(self, path: str) -> str:
        for pattern in self._patterns:
            path = pattern.sub(r"\1<redacted>", path)
        return _QUERY_TOKEN.sub(r"\1<redacted>", path)

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn.access passes a 5-tuple; anything else is left alone rather
        # than guessed at — a filter that raises takes the log line with it.
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path = args[2]
            redacted = self._redact(path)
            if redacted != path:
                record.args = (args[0], args[1], redacted, args[3], args[4])
        return True


def install(patterns: Iterable[str]) -> RedactingAccessFilter:
    """Attach the filter to uvicorn's access logger. Safe to call twice.

    Called at import from each tool's app.py, so it is in place before the
    first request — a filter added later would miss whatever had already been
    logged, and on a busy restart that is not nothing.
    """
    flt = RedactingAccessFilter(patterns)
    access = logging.getLogger("uvicorn.access")
    for existing in list(access.filters):
        if isinstance(existing, RedactingAccessFilter):
            access.removeFilter(existing)
    access.addFilter(flt)
    return flt


def assert_credential_paths_are_covered(patterns: Iterable[str],
                                        samples: dict[str, str]) -> None:
    """Raise unless every sample path is redacted. For a tool's own test.

    `samples` maps a realistic request path to the token that must not survive.
    """
    flt = RedactingAccessFilter(patterns)
    leaked = []
    for path, secret in samples.items():
        if secret in flt._redact(path):
            leaked.append(path)
    if leaked:
        raise AssertionError(
            "these credential-bearing paths would reach the access log intact:\n  "
            + "\n  ".join(leaked))
