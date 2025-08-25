"""Simple SMTP email adapter.

Uses built-in smtplib for portability. For production you might
swap with a provider SDK (e.g., SendGrid, SES). The adapter returns
an opaque message_id (here we synthesize one) for timeline correlation.
"""
from __future__ import annotations
import os
import smtplib
import ssl
import email.utils
from email.message import EmailMessage
import time
import hashlib


class EmailAdapter:
    def __init__(self):
        self.host = os.getenv("EMAIL_SMTP_HOST")
        self.port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        self.username = os.getenv("EMAIL_USERNAME")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.use_tls = os.getenv("EMAIL_USE_TLS", "1") != "0"
        self.from_address = os.getenv("EMAIL_FROM", self.username or "no-reply@example.com")

    def configured(self) -> bool:
        return all([self.host, self.port, self.username, self.password])

    def send(self, to: list[str], subject: str, body: str, cc: list[str] | None = None, bcc: list[str] | None = None) -> str:
        if not self.configured():
            raise RuntimeError("Email adapter not configured (missing env vars)")
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_address
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        all_recipients = list(to) + (cc or []) + (bcc or [])
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg.set_content(body)

        context = ssl.create_default_context()
        if self.use_tls:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.starttls(context=context)
                server.login(self.username, self.password)
                server.send_message(msg, from_addr=self.from_address, to_addrs=all_recipients)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=10) as server:
                server.login(self.username, self.password)
                server.send_message(msg, from_addr=self.from_address, to_addrs=all_recipients)

        # Pseudo message id for tracking
        raw = f"{subject}-{time.time()}-{','.join(all_recipients)}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]
