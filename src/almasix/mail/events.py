"""Mail lifecycle events (Laravel MessageSending / MessageSent)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from almasix.mail.message import SentMessage


@dataclass
class MessageSending:
    """Dispatched before a message is handed to a transport. Return False to abort."""

    message: SentMessage
    data: dict[str, Any] | None = None


@dataclass
class MessageSent:
    """Dispatched after a transport accepts the message."""

    message: SentMessage
    data: dict[str, Any] | None = None
