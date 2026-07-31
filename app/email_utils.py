"""
Minimal pluggable email sending.

If SMTP_HOST is configured (.env), sends real email via stdlib smtplib.
Otherwise (the default today — no SMTP server is set up for this project
yet), logs the message so a developer can still complete the flow locally;
in debug mode it's also flashed to the page so the reset link is clickable
without needing a mail server at all.
"""

import os
import smtplib
from email.mime.text import MIMEText

from flask import current_app, flash


def send_email(to_address, subject, body):
    smtp_host = os.getenv('SMTP_HOST')

    if not smtp_host:
        current_app.logger.info(f"[email stub] To: {to_address} | Subject: {subject}\n{body}")
        if current_app.debug:
            flash(f"(Dev mode, no SMTP configured) {body}", "info")
        return

    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    smtp_user = os.getenv('SMTP_USER')
    smtp_password = os.getenv('SMTP_PASSWORD')
    from_address = os.getenv('SMTP_FROM', smtp_user or 'no-reply@triumphantag.com')

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = to_address

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        if smtp_user and smtp_password:
            server.login(smtp_user, smtp_password)
        server.sendmail(from_address, [to_address], msg.as_string())
