"""Array mail transport — captures sent and queued messages for tests."""

from __future__ import annotations

from almasix.mail.message import SentMessage


class ArrayTransport:
    """In-memory transport for assertions in tests."""

    sent_messages: list[SentMessage]
    queued_messages: list[SentMessage]

    def __init__(self) -> None:
        self.sent_messages = []
        self.queued_messages = []

    def send(self, message: SentMessage) -> None:
        self.sent_messages.append(message)

    def queue(self, message: SentMessage) -> None:
        self.queued_messages.append(message)

    def flush(self) -> None:
        self.sent_messages.clear()
        self.queued_messages.clear()
