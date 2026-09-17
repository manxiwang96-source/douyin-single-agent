from __future__ import annotations

import smtplib
from email.header import Header
from email.mime.text import MIMEText
from typing import Any, Protocol

from app.config import Settings


class EmailClient(Protocol):
    def send(self, *, subject: str, body: str, to: str | None = None) -> dict[str, Any]:
        ...


class SmtpEmailClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sends: list[dict[str, Any]] = []

    def send(self, *, subject: str, body: str, to: str | None = None) -> dict[str, Any]:
        to_addr = to or self.settings.smtp_to
        from_addr = self.settings.smtp_from or self.settings.smtp_user
        if not to_addr or not from_addr:
            raise RuntimeError("SMTP_TO and SMTP_FROM/SMTP_USER are required to send email")
        message = MIMEText(body or "", "plain", "utf-8")
        message["Subject"] = Header(subject or "", "utf-8")
        message["From"] = from_addr
        message["To"] = to_addr
        if self.settings.smtp_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                self.settings.smtp_host,
                int(self.settings.smtp_port),
                timeout=30,
            )
        else:
            client = smtplib.SMTP(
                self.settings.smtp_host,
                int(self.settings.smtp_port),
                timeout=30,
            )
            client.starttls()
        try:
            client.login(self.settings.smtp_user, self.settings.smtp_password)
            client.sendmail(from_addr, [to_addr], message.as_string())
        finally:
            client.quit()
        record = {"ok": True, "subject": subject, "body": body, "to": to_addr}
        self.sends.append(record)
        return record