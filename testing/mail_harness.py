"""The sample-mail harness: where test mail may go, and whether to send at all.

`scripts/send_test_emails.py` exists in eight tools to send a LIVE sample of
every message the tool can produce — two e-mail faults survived weeks in July
2026 because nothing ever sent a real message, and a test that stubs SMTP out
sees neither. Around each tool's own samples sat 130 identical lines: a .env
parser, the recipient allowlist, the "are we on the server" test, the
send/skip/error decision, and the CLI. They are here since 4 September 2026.

What stays in each tool's script, deliberately: TOOL_LABEL, PUBLIC_DOMAIN, the
URL paths, every `_send_*` function, and SAMPLES. Those are the tool's own
statement about what mail it sends.

The functions that need the project take it as an argument; each script keeps a
zero-argument wrapper of the same name, because the test suite and conftest
reach for `send_test_emails.live_sending_status()` and friends by name.

No pytest import here (see phronon_common/testing/__init__.py) — and this one
is imported by a PRODUCTION script, run by the service user on the server, so
it must stay stdlib-only.
"""
from __future__ import annotations

import os
import traceback
from pathlib import Path

#: Dedicated test mailbox — test e-mail never reaches a real inbox.
TEST_RECIPIENT = "test@phronon.org"

#: Every brand name in the fleet. The leak check asks whether a message for one
#: tool names any of the others; `services/email.py` is copy-pasted between
#: projects, so it is the July 2026 branding bug that this guards against. It
#: lives here, with the harness, because the sample script is what puts a brand
#: name into a real message.
FLEET_TOOL_NAMES = (
    "Controversy Generator",
    "Drawbridge Drama",
    "Inequality Explorer",
    "Layoff Exercise",
    "Moral Mirror",
    "Orgdesignsim",
    "Polarity Profiler",
    "Whiteout Exercise",
)

#: An obviously-fake token: if one of these ever turns up in a real inbox or a
#: log, it is from the sample script and grants nothing.
SAMPLE_TOKEN = "TEST-EMAIL-DO-NOT-USE-0000000000000000"

# ── Recipient allowlist ──────────────────────────────────────────────────────
# Test e-mail must never reach a real person. Every sample recipient is checked
# against this list before anything is sent — a hard refusal, not a warning, and
# deliberately NOT overridable by an environment variable: an override is the
# first thing that gets set "just this once" and then forgotten. Widening this
# is a code change, visible in review.
ALLOWED_RECIPIENT_DOMAINS = ("phronon.org",)

# Deployment roots. All nine Phronon units live under /var/www — verified
# against systemd, which is the only source of truth for where a tool runs.
# /opt is kept as a cheap safety net: a tool deployed outside these roots would
# skip its live e-mail test silently while still reporting a green run.
SERVER_ROOTS = ("/var/www/", "/opt/")


def parse_env_file(path: Path) -> dict:
    """Minimal .env parser — no python-dotenv dependency.

    Quoted values are taken verbatim. That is not pedantry: the Layoff mailbox
    password contains '#', and an unquoted '#' reads as a comment to both
    python-dotenv and systemd's EnvironmentFile.
    """
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_project_env(project_root: Path) -> bool:
    """Load the project's own .env into os.environ. Returns True if one existed.

    systemd injects these via EnvironmentFile for the running service, but that
    does nothing for a pytest run started by hand — without this, every server
    run would report "SMTP_PASSWORD not set" and prove nothing.
    """
    env_path = Path(project_root) / ".env"
    if not env_path.is_file():
        return False
    for key, value in parse_env_file(env_path).items():
        os.environ[key] = value
    return True


def recipient_refusal(address: str):
    """Return None if this address may receive test mail, else the reason why not."""
    addr = (address or "").strip()
    if "@" not in addr:
        return repr(address) + " is not an e-mail address."
    domain = addr.rsplit("@", 1)[-1].lower()
    if domain not in ALLOWED_RECIPIENT_DOMAINS:
        return (
            "refusing to send test e-mail to " + addr + " — the domain '" + domain +
            "' is not in ALLOWED_RECIPIENT_DOMAINS (" +
            ", ".join(ALLOWED_RECIPIENT_DOMAINS) + "). Test mail goes only to the "
            "dedicated test mailbox, never to a real inbox."
        )
    return None


def running_on_server(project_root: Path) -> bool:
    return str(project_root).startswith(SERVER_ROOTS)


def live_sending_status(project_root: Path) -> tuple:
    """Return (status, reason) where status is 'send', 'skip' or 'error'.

    The distinction matters more than it looks. 'skip' means we deliberately
    chose not to send (a local working copy); 'error' means we meant to send and
    could not — missing credentials on the server. Reporting the second as a
    skip is how an e-mail outage hides inside a green test run, so the caller
    must fail on 'error'.

    The reason strings are load-bearing: conftest's _ALLOWED_SKIPS recognises
    "Local working copy" and "SEND_TEST_EMAILS=0" and fails the run on any skip
    reason it does not know. Reword one here and every tool's server run fails.
    """
    project_root = Path(project_root)
    refusal = recipient_refusal(TEST_RECIPIENT)
    if refusal:
        return "error", refusal

    override = os.getenv("SEND_TEST_EMAILS", "").strip().lower()
    if override in ("0", "false", "no"):
        return "skip", "SEND_TEST_EMAILS=0 — live sending explicitly disabled."
    forced = override in ("1", "true", "yes")

    if not forced and not running_on_server(project_root):
        return "skip", (
            "Local working copy (" + str(project_root) + " is not under " +
            " or ".join(SERVER_ROOTS) + "), so no e-mail was sent. Real delivery is "
            "verified on the server, where the live .env is. Force a local send "
            "with SEND_TEST_EMAILS=1."
        )

    load_project_env(project_root)

    if not os.getenv("SMTP_PASSWORD"):
        env_path = project_root / ".env"
        detail = (
            "there is no .env file at " + str(env_path)
            if not env_path.is_file()
            else "the .env at " + str(env_path) + " does not define SMTP_PASSWORD"
        )
        legacy = ""
        if env_path.is_file() and "MAIL_PASSWORD" in parse_env_file(env_path):
            legacy = (
                " It does define MAIL_PASSWORD — the Flask-era name; "
                "services/email.py reads only SMTP_*. This is exactly the fault "
                "that silently broke Layoff-Exercise for weeks."
            )
        return "error", (
            "SMTP_PASSWORD is not set: " + detail + "." + legacy +
            " send_password_reset() fails closed, so no password reset can go out "
            "from this deployment."
        )

    return "send", ""


def send_all(samples, recipient: str = TEST_RECIPIENT) -> list:
    """Send every sample. Returns [(key, label, error_or_None), ...].

    Nothing is caught at a level that would let a failure pass as success — an
    exception is recorded per sample and re-surfaced by the caller.
    """
    refusal = recipient_refusal(recipient)
    if refusal:
        raise ValueError(refusal)
    results = []
    for key, label, sender in samples:
        try:
            sender(recipient)
            results.append((key, label, None))
        except Exception as exc:  # noqa: BLE001 — reported, not swallowed
            results.append((key, label, exc))
    return results


def main(argv: list, *, samples, tool_label: str, public_domain: str,
         status_of: callable, send: callable) -> int:
    """The CLI every tool's script exposes: send every sample, report each one.

    `status_of` and `send` are the tool's own zero/one-argument wrappers, so a
    tool that needs to do something before sending keeps that hook.
    """
    recipient = argv[1] if len(argv) > 1 else TEST_RECIPIENT

    refusal = recipient_refusal(recipient)
    if refusal:
        print("REFUSED — " + refusal)
        return 2

    status, reason = status_of()
    if status == "skip":
        print("SKIPPED — " + reason)
        return 0
    if status == "error":
        print("ERROR — " + reason)
        return 3

    sender_addr = (
        os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM")
        or "info@" + public_domain
    )
    print(
        tool_label + ": sending " + str(len(samples)) + " sample e-mail(s)\n"
        "  from " + sender_addr + " via "
        + os.getenv("SMTP_HOST", "smtp.ionos.de") + "\n"
        "  to   " + recipient
    )

    failures = 0
    for key, label, error in send(recipient):
        if error is None:
            print("  ok    " + label)
        else:
            failures += 1
            print("  FAIL  " + label + ": " + type(error).__name__ + ": " + str(error))
            traceback.print_exception(type(error), error, error.__traceback__)

    if failures:
        print("\n" + str(failures) + " of " + str(len(samples)) + " failed.")
        return 1
    print("\nAll sent. Check " + recipient + ".")
    return 0
