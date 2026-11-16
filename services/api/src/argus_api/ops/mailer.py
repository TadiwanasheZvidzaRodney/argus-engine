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
    smtp_host: str = "127.0.0.1",
    smtp_port: int = 1025,
) -> bool:
    """Send an operational alert email via SMTP (Mailpit in local dev, SES in prod)."""
    log = get_logger("ops.mailer")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "Argus Engine Alert <alerts@argus.engine>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain"))
    if html_content:
        msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=5) as server:
            server.sendmail(msg["From"], [to_email], msg.as_string())
        log.info("ops.email.sent", to_email=to_email, subject=subject)
        return True
    except Exception as exc:
        log.warning("ops.email.failed", to_email=to_email, error=str(exc))
        return False
