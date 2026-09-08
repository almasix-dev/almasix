"""Mail transport protocol."""

from __future__ import annotations

from typing import Protocol

from almasix.mail.message import SentMessage


class Transport(Protocol):
    """Send a rendered message through a mail driver."""

    def send(self, message: SentMessage) -> None:
        """Deliver ``message`` synchronously."""
