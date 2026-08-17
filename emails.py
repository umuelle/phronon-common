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

#: How long a confirm-your-new-address link lives, in hours. Defined HERE, where
#: the mail that states it is written, and imported by `account.py` for the
#: signature age limit — so the sentence in the mail and the limit the server
#: enforces cannot disagree. Matches the password-reset window.
EMAIL_CHANGE_HOURS = 2


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
    sender = _sender_address(default_from)
    msg = build_password_reset_message(tool_name, sender, to_email, reset_url,
                                       hours, subject_prefix)
    _smtp_send(sender, to_email, msg)


# ── transport, shared by every sender below ─────────────────────────────────

def _sender_address(default_from: str) -> str:
    return os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM") or default_from


def _smtp_send(sender: str, to_email: str, msg: MIMEMultipart) -> None:
    """The one SMTP conversation in the fleet.

    Extracted from `send_password_reset` unchanged (17 August 2026) so the mails
    added since do not each grow their own copy of the host/port/STARTTLS
    handling — the drift that `recipient_domain` above is a monument to.
    """
    with smtplib.SMTP(
        os.getenv("SMTP_HOST", "smtp.ionos.de"),
        int(os.getenv("SMTP_PORT", "587")),
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(os.getenv("SMTP_USER", sender), os.getenv("SMTP_PASSWORD", ""))
        smtp.sendmail(sender, [to_email], msg.as_string())


def _unsendable(what: str, to_email: str, link: str = "") -> None:
    """Log an unsent mail the way `send_password_reset` does, and for its reasons.

    `link`, when given, is a live credential: it is withheld from the journal
    unless LOG_RESET_LINKS is explicitly on, and the address is never written in
    full. The variable keeps its name deliberately — one switch for "log the
    links while developing", not one per mail type.
    """
    where = recipient_domain(to_email)
    if link and os.getenv("LOG_RESET_LINKS", "").strip() in ("1", "true", "yes"):
        logger.warning("SMTP not configured — %s link for %s: %s "
                       "(LOG_RESET_LINKS is on; never set it in production)",
                       what, where, link)
    elif os.getenv("PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
        logger.error("SMTP not configured (SMTP_PASSWORD unset) — %s for %s could "
                     "not be sent%s.", what, where,
                     "; link withheld from logs" if link else "")
    else:
        logger.warning("SMTP not configured — %s for %s was not sent.%s", what, where,
                       " Set LOG_RESET_LINKS=1 to log the link while developing."
                       if link else "")


def _multipart(subject: str, sender: str, to_email: str, text: str, html: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


# ── account self-service mails (Manage account, 17 August 2026) ─────────────
# Three mails, and each one exists because the change it reports can otherwise
# be made silently by whoever is holding the session:
#
#   confirm  → to the NEW address. The change does not happen until this comes
#              back, which is what stops a typo becoming a permanent lockout and
#              a borrowed session becoming a takeover.
#   notice   → to the OLD address, at the moment the change is REQUESTED rather
#              than applied. The real owner hears about it while the link is
#              still unused and there is still something they can do.
#   2fa reset→ to the account whose second factor an administrator cleared. An
#              admin resetting somebody's 2FA is legitimate and routine; it is
#              also exactly what taking over an account looks like, so it is
#              never something the account holder learns only by noticing.

def email_change_confirm_bodies(tool_name: str, confirm_url: str, hours: str = "2"):
    text = (
        "Hello,\n\n"
        f"This address was given as the new sign-in address for a {tool_name} account.\n\n"
        f"Open the link below to confirm it (valid for {hours} hours):\n\n"
        f"{confirm_url}\n\n"
        "Until you do, the account keeps its current address and nothing changes.\n\n"
        "If you were not expecting this, you can ignore this mail — without this "
        "link the address cannot be changed.\n\n"
        f"— {tool_name}\n"
        "Part of Phronon · https://phronon.org"
    )
    html = branded_html(tool_name, (
        '<p style="margin:0 0 16px;">Hello,</p>'
        f'<p style="margin:0 0 16px;">This address was given as the new sign-in address '
        f'for a <strong>{tool_name}</strong> account. Confirm it below.</p>'
        '<p style="margin:0 0 24px;text-align:center;">'
        f'<a href="{confirm_url}" style="display:inline-block;background:#0F1B2D;color:#ffffff;'
        'text-decoration:none;font-weight:600;padding:12px 28px;border-radius:6px;">'
        'Confirm this address</a></p>'
        f'<p style="margin:0 0 16px;color:#555555;font-size:13px;">This link is valid for {hours} hours. '
        'If the button does not work, paste this URL into your browser:<br>'
        f'<a href="{confirm_url}" style="color:#0F1B2D;word-break:break-all;">{confirm_url}</a></p>'
        '<p style="margin:0;color:#555555;font-size:13px;">Until then the account keeps its '
        'current address. If you were not expecting this, ignore this mail — without this link '
        'the address cannot be changed.</p>'
    ))
    return text, html


def send_email_change_confirm(tool_name: str, default_from: str, to_email: str,
                              confirm_url: str, subject_prefix: str = "") -> None:
    """Send the confirm-your-new-address link. No-op (logs) without SMTP."""
    hours = str(EMAIL_CHANGE_HOURS)
    if not os.getenv("SMTP_PASSWORD"):
        _unsendable("e-mail address confirmation", to_email, confirm_url)
        return
    sender = _sender_address(default_from)
    text, html = email_change_confirm_bodies(tool_name, confirm_url, hours)
    _smtp_send(sender, to_email, _multipart(
        f"{subject_prefix}{tool_name} — confirm your new e-mail address",
        sender, to_email, text, html))


def email_change_notice_bodies(tool_name: str, new_email: str):
    text = (
        "Hello,\n\n"
        f"Somebody asked to change the sign-in address of your {tool_name} account "
        f"to:\n\n    {new_email}\n\n"
        "Nothing has changed yet. The new address has to be confirmed from a link "
        "sent to it before it replaces this one.\n\n"
        "If that was you, there is nothing to do here.\n\n"
        "If it was NOT you, somebody is signed in to your account: change your "
        "password now, and switch on two-factor login while you are there.\n\n"
        f"— {tool_name}\n"
        "Part of Phronon · https://phronon.org"
    )
    html = branded_html(tool_name, (
        '<p style="margin:0 0 16px;">Hello,</p>'
        f'<p style="margin:0 0 16px;">Somebody asked to change the sign-in address of your '
        f'<strong>{tool_name}</strong> account to:</p>'
        f'<p style="margin:0 0 16px;padding:12px 16px;background:#f4f5f7;border-radius:6px;'
        f'word-break:break-all;"><strong>{new_email}</strong></p>'
        '<p style="margin:0 0 16px;">Nothing has changed yet — the new address has to be '
        'confirmed from a link sent to it before it replaces this one.</p>'
        '<p style="margin:0 0 16px;color:#555555;font-size:13px;">If that was you, there is '
        'nothing to do here.</p>'
        '<p style="margin:0;color:#555555;font-size:13px;"><strong>If it was not you</strong>, '
        'somebody is signed in to your account: change your password now, and switch on '
        'two-factor login while you are there.</p>'
    ))
    return text, html


def send_email_change_notice(tool_name: str, default_from: str, to_email: str,
                             new_email: str, subject_prefix: str = "") -> None:
    """Tell the CURRENT address that a change was requested. No link inside."""
    if not os.getenv("SMTP_PASSWORD"):
        _unsendable("e-mail address change notice", to_email)
        return
    sender = _sender_address(default_from)
    text, html = email_change_notice_bodies(tool_name, new_email)
    _smtp_send(sender, to_email, _multipart(
        f"{subject_prefix}{tool_name} — a change of e-mail address was requested",
        sender, to_email, text, html))


def two_factor_reset_bodies(tool_name: str, account_url: str):
    text = (
        "Hello,\n\n"
        f"An administrator has reset two-factor login on your {tool_name} account.\n\n"
        "Your next sign-in will ask for your password only. Your old authenticator "
        "entry and your old recovery codes no longer work — delete them.\n\n"
        "You can set two-factor login up again here:\n\n"
        f"{account_url}\n\n"
        "If you did not ask for this, tell your administrator: it means somebody "
        "else can now sign in with your password alone.\n\n"
        f"— {tool_name}\n"
        "Part of Phronon · https://phronon.org"
    )
    html = branded_html(tool_name, (
        '<p style="margin:0 0 16px;">Hello,</p>'
        f'<p style="margin:0 0 16px;">An administrator has reset two-factor login on your '
        f'<strong>{tool_name}</strong> account.</p>'
        '<p style="margin:0 0 16px;">Your next sign-in will ask for your password only. Your '
        'old authenticator entry and your old recovery codes no longer work — delete them.</p>'
        '<p style="margin:0 0 24px;text-align:center;">'
        f'<a href="{account_url}" style="display:inline-block;background:#0F1B2D;color:#ffffff;'
        'text-decoration:none;font-weight:600;padding:12px 28px;border-radius:6px;">'
        'Set it up again</a></p>'
        '<p style="margin:0;color:#555555;font-size:13px;">If you did not ask for this, tell your '
        'administrator: it means somebody else can now sign in with your password alone.</p>'
    ))
    return text, html


def send_two_factor_reset_notice(tool_name: str, default_from: str, to_email: str,
                                 account_url: str, subject_prefix: str = "") -> None:
    """Tell an account that an administrator cleared its second factor.

    `account_url` is a plain page address behind the login, not a credential —
    it is logged with the rest of the line when SMTP is missing.
    """
    if not os.getenv("SMTP_PASSWORD"):
        _unsendable("two-factor reset notice", to_email)
        return
    sender = _sender_address(default_from)
    text, html = two_factor_reset_bodies(tool_name, account_url)
    _smtp_send(sender, to_email, _multipart(
        f"{subject_prefix}{tool_name} — two-factor login was reset",
        sender, to_email, text, html))
