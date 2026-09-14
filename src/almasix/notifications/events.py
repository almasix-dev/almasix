"""Notification lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NotificationSending:
    """Dispatched before a channel delivers. Listener may return False to abort."""

    notifiable: Any
    notification: Any
    channel: str


@dataclass
class NotificationSent:
    """Dispatched after a channel delivers successfully."""

    notifiable: Any
    notification: Any
    channel: str
    response: Any = None
