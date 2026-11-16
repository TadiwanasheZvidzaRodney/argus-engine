"""Email dispatcher for DevOps alert notifications and repeated escalations."""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from argus_core.logging import get_logger

DEFAULT_DEVOPS_EMAIL = "devops@zimworx.com"


def send_ops_email(
    *,
    to_email: str = DEFAULT_DEVOPS_EMAIL,
    subject: str,
    text_content: str,
    html_content: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int | None = None,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    smtp_use_tls: bool | None = None,
    email_from: str | None = None,
) -> tuple[bool, str | None]:
    """Send an operational alert email via SMTP (Mailpit in local dev, SES in prod)."""
    from argus_core.settings import get_settings

    settings = get_settings()
    host = smtp_host or settings.smtp_host
    port = smtp_port or settings.smtp_port
    user = smtp_user or settings.smtp_user
    password = smtp_password or settings.smtp_password
    use_tls = smtp_use_tls if smtp_use_tls is not None else settings.smtp_use_tls
    sender = email_from or settings.email_from

    log = get_logger("ops.mailer")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain"))
    if html_content:
        msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=5) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.sendmail(msg["From"], [to_email], msg.as_string())
        log.info("ops.email.sent", to_email=to_email, subject=subject, host=host, port=port)
        return True, None
    except Exception as exc:
        err_msg = str(exc)
        log.warning("ops.email.failed", to_email=to_email, error=err_msg, host=host, port=port)
        return False, err_msg
