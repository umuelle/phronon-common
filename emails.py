"""Shared transactional-email building — canonical Phronon design.

This is the source of truth for the password-reset email look/feel. Tools that
can import phronon_common should call `build_password_reset_message()` /
`send_password_reset()` here; tools that vendor their own services/email.py keep
the same markup (copy it from this module). Only the tool name / sender differ.

Harmonization O1 — branded HTML + plain-text multipart, June 14, 2026.
"""
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


def recipient_domain(address) -> str:
    """A log-safe stand-in for a recipient address: `"@domain"`, or a placeholder.

    ONE implementation, fleet-wide, since 16 August 2026. There were four —
    Controversy Generator, LSR, Whiteout and Moral Mirror each grew their own,
    the last of them written the same week with a comment saying "there is no
    shared helper for it, so it lives here". They had already diverged, and not
    harmlessly: three of the four returned `"@not-an-address"` for a string
    with no `@` in it, which logs the WHOLE thing — so a participant who
    mistyped their address had their raw input written to the journal in full,
    by the very helper that exists to stop exactly that. Three also left
    surrounding whitespace in. CG's was the strict one, and this is CG's, which
    is the rule when consolidating: promote the strictest copy, never the most
    convenient (harmonization wave 2, 29 July).

    WHY REDACT AT ALL. Participant addresses are personal data and journald
    retention on this host is open-ended relative to the tools' own rules, so
    an address logged here outlives the response it belongs to and the deletion
    promised for it — a log line quietly undoing a retention rule.

    WHY KEEP THE DOMAIN. It is what makes a mail log useful: it separates "the
    whole university's mail server is refusing us" from "one person mistyped
    their address", and it identifies nobody.
    """
    # str() before strip(): this is called from exception handlers and
    # background workers, where whatever went wrong may hand us something that
    # is not a string at all — and a raise HERE would replace the error being
    # reported with its own, losing the incident. The loose per-tool copies
    # coerced; the strict one did not, so consolidating on the strict one meant
    # taking its robustness gap with it.
    if not address:
        return "(no address)"
    address = str(address).strip()
    if "@" not in address:
        return "(no address)"
    domain = address.rsplit("@", 1)[-1]
    return "@" + domain if domain else "(no address)"


def branded_html(tool_name: str, inner_html: str, card_width: int = 520,
                 subtitle: str = "", footer_note: str = "") -> str:
    """Wrap `inner_html` in the fleet's e-mail shell: navy header carrying the
    tool's name, white card, Phronon footer.

    `tool_name` IS the header title — there is deliberately no separate `title`
    argument. The header is branding, and a per-mail heading there ("Your
    results are ready") is how nine tools drift into nine headers again; every
    template already puts its heading in the body, which is where it belongs.
    `subtitle` is the optional second line under it — a standing tagline, not a
    per-mail line: LSR's mails carry "Leadership Style Repertoire" (12 August
    2026, added so LSR could adopt this shell without losing its header).

    `footer_note` sits above the Phronon line and is for a tool's standing
    disclaimer. It exists because LSR's mails carry one that matters: "not a
    psychometric diagnosis or a basis for selection decisions." A shell without
    a slot for it would have quietly dropped that sentence during the
    conversion, which is the sort of thing a cosmetic change is not allowed to
    do. Pass it already localised — this module does no translation.

    ONE copy of this markup, for the reason the fleet keeps one of anything: a
    student in two courses gets mail from the same operator and it should look
    like it. The design started life inside password_reset_bodies() below and
    was hand-copied into Controversy Generator as a Jinja template on 12 August
    2026; that copy is gone and both now render from here (FL/CG-001).

    `tool_name` is the whole of the per-tool branding — the header text — which
    is why "shared shell" and "each project's own look" are not in tension.
    `card_width` widens the card for mails that carry a table; 520 suits prose.

    Inline styles and tables, not CSS: mail clients strip <style> blocks, and
    Outlook needs the table scaffolding.
    """
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f4f5f7;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f5f7;padding:24px 0;"><tr><td align="center">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="width:100%;max-width:{card_width}px;background:#ffffff;border:1px solid #e3e6ea;border-radius:8px;overflow:hidden;">'
        '<tr><td style="background:#0F1B2D;padding:20px 28px;">'
        f'<span style="font-family:Georgia,\'Times New Roman\',serif;font-size:18px;font-weight:600;color:#ffffff;">{tool_name}</span>'
        + (f'<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
           f'font-size:13px;color:#b4cde1;margin-top:6px;">{subtitle}</div>' if subtitle else '')
        + '</td></tr>'
        '<tr><td style="padding:28px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;color:#222222;">'
        f'{inner_html}'
        '</td></tr>'
        '<tr><td style="padding:18px 28px;border-top:1px solid #e3e6ea;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:12px;color:#888888;text-align:center;">'
        + (f'<div style="margin:0 0 10px;line-height:1.5;">{footer_note}</div>' if footer_note else '')
        + 'Part of <a href="https://phronon.org" style="color:#888888;">Phronon</a> — online tools for practical judgment'
        '</td></tr></table></td></tr></table></body></html>'
    )


def password_reset_bodies(tool_name: str, reset_url: str, hours: str = "2"):
    """Return (plain_text, html) for a branded password-reset email."""
    text = (
        "Hello,\n\n"
        f"Someone requested a password reset for your {tool_name} account.\n\n"
        f"Open the link below to choose a new password (valid for {hours} hours):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can safely ignore this email — "
        "your password will not change.\n\n"
        f"— {tool_name}\n"
        "Part of Phronon · https://phronon.org"
    )
    html = branded_html(tool_name, (
        '<p style="margin:0 0 16px;">Hello,</p>'
        f'<p style="margin:0 0 16px;">Someone requested a password reset for your <strong>{tool_name}</strong> account. '
        'Click the button below to choose a new password.</p>'
        '<p style="margin:0 0 24px;text-align:center;">'
        f'<a href="{reset_url}" style="display:inline-block;background:#0F1B2D;color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:6px;">Reset your password</a></p>'
        f'<p style="margin:0 0 16px;color:#555555;font-size:13px;">This link is valid for {hours} hours. '
        'If the button does not work, paste this URL into your browser:<br>'
        f'<a href="{reset_url}" style="color:#0F1B2D;word-break:break-all;">{reset_url}</a></p>'
        '<p style="margin:0;color:#555555;font-size:13px;">If you did not request this, you can safely ignore this email — your password will not change.</p>'
    ))
    return text, html


def build_password_reset_message(tool_name: str, sender: str, to_email: str,
                                 reset_url: str, hours: str = "2",
                                 subject_prefix: str = "") -> MIMEMultipart:
    # subject_prefix exists for the test samples ("[TEST] "), so a sample in
    # the inbox can never be mistaken for a real reset. Production callers
    # leave it empty.
    text, html = password_reset_bodies(tool_name, reset_url, hours)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{subject_prefix}{tool_name} — password reset"
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def send_password_reset(tool_name: str, default_from: str, to_email: str,
                        reset_url: str, subject_prefix: str = "") -> None:
    """Send the branded reset email. No-op (logs the link) if SMTP unconfigured."""
    hours = os.getenv("RESET_TOKEN_HOURS", "2")
    if not os.getenv("SMTP_PASSWORD"):
        # A reset URL is a live credential and an address is personal data, so
        # neither is logged by default ANYWHERE (external review, 16 August
        # 2026). This used to withhold the link in production but still log the
        # full address in both branches, and log the live link outright off
        # production — and "off production" is any box where PRODUCTION is
        # unset, which is a weaker guarantee than it looks.
        #
        # LOG_RESET_LINKS=1 is the deliberate, explicit way to get the link
        # while developing without SMTP. It is opt-in and named for what it
        # does, so switching it on is a decision someone made rather than a
        # default they inherited.
        where = recipient_domain(to_email)
        if os.getenv("LOG_RESET_LINKS", "").strip() in ("1", "true", "yes"):
            logger.warning(
                "SMTP not configured — reset link for %s: %s "
                "(LOG_RESET_LINKS is on; never set it in production)",
                where, reset_url,
            )
        elif os.getenv("PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
            logger.error(
                "SMTP not configured (SMTP_PASSWORD unset) — password reset for "
                "%s could not be sent; reset link withheld from logs.", where,
            )
        else:
            logger.warning(
                "SMTP not configured — password reset for %s was not sent. Set "
                "LOG_RESET_LINKS=1 to log the link while developing.", where,
            )
        return
    sender = os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM") or default_from
    msg = build_password_reset_message(tool_name, sender, to_email, reset_url,
                                       hours, subject_prefix)
    with smtplib.SMTP(
        os.getenv("SMTP_HOST", "smtp.ionos.de"),
        int(os.getenv("SMTP_PORT", "587")),
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(os.getenv("SMTP_USER", sender), os.getenv("SMTP_PASSWORD", ""))
        smtp.sendmail(sender, [to_email], msg.as_string())
