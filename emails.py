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
    html = (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f4f5f7;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#f4f5f7;padding:24px 0;"><tr><td align="center">'
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        'style="width:100%;max-width:520px;background:#ffffff;border:1px solid #e3e6ea;border-radius:8px;overflow:hidden;">'
        '<tr><td style="background:#1e3a5f;padding:20px 28px;">'
        f'<span style="font-family:Georgia,\'Times New Roman\',serif;font-size:18px;font-weight:600;color:#ffffff;">{tool_name}</span>'
        '</td></tr>'
        '<tr><td style="padding:28px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:15px;line-height:1.55;color:#222222;">'
        '<p style="margin:0 0 16px;">Hello,</p>'
        f'<p style="margin:0 0 16px;">Someone requested a password reset for your <strong>{tool_name}</strong> account. '
        'Click the button below to choose a new password.</p>'
        '<p style="margin:0 0 24px;text-align:center;">'
        f'<a href="{reset_url}" style="display:inline-block;background:#1e3a5f;color:#ffffff;text-decoration:none;font-weight:600;padding:12px 28px;border-radius:6px;">Reset your password</a></p>'
        f'<p style="margin:0 0 16px;color:#555555;font-size:13px;">This link is valid for {hours} hours. '
        'If the button does not work, paste this URL into your browser:<br>'
        f'<a href="{reset_url}" style="color:#1e3a5f;word-break:break-all;">{reset_url}</a></p>'
        '<p style="margin:0;color:#555555;font-size:13px;">If you did not request this, you can safely ignore this email — your password will not change.</p>'
        '</td></tr>'
        '<tr><td style="padding:18px 28px;border-top:1px solid #e3e6ea;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:12px;color:#888888;text-align:center;">'
        'Part of <a href="https://phronon.org" style="color:#888888;">Phronon</a> — classroom simulations for practical judgment'
        '</td></tr></table></td></tr></table></body></html>'
    )
    return text, html


def build_password_reset_message(tool_name: str, sender: str, to_email: str,
                                 reset_url: str, hours: str = "2") -> MIMEMultipart:
    text, html = password_reset_bodies(tool_name, reset_url, hours)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{tool_name} — password reset"
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def send_password_reset(tool_name: str, default_from: str, to_email: str,
                        reset_url: str) -> None:
    """Send the branded reset email. No-op (logs the link) if SMTP unconfigured."""
    hours = os.getenv("RESET_TOKEN_HOURS", "2")
    if not os.getenv("SMTP_PASSWORD"):
        # A reset URL is a live credential — never log it in production
        # (security audit, finding 3). Locally the link is logged so the dev
        # can complete the flow without SMTP configured.
        if os.getenv("PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
            logger.error(
                "SMTP not configured (SMTP_PASSWORD unset) — password reset for "
                "%s could not be sent; reset link withheld from logs.", to_email,
            )
        else:
            logger.warning(
                "SMTP not configured (dev) — reset link for %s: %s",
                to_email, reset_url,
            )
        return
    sender = os.getenv("EMAIL_FROM") or os.getenv("SMTP_FROM") or default_from
    msg = build_password_reset_message(tool_name, sender, to_email, reset_url, hours)
    with smtplib.SMTP(
        os.getenv("SMTP_HOST", "smtp.ionos.de"),
        int(os.getenv("SMTP_PORT", "587")),
    ) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(os.getenv("SMTP_USER", sender), os.getenv("SMTP_PASSWORD", ""))
        smtp.sendmail(sender, [to_email], msg.as_string())
