"""Built mail message sent to transports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from almasix.mail.mailable import Address


@dataclass
class ResolvedAttachment:
    name: str
    data: bytes
    mime: str | None = None


@dataclass
class SentMessage:
    """Fully rendered message handed to a transport."""

    mailable: Any
    to: list[Address] = field(default_factory=list)
    cc: list[Address] = field(default_factory=list)
    bcc: list[Address] = field(default_factory=list)
    subject: str = ""
    html: str | None = None
    text: str | None = None
    from_address: Address | None = None
    reply_to: list[Address] = field(default_factory=list)
    attachments: list[ResolvedAttachment] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_recipient(self, address: str) -> bool:
        needle = address.lower()
        for group in (self.to, self.cc, self.bcc):
            if any(item.address.lower() == needle for item in group):
                return True
        return False
