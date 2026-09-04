"""How a test RUN reports itself: unexpected skips, and the summary e-mail.

Two rules the whole fleet keeps, written once here since 4 September 2026.

1. **A skipped test proves nothing.** Where a green result is a GATE — in CI
   and on the server — a skip whose reason is not on the allowed list fails the
   run. The reason must be about the ENVIRONMENT (missing credentials, an
   opt-in suite, no disposable database), never about the code under test. The
   skip this rule exists to catch is the "X not found in app.py" kind: the test
   looked for something, did not find it, and quietly tested nothing, which is
   how a rename silently deletes coverage.

2. **Every server-side run says so in the owner's inbox.** One mail per run to
   the same mailbox as the sample e-mails, with the counts the terminal shows.
   A missing summary after a deploy means the run died before the end.

WHY THE HOOKS ARE STILL IN EACH conftest.py
pytest finds `pytest_runtest_logreport`, `pytest_sessionfinish` and
`pytest_terminal_summary` by NAME, in the project's own conftest. Keeping the
three definitions there is not a formality: it is what stops a tool from
quietly losing the rule while its CI stays green, and it keeps each tool's own
`_ALLOWED_SKIPS` additions — several of which are half of a matched pair with a
reason string in a test file — visible in the project they belong to.

No pytest import here (see phronon_common/testing/__init__.py): these functions
take the objects pytest hands the hooks and nothing more.
"""
from __future__ import annotations

from pathlib import Path

#: Allowed everywhere: eight environmental reasons that are true in every tool.
#: A tool ADDS to this tuple in its own conftest — mostly its own phrasing for
#: "no database here" — and those additions stay local, with their reasons.
BASE_ALLOWED_SKIPS = (
    "RUN_SERVER_SMOKE",                 # opt-in post-deploy suite
    "SMOKE_ADMIN_EMAIL",                # ditto, needs real admin credentials
    "no local .env",                    # live-mail tests off-server
    "defines no mail settings",         # ditto
    "fleet workspace not checked out",  # cross-repo test, isolated CI checkout
    "requires the live server",         # opt-in
    "Local working copy",               # live e-mail only ever sends FROM the server
    "SEND_TEST_EMAILS=0",               # live sending explicitly switched off
)

# NOTE on the live-e-mail tests: only the "we are not on the server" case is
# allowed. Missing credentials ON the server is reported as an ERROR by
# live_sending_status() and fails — a mail outage must not hide in a green run.

SERVER_ROOTS = ("/var/www/", "/opt/")


def collect_unexpected_skip(report, allowed, sink: list) -> None:
    """Append `report` to `sink` if it is a skip for an unrecognised reason."""
    if not report.skipped or hasattr(report, "wasxfail"):
        return
    longrepr = report.longrepr
    reason = (str(longrepr[2]) if isinstance(longrepr, tuple) and len(longrepr) == 3
              else str(longrepr))
    if any(a in reason for a in allowed):
        return
    sink.append(f"{report.nodeid}\n      {reason}")


def strict_about_skips(conftest_file: Path | str) -> bool:
    """Strict only where a green result is a GATE: CI, and the server.

    On a laptop a skip is often a real environment gap — no database, no
    credentials — and the fixtures already encode that deliberately: they skip
    locally and fail on the server. Forcing a local red would fight that design
    and make the suite unusable off-server. Locally we warn instead.
    """
    import os
    if os.environ.get("GITHUB_ACTIONS") == "true":
        return True
    return str(Path(conftest_file).resolve()).startswith(SERVER_ROOTS)


def report_unexpected_skips(session, unexpected: list, strict: bool) -> None:
    """Print the unrecognised skips; where a green run is a gate, fail it."""
    if not unexpected:
        return
    if not strict:
        print(f"\n[note] {len(unexpected)} unexpected skip(s); "
              f"these fail the run in CI and on the server.")
        return
    print("\n" + "=" * 70)
    print(f"{len(unexpected)} test(s) skipped for a reason that is not allowed.")
    print("A skipped test proves nothing. Either fix the test, or — if the skip is")
    print("genuinely about the environment — add it to _ALLOWED_SKIPS in conftest.py")
    print("with a comment saying why.\n")
    for item in unexpected:
        print(f"  ✗ {item}")
    print("=" * 70)
    session.exitstatus = 1


def send_run_summary(terminalreporter, exitstatus, project_root: Path | str,
                     tool_name: str) -> None:
    """One mail per server-side suite run, with the counts the terminal shows.

    Same live-send guard as `scripts/send_test_emails.py`: on a local working
    copy nothing is sent (SEND_TEST_EMAILS=1/0 forces it), and a failure here
    only prints a warning — the summary must never turn the run red.
    """
    import importlib.util as _ilu

    try:
        _root = Path(project_root).resolve()
        _spec = _ilu.spec_from_file_location(
            "_ste_for_summary", _root / "scripts" / "send_test_emails.py")
        _ste = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_ste)
        _status, _ = _ste.live_sending_status()
        if _status != "send":
            return
        _stats = terminalreporter.stats
        _n = {k: len(_stats.get(k, [])) for k in
              ("passed", "failed", "error", "skipped", "deselected")}
        if not any(_n[k] for k in ("passed", "failed", "error")):
            return  # collect-only or nothing ran — nothing worth mailing
        import os as _os
        import smtplib as _smtplib
        from email.message import EmailMessage as _EmailMessage

        _verdict = ("PASSED" if exitstatus == 0
                    else "FAILED (exit " + str(exitstatus) + ")")
        # Anything red (or an unexpected-skip exit) shouts from the inbox:
        # URGENT in the subject plus high-priority headers, so a broken run
        # cannot hide among the routine summaries.
        _urgent = "URGENT: " if (exitstatus != 0 or _n["failed"]
                                 or _n["error"]) else ""
        _line = (str(_n["passed"]) + " passed, " + str(_n["failed"])
                 + " failed, " + str(_n["error"]) + " errors, "
                 + str(_n["skipped"]) + " skipped, "
                 + str(_n["deselected"]) + " deselected")
        _msg = _EmailMessage()
        _msg["Subject"] = (_urgent + "[TEST-SUMMARY] " + tool_name + " — "
                           + _verdict + ": " + _line)
        if _urgent:
            _msg["X-Priority"] = "1"
            _msg["Importance"] = "high"
        _sender = (_os.getenv("EMAIL_FROM") or _os.getenv("SMTP_FROM")
                   or _os.getenv("SMTP_USER", ""))
        _msg["From"] = _sender
        _msg["To"] = _ste.TEST_RECIPIENT
        _msg.set_content(
            tool_name + " test suite finished: " + _verdict + "\n\n" + _line
            + "\n\nThis summary is sent automatically after every server-side"
            " test run (deploys included), to the same mailbox as the sample"
            " e-mails. A missing summary after a deploy means the run died"
            " before the end - check the deploy output.")
        with _smtplib.SMTP(_os.getenv("SMTP_HOST", "smtp.ionos.de"),
                           int(_os.getenv("SMTP_PORT", "587")),
                           timeout=20) as _s:
            _s.ehlo()
            _s.starttls()
            _s.login(_os.getenv("SMTP_USER", _sender),
                     _os.getenv("SMTP_PASSWORD", ""))
            _s.send_message(_msg)
        terminalreporter.write_line(
            "test-summary e-mail sent to " + _ste.TEST_RECIPIENT)
    except Exception as _exc:  # noqa: BLE001 — must never fail the run
        terminalreporter.write_line(
            "test-summary e-mail NOT sent: "
            + type(_exc).__name__ + ": " + str(_exc))
