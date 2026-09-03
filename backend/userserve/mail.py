"""SMTP email sending with support for multiple providers (QQ, Gmail).

Each provider has a built-in host/port/security preset, so only credentials are
taken from env vars (see config.py). send_email tries every configured provider
in turn until one succeeds. When none is configured (typical in development),
emails are logged to the console instead of being sent.

User-facing helpers (send_password_reset_email / send_verification_code_email)
dispatch the SMTP work to a background daemon thread so request handlers never
block on a slow QQ/Gmail server. SMTP routes are already rate-limited (see
userserve/routes.py), so the thread count stays bounded in practice.
"""

import smtplib
import threading
from email.message import EmailMessage

from flask import current_app

# Built-in SMTP presets for the supported providers.
SMTP_PROVIDERS = {
    'qq': {'host': 'smtp.qq.com', 'port': 465, 'use_ssl': True, 'use_tls': False},
    'gmail': {'host': 'smtp.gmail.com', 'port': 587, 'use_ssl': False, 'use_tls': True},
}

def _configured_accounts():
    """Return [(provider, username, password), ...] for every supported provider
    that has credentials configured, ordered by MAIL_PROVIDER_ORDER."""
    cfg = current_app.config
    accounts = []
    for provider in cfg.get('MAIL_PROVIDER_ORDER', []):
        username = cfg.get(f'MAIL_{provider.upper()}_USERNAME')
        password = cfg.get(f'MAIL_{provider.upper()}_PASSWORD')
        if provider in SMTP_PROVIDERS and username and password:
            accounts.append((provider, username, password))
    return accounts

def _send_via(provider, username, password, to, subject, body):
    """Send one message through a single provider. Raises on failure."""
    preset = SMTP_PROVIDERS[provider]
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = username
    message['To'] = to
    message.set_content(body)

    smtp_class = smtplib.SMTP_SSL if preset['use_ssl'] else smtplib.SMTP
    with smtp_class(preset['host'], preset['port'], timeout=10) as client:
        if preset['use_tls']:
            client.starttls()
        client.login(username, password)
        client.send_message(message)

def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via the first configured provider that succeeds. With no
    provider configured (or MAIL_SUPPRESS_SEND set), the email is logged."""
    accounts = _configured_accounts()

    # Dev fallback: nothing configured → log the message instead of sending.
    if not accounts or current_app.config.get('MAIL_SUPPRESS_SEND'):
        current_app.logger.info(f"[mail suppressed] to={to} subject={subject!r}\n{body}")
        return True

    for provider, username, password in accounts:
        try:
            _send_via(provider, username, password, to, subject, body)
            return True
        except Exception as e:
            current_app.logger.warning(f"Email send via {provider} failed: {e}")
    current_app.logger.error(f"All configured mail providers failed for {to}")
    return False

def _dispatch_async(to: str, subject: str, body: str) -> None:
    """Hand the send_email call off to a daemon thread, with app context
    preserved so config / logging work normally inside the worker."""
    app = current_app._get_current_object()
    def _run():
        with app.app_context():
            try:
                send_email(to, subject, body)
            except Exception as exc:
                app.logger.exception(f"async mail dispatch failed: {exc}")
    threading.Thread(target=_run, daemon=True).start()

def send_password_reset_email(user, reset_url: str) -> None:
    subject = "Reset your VNDB account password"
    body = (
        f"Hi {user.username},\n\n"
        f"We received a request to reset your password. Open the link below to "
        f"choose a new one:\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email — your "
        f"password won't change.\n"
    )
    _dispatch_async(user.email, subject, body)

def send_verification_code_email(email: str, code: str) -> None:
    subject = "Your VNDB sign-up verification code"
    body = (
        f"Your verification code is:\n\n"
        f"    {code}\n\n"
        f"Enter it on the sign-up form to finish creating your account. "
        f"The code expires in 10 minutes.\n\n"
        f"If you didn't request this, you can safely ignore this email.\n"
    )
    _dispatch_async(email, subject, body)
