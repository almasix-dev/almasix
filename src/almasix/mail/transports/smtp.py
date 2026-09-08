"""SMTP mail transport — stdlib smtplib baseline."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from almasix.mail.message import SentMessage


class SmtpTransport:
    """Deliver mail via SMTP using :mod:`smtplib`."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 2525,
        username: str | None = None,
        password: str | None = None,
        encryption: str | None = None,
        timeout: float | None = None,
        local_domain: str | None = None,
        client: Any | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.encryption = (encryption or "").lower() or None
        self.timeout = timeout
        self.local_domain = local_domain
        self._client = client

    def send(self, message: SentMessage) -> None:
        email = self._build_email(message)
        client = self._client or self._connect()
        own_client = self._client is None
        try:
            recipients = [item.address for item in message.to + message.cc + message.bcc]
            client.send_message(email, to_addrs=recipients or None)
        finally:
            if own_client:
                client.quit()

    def _connect(self) -> smtplib.SMTP:
        if self.encryption == "ssl":
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                self.host,
                self.port,
                timeout=self.timeout,
                local_hostname=self.local_domain,
            )
        else:
            client = smtplib.SMTP(
                self.host,
                self.port,
                timeout=self.timeout,
                local_hostname=self.local_domain,
            )
            if self.encryption == "tls":
                client.starttls()
        if self.username:
            client.login(self.username, self.password or "")
        return client

    @staticmethod
    def _build_email(message: SentMessage) -> EmailMessage:
        email = EmailMessage()
        if message.from_address is not None:
            if message.from_address.name:
                email["From"] = (
                    message.from_address.name,
                    message.from_address.address,
                )
            else:
                email["From"] = message.from_address.address
        email["Subject"] = message.subject
        if message.to:
            email["To"] = ", ".join(item.address for item in message.to)
        if message.cc:
            email["Cc"] = ", ".join(item.address for item in message.cc)
        if message.reply_to:
            email["Reply-To"] = ", ".join(item.address for item in message.reply_to)

        if message.text and message.html:
            email.set_content(message.text)
            email.add_alternative(message.html, subtype="html")
        elif message.html:
            email.set_content(message.html, subtype="html")
        elif message.text:
            email.set_content(message.text)
        else:
            email.set_content("")

        for attachment in message.attachments:
            maintype, _, subtype = (attachment.mime or "application/octet-stream").partition("/")
            email.add_attachment(
                attachment.data,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=attachment.name,
            )
        return email
