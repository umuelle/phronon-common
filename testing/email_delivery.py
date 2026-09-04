"""E-mail tests: what the messages say, and whether they actually go out.

Two layers, because the July 2026 faults needed both:

  Offline (always runs, no network). Drives the real send_password_reset()
  with SMTP swapped for a capture, then asserts on the finished MIME message —
  subject, sender, and both body parts. Asserting on the assembled message
  rather than on _reset_bodies() is deliberate: the "Wealth Inequality Explorer"
  bug sat in the subject *and* in four places in the body, and a fix that only
  touched the subject still looked correct to a body-only check.

  Live (server only). Sends the real thing to test@phronon.org through the
  app's own code path, so a wrong env-var name or a dead mailbox fails there
  the way it fails in production. On a local working copy this skips; on the
  server with credentials missing it FAILS, because a silent skip is how an
  outage hides inside a green run.

SHARED SINCE 4 SEPTEMBER 2026. 244 of each tool's ~330 lines were the same in
all eight once the tool's own name and domain are substituted. What stays local
is each tool's name, its SMTP sender, and the mail TYPES only it has.

`FLEET_TOOL_NAMES` moved here for a reason beyond duplication: the eight copies
had drifted, and in FIVE of them the list omitted "Whiteout Exercise" and
repeated the tool's own name instead. Since the leak check is
`[n for n in FLEET_TOOL_NAMES if n != TOOL_NAME]`, those five were never
checking for a Whiteout brand name at all — the exact class of bug the check
exists to catch. One list, in one place, cannot drift that way.

No pytest import here — see phronon_common/testing/__init__.py. The fixtures
stay in each tool's own test module and call `capture_password_reset` below.
"""
from __future__ import annotations

import email as email_lib
import importlib.util
import logging
from pathlib import Path

# The canonical brand list lives with the sample-mail harness, which is what
# puts a brand name into a real message; re-exported here because this contract
# is where the leak check reads it.
from phronon_common.testing.mail_harness import FLEET_TOOL_NAMES  # noqa: F401


def other_fleet_names(tool_name: str) -> list[str]:
    """Every fleet brand name except this tool's own."""
    assert tool_name in FLEET_TOOL_NAMES, (
        f"{tool_name!r} is not in FLEET_TOOL_NAMES — either the tool is new and "
        f"the fleet list has not learned it, or the name is misspelt, and either "
        f"way this tool's own name would be searched for as a leak")
    return [n for n in FLEET_TOOL_NAMES if n != tool_name]


class CapturingSMTP:
    """Stands in for smtplib.SMTP and records what was handed to sendmail()."""

    captured: list = []

    def __init__(self, host, port, *args, **kwargs):
        self.host = host
        self.port = port

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self, *a, **kw):
        pass

    def starttls(self, *a, **kw):
        pass

    def login(self, user, password):
        self.user = user

    def sendmail(self, sender, recipients, raw):
        type(self).captured.append(
            {"host": self.host, "port": self.port, "sender": sender,
             "recipients": recipients, "raw": raw}
        )


def load_sender_module(project_root: Path | str):
    """Import scripts/send_test_emails.py, which is not on a package path."""
    path = Path(project_root) / "scripts" / "send_test_emails.py"
    spec = importlib.util.spec_from_file_location("_send_test_emails", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parts(message) -> dict:
    """Return {'text/plain': body, 'text/html': body} from a multipart message."""
    out = {}
    for part in message.walk():
        ctype = part.get_content_type()
        if ctype in ("text/plain", "text/html"):
            out[ctype] = part.get_payload(decode=True).decode("utf-8", "replace")
    return out


def capture_password_reset(monkeypatch, sender_module, smtp_user: str) -> dict:
    """Run the real send_password_reset() against a fake SMTP; return the message.

    Called from each tool's own `captured_reset` fixture, which is where the
    pytest dependency belongs.
    """
    import services.email as email_service

    monkeypatch.setenv("SMTP_PASSWORD", "not-a-real-password")
    monkeypatch.setenv("SMTP_USER", smtp_user)
    monkeypatch.delenv("EMAIL_FROM", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    monkeypatch.setattr(email_service.smtplib, "SMTP", CapturingSMTP)
    CapturingSMTP.captured = []

    url = sender_module.sample_reset_url()
    email_service.send_password_reset("recipient@example.org", url)

    assert CapturingSMTP.captured, (
        "send_password_reset() sent nothing even with SMTP_PASSWORD set — it "
        "returned early, so no password reset would ever leave this deployment."
    )
    record = CapturingSMTP.captured[-1]
    record["message"] = email_lib.message_from_string(record["raw"])
    record["reset_url"] = url
    return record


class _EmailContract:
    """Config every mixin below shares. The tool sets these."""

    TOOL_NAME: str = ""
    PROJECT_ROOT: Path | None = None
    #: The imported scripts/send_test_emails.py module.
    sender_module = None

    @property
    def other_fleet_names(self) -> list[str]:
        return other_fleet_names(self.TOOL_NAME)


class PasswordResetMessage(_EmailContract):
    """Needs a `captured_reset` fixture, defined in the tool's own module."""

    def test_is_multipart_with_text_and_html(self, captured_reset):
        p = parts(captured_reset["message"])
        assert "text/plain" in p, "no plain-text alternative"
        assert "text/html" in p, "no HTML alternative"

    def test_subject_names_this_tool(self, captured_reset):
        subject = str(email_lib.header.make_header(
            email_lib.header.decode_header(captured_reset["message"]["Subject"])
        ))
        assert self.TOOL_NAME in subject, (
            "subject is " + repr(subject) + " — it must name " + self.TOOL_NAME
        )

    def test_both_bodies_name_this_tool(self, captured_reset):
        for ctype, body in parts(captured_reset["message"]).items():
            assert self.TOOL_NAME in body, (
                ctype + " body never mentions " + self.TOOL_NAME)

    def test_no_other_fleet_tool_is_named(self, captured_reset):
        subject = captured_reset["message"]["Subject"] or ""
        haystacks = dict(parts(captured_reset["message"]), subject=subject)
        for where, body in haystacks.items():
            for other in self.other_fleet_names:
                assert other not in body, (
                    other + " appears in the " + where + " of a " + self.TOOL_NAME +
                    " e-mail. services/email.py is copy-pasted between tools; "
                    "this is the July 2026 branding bug recurring."
                )

    def test_reset_link_is_in_both_bodies(self, captured_reset):
        for ctype, body in parts(captured_reset["message"]).items():
            assert captured_reset["reset_url"] in body, (
                ctype + " body does not contain the reset link — the recipient "
                "cannot complete the reset."
            )

    def test_sender_and_recipient(self, captured_reset):
        assert captured_reset["message"]["To"] == "recipient@example.org"
        assert "@" in (captured_reset["message"]["From"] or "")
        assert captured_reset["recipients"] == ["recipient@example.org"]


class SmtpConfiguration(_EmailContract):
    """How the sampler is configured, and what it must refuse.

    `OUTSIDE_ADDRESSES` is a plain attribute rather than a pytest parametrize so
    that this class carries no pytest import; the tool's subclass gets one test
    that walks them, which fails naming the address that was accepted.
    """

    OUTSIDE_ADDRESSES = (
        "urs@urs-mueller.com",          # a real inbox — the thing being prevented
        "someone@example.org",
        "student@university.edu",
        "test@phronon.org.evil.com",    # suffix trick
        "test@notphronon.org",          # substring trick
        "",
        "not-an-address",
    )

    def test_samples_go_only_to_the_dedicated_test_mailbox(self):
        """Test mail must never reach a real person's inbox.

        The recipient is a single constant, so a careless edit (or a copy-paste
        from another tool) could silently redirect live sends. This pins it.
        """
        assert self.sender_module.TEST_RECIPIENT == "test@phronon.org", (
            "samples would be sent to " + repr(self.sender_module.TEST_RECIPIENT) +
            " — the fleet's dedicated test mailbox is test@phronon.org."
        )

    def test_only_phronon_org_is_an_allowed_recipient_domain(self):
        assert self.sender_module.ALLOWED_RECIPIENT_DOMAINS == ("phronon.org",), (
            "the recipient allowlist is " +
            repr(self.sender_module.ALLOWED_RECIPIENT_DOMAINS) +
            " — test mail must be confined to phronon.org."
        )

    def test_the_configured_recipient_passes_its_own_allowlist(self):
        assert self.sender_module.recipient_refusal(
            self.sender_module.TEST_RECIPIENT) is None

    def test_outside_addresses_are_refused(self):
        """One test over every address, not one test each.

        The eight copies parametrized this, which made seven test ids; here it
        is one that names EVERY address that got through rather than stopping
        at the first. Fewer ids, strictly more information on failure — and the
        collapse is why this file collects five fewer tests per tool than the
        copies it replaced.
        """
        accepted = [a for a in self.OUTSIDE_ADDRESSES
                    if self.sender_module.recipient_refusal(a) is None]
        assert not accepted, (
            f"accepted as test recipients: {accepted!r} — test mail must be "
            f"confined to phronon.org, and each of these would reach a real "
            f"inbox")

    def test_the_fleet_name_list_is_the_shared_one(self):
        """Five of the eight copies of this list had dropped "Whiteout
        Exercise" and repeated the tool's own name instead, so their leak check
        silently stopped looking for one of the eight brands.

        Since v1.37.0 the script IMPORTS the list, so this asks for identity,
        not equality: a tool that goes back to keeping its own copy fails here
        even if the copy happens to be correct today.
        """
        assert self.sender_module.FLEET_TOOL_NAMES is FLEET_TOOL_NAMES, (
            "scripts/send_test_emails.py no longer takes the fleet name list "
            "from phronon_common.testing — a private copy is how five tools "
            "stopped checking for a Whiteout brand leak"
        )

    def test_send_all_refuses_an_outside_address(self, monkeypatch):
        """The refusal must live in send_all(), not only in the CLI.

        The test suite calls send_all() directly, so a guard placed only in
        main() would leave the pytest path unprotected.
        """
        called = []
        monkeypatch.setattr(
            self.sender_module, "SAMPLES",
            (("x", "x", lambda r: called.append(r)),),
        )
        try:
            self.sender_module.send_all("urs@urs-mueller.com")
        except ValueError:
            pass
        else:
            raise AssertionError("send_all accepted an outside address")
        assert not called, "a sample was sent despite the refusal"

    def test_send_is_skipped_when_password_missing(self, monkeypatch):
        """Fail-closed: no credentials must mean no send, never a crash."""
        import services.email as email_service

        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.setattr(email_service.smtplib, "SMTP", CapturingSMTP)
        CapturingSMTP.captured = []
        email_service.send_password_reset("recipient@example.org", "https://x/y")
        assert not CapturingSMTP.captured

    def test_reset_url_is_never_logged_in_production(self, monkeypatch, caplog):
        """A reset URL is a live credential (security audit, finding 3).

        Moral Mirror was still logging it in July 2026, months after the other
        seven tools were fixed: the guard lives in a file that is copy-pasted
        between projects, so it can go missing again exactly the same way.
        """
        import services.email as email_service

        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.setenv("PRODUCTION", "1")
        url = "https://example.org/reset?token=SECRET-TOKEN-VALUE"

        with caplog.at_level(logging.DEBUG, logger=email_service.logger.name):
            email_service.send_password_reset("educator@example.org", url)

        assert caplog.text.strip(), (
            "nothing was logged when SMTP was unconfigured — an operator would "
            "have no idea the password reset never went out."
        )
        assert "SECRET-TOKEN-VALUE" not in caplog.text, (
            "the reset token was written to the log in production. Anyone with "
            "log access could take over the account."
        )

    def test_the_reset_url_needs_an_explicit_opt_in(self, monkeypatch, caplog):
        """The link is logged ONLY when LOG_RESET_LINKS is set (16 Aug 2026).

        It used to be logged whenever PRODUCTION was unset — but "not
        production" is any box where one environment variable happens to be
        missing, which is a weaker guarantee than it reads as. A reset URL is a
        live credential; logging one should be a decision somebody made, not a
        default they inherited.

        The dev convenience survives, one flag away, and the message says so —
        which is what stops "never log the URL" from being satisfied by
        dropping the logging entirely and leaving no way to reset locally.
        """
        import services.email as email_service

        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        monkeypatch.delenv("PRODUCTION", raising=False)
        monkeypatch.delenv("LOG_RESET_LINKS", raising=False)
        url = "https://example.org/reset?token=DEV-TOKEN-VALUE"

        with caplog.at_level(logging.DEBUG, logger=email_service.logger.name):
            email_service.send_password_reset("educator@example.org", url)
        assert "DEV-TOKEN-VALUE" not in caplog.text, (
            "a live reset link was logged without anyone opting in"
        )
        assert "LOG_RESET_LINKS" in caplog.text, (
            "the message must say how to get the link, or the dev flow is "
            "simply broken with no hint why"
        )

        caplog.clear()
        monkeypatch.setenv("LOG_RESET_LINKS", "1")
        with caplog.at_level(logging.DEBUG, logger=email_service.logger.name):
            email_service.send_password_reset("educator@example.org", url)
        assert "DEV-TOKEN-VALUE" in caplog.text, (
            "with the opt-in set the link must be logged, or there is no way "
            "to complete a password reset without SMTP configured"
        )

    def test_the_recipient_address_never_reaches_the_log(self, monkeypatch, caplog):
        """Not in production, not in development, not with the opt-in set.

        Every branch used to log the full address; only the URL was withheld.
        """
        import services.email as email_service

        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        url = "https://example.org/reset?token=T"
        for env in ({}, {"PRODUCTION": "1"}, {"LOG_RESET_LINKS": "1"}):
            caplog.clear()
            monkeypatch.delenv("PRODUCTION", raising=False)
            monkeypatch.delenv("LOG_RESET_LINKS", raising=False)
            for k, v in env.items():
                monkeypatch.setenv(k, v)
            with caplog.at_level(logging.DEBUG, logger=email_service.logger.name):
                email_service.send_password_reset("educator@example.org", url)
            assert "educator@example.org" not in caplog.text, (
                "the full address reached the log with env=%r" % env
            )
            assert "@example.org" in caplog.text, (
                "the domain should survive — it is what makes a mail log useful"
            )

    def env_file_key_check(self):
        """Catches the Layoff fault: .env on MAIL_*, code on SMTP_*.

        Returns a skip reason, or None when the assertion has been made. Only
        key *names* ever reach an assertion: pytest rewrites asserts and prints
        the operands, so touching the parsed dict inside the assert expression
        would spill the mailbox password into the test log — and into whatever
        CI or terminal scrollback happens to keep it.

        Shaped as "return a reason" rather than calling pytest.skip so that this
        module stays free of pytest; the tool's wrapper does the skipping.
        """
        env_path = Path(self.PROJECT_ROOT) / ".env"
        if not env_path.is_file():
            return "no local .env (expected — this tool has none locally)"

        values = self.sender_module._parse_env_file(env_path)
        mail_keys = sorted(
            k for k in values if k.startswith(("SMTP_", "MAIL_", "EMAIL_"))
        )
        del values  # nothing holding secrets survives into the assertions below

        if not mail_keys:
            return ".env defines no mail settings at all"

        has_smtp_password = "SMTP_PASSWORD" in mail_keys
        has_legacy_password = "MAIL_PASSWORD" in mail_keys
        hint = (
            " It defines MAIL_PASSWORD — the Flask-era name that "
            "services/email.py never reads. That is the exact fault that "
            "silently stopped Layoff-Exercise sending."
            if has_legacy_password else ""
        )
        assert has_smtp_password, (
            "The .env defines mail settings (" + ", ".join(mail_keys) + ") but "
            "not SMTP_PASSWORD, so send_password_reset() fails closed and sends "
            "nothing." + hint
        )
        return None


class LiveDelivery(_EmailContract):
    """Really sends, on the server. The tool marks its subclass `live_email`."""

    def live_delivery_result(self):
        """(status, reason) when the caller should skip or fail, else None.

        Same shape as `env_file_key_check`: the pytest verbs stay in the tool.
        """
        status, reason = self.sender_module.live_sending_status()
        if status in ("skip", "error"):
            return status, reason

        results = self.sender_module.send_all()
        assert results, "no sample e-mails are defined"

        failures = [
            label + ": " + type(err).__name__ + ": " + str(err)
            for _key, label, err in results if err is not None
        ]
        assert not failures, (
            "live send failed for " + str(len(failures)) + " of " +
            str(len(results)) + " sample e-mail(s):\n  " + "\n  ".join(failures)
        )
        return None
