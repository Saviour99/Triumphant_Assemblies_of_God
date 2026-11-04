"""
Transactional email (password resets, church-inbox notifications).

Provider is chosen per send, from config/.env:

  1. RESEND_API_KEY set  -> Resend REST API (app/resend_client.py).
  2. else SMTP_HOST set  -> stdlib smtplib (legacy path, kept as fallback).
  3. else                -> not sent. Only recipient + subject are logged;
                            in development (debug, not testing) the plain-
                            text body is also printed to the console so a
                            developer can click a reset link locally.

Callers get a bool back and must not change what they show the user based
on it (no account enumeration). Message bodies (which may contain reset
tokens) are never flashed and never written to the production log.

Adding another provider = one more branch in send_email(); callers don't
change.
"""

import hashlib
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr

from flask import current_app, render_template, url_for

from app import resend_client
from app.security import site_base_url

DEFAULT_FROM_NAME = 'Triumphant Assemblies of God'


# Keys an admin can set in the dashboard (app/integrations.py).
_INTEGRATION_KEYS = {'RESEND_API_KEY', 'MAIL_FROM', 'MAIL_REPLY_TO', 'MAIL_NOTIFY_TO'}


def _cfg(key, default=''):
    """Settings are read at call time. Integration keys go through the
    shared resolver (admin-saved > config > env); SMTP_* stay config/env."""
    if key in _INTEGRATION_KEYS:
        return resend_client.get_setting(key, default)
    val = current_app.config.get(key)
    if val is None or val == '':
        val = os.getenv(key, default)
    return (val or '').strip() if isinstance(val, str) else val


def _one_line(value):
    """Strip CR/LF so user-supplied text can't inject headers."""
    return ' '.join(str(value or '').splitlines()).strip()


def provider():
    """'resend', 'smtp' or None (not configured)."""
    if _cfg('RESEND_API_KEY'):
        return 'resend'
    if _cfg('SMTP_HOST'):
        return 'smtp'
    return None


def _from_address():
    return _cfg('MAIL_FROM') or _cfg('SMTP_FROM') or _cfg('SMTP_USER')


def idempotency_key(*parts):
    """Stable key for one logical send (e.g. a specific reset token), so
    a duplicate submit of the same thing is de-duplicated by Resend."""
    raw = '|'.join(str(p) for p in parts)
    return 'tag-' + hashlib.sha256(raw.encode('utf-8')).hexdigest()[:48]


def send_email(to_address, subject, body, html=None, reply_to=None, tags=None,
               idempotency_key=None):
    """Send one email. `body` is the plain-text part (always sent); `html`
    the optional HTML part. Returns True only if the provider accepted it.
    Never raises for delivery problems."""
    subject = _one_line(subject)
    to_address = _one_line(to_address)
    reply_to = _one_line(reply_to) or _cfg('MAIL_REPLY_TO') or None
    which = provider()

    if which is None:
        current_app.logger.warning(
            f"[email stub] no email provider configured (RESEND_API_KEY / SMTP_HOST); "
            f"not sent. To: {to_address} | Subject: {subject}"
        )
        if current_app.debug and not current_app.testing:
            # Development console only — app.logger in debug mode writes to
            # stderr; the rotating log file is only attached when not debug.
            current_app.logger.debug(f"[email stub body — dev console only]\n{body}")
        return False

    from_address = _from_address()
    if not from_address:
        current_app.logger.error(
            f"send_email: MAIL_FROM is not set; not sent. To: {to_address} | Subject: {subject}"
        )
        return False

    if which == 'resend':
        try:
            email_id = resend_client.send_email(
                from_address, to_address, subject, html=html, text=body,
                reply_to=reply_to, tags=tags,
                idempotency_key=idempotency_key or f'tag-{uuid.uuid4().hex}',
            )
        except resend_client.ResendError as e:
            current_app.logger.error(
                f"send_email via Resend failed To: {to_address} | Subject: {subject} | "
                f"status={e.status} {e.name}: {e.message}"
            )
            return False
        current_app.logger.info(f"send_email via Resend ok id={email_id} To: {to_address} | Subject: {subject}")
        return True

    return _send_smtp(from_address, to_address, subject, body, html, reply_to)


def _send_smtp(from_address, to_address, subject, body, html, reply_to):
    smtp_host = _cfg('SMTP_HOST')
    smtp_port = int(_cfg('SMTP_PORT') or '587')
    smtp_user = _cfg('SMTP_USER')
    smtp_password = _cfg('SMTP_PASSWORD')

    if html:
        msg = MIMEMultipart('alternative')
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        msg.attach(MIMEText(html, 'html', 'utf-8'))
    else:
        msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = to_address
    if reply_to:
        msg['Reply-To'] = reply_to
    envelope_from = parseaddr(from_address)[1] or from_address

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.sendmail(envelope_from, [to_address], msg.as_string())
    except (smtplib.SMTPException, OSError) as e:
        # Don't 500 the request (or reveal whether the address exists) —
        # log the failure without the body.
        current_app.logger.error(
            f"send_email via SMTP failed To: {to_address} | Subject: {subject} | {type(e).__name__}"
        )
        return False
    return True


# ------------------------------------------------------------- rendering

def render_transactional(subject, heading, paragraphs, cta_label='', cta_url='',
                         note='', preheader='', details=None):
    """Branded HTML + plain-text bodies for a transactional email.

    paragraphs: list of plain strings (autoescaped in the template).
    details: optional list of (label, value) rows (e.g. a contact message).
    note: small print under the button (expiry / "ignore this" text).
    Returns (html, text)."""
    base = site_base_url()
    logo_path = url_for('static', filename='img/logo2.png')
    html = render_template(
        'email/transactional.html',
        subject=subject, heading=heading, paragraphs=paragraphs,
        cta_label=cta_label, cta_url=cta_url, note=note,
        preheader=preheader, details=details or [],
        logo_url=(base + logo_path) if base else '',
        site_url=base, year=datetime.now(timezone.utc).year,
    )
    lines = [heading, '']
    for p in paragraphs:
        lines += [p, '']
    for label, value in (details or []):
        lines.append(f'{label}: {value}')
    if details:
        lines.append('')
    if cta_label and cta_url:
        lines += [f'{cta_label}: {cta_url}', '']
    if note:
        lines += [note, '']
    lines += ['--', DEFAULT_FROM_NAME, 'Dansoman, Accra, Ghana']
    if base:
        lines.append(base)
    return html, '\n'.join(lines)


def send_password_reset(to_address, reset_url, minutes, audience='member', key_parts=()):
    """Branded password-reset email for admins or members. Returns bool;
    callers must show the same generic message either way."""
    if audience == 'admin':
        subject = 'Reset your TAG admin password'
        intro = ('We received a request to reset the password for your '
                 'Triumphant Assemblies of God admin dashboard account.')
        ignore = ("If you didn't request this, you can ignore this email (your password "
                  "won't change), but please let the site developer know.")
    else:
        subject = 'Reset your Triumphant Assemblies of God password'
        intro = ('We received a request to reset the password for your '
                 'Triumphant Assemblies of God member account.')
        ignore = ("If you didn't request this, you can safely ignore this email. "
                  "Your password won't change.")
    html, text = render_transactional(
        subject=subject,
        heading='Reset your password',
        paragraphs=[intro, 'Click the button below to choose a new password.'],
        cta_label='Reset password',
        cta_url=reset_url,
        note=f'This link expires in {minutes} minutes and can only be used once. {ignore}',
        preheader=f'Your password reset link (valid for {minutes} minutes).',
    )
    return send_email(
        to_address, subject, text, html=html,
        tags=[{'name': 'category', 'value': f'password_reset_{audience}'}],
        idempotency_key=idempotency_key('pwreset', audience, *key_parts) if key_parts else None,
    )


def notify_church(subject, heading, details, reply_to=None, category='notification'):
    """Best-effort alert to the church inbox (MAIL_NOTIFY_TO). Does nothing
    if unset; never raises, so a form submission can't fail because of
    email."""
    try:
        to_address = _cfg('MAIL_NOTIFY_TO')
        if not to_address:
            return False
        html, text = render_transactional(
            subject=subject, heading=heading,
            paragraphs=['A new submission arrived on the church website.'],
            details=details,
            note='Reply to this email to respond directly to the sender.' if reply_to else '',
            preheader=heading,
        )
        return send_email(to_address, subject, text, html=html, reply_to=reply_to,
                          tags=[{'name': 'category', 'value': category}])
    except Exception as e:  # noqa: BLE001 — must never break the caller
        current_app.logger.error(f"notify_church failed: {type(e).__name__}")
        return False
