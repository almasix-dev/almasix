"""Log mail transport — writes rendered messages to the logging stack."""

from __future__ import annotations

import json

from almasix.log.manager import get_logger
from almasix.mail.message import SentMessage


class LogTransport:
    """Log outgoing mail instead of delivering it."""

    def __init__(self, channel: str | None = None) -> None:
        self.channel = channel

    def send(self, message: SentMessage) -> None:
        payload = {
            "to": [item.address for item in message.to],
            "cc": [item.address for item in message.cc],
            "bcc": [item.address for item in message.bcc],
            "subject": message.subject,
            "from": message.from_address.address if message.from_address else None,
            "html": message.html,
            "text": message.text,
            "attachments": [item.name for item in message.attachments],
            "mailable": type(message.mailable).__name__,
        }
        get_logger(self.channel).info("Mail sent: %s", json.dumps(payload, default=str))
