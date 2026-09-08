"""Notification helpers and default config."""

from __future__ import annotations

from typing import Any

from almasix.notifications.sender import NotificationSender


async def notify(notifiable: Any, notification: Any) -> list[Any]:
    """Send a notification (respects ``ShouldQueue``)."""
    return await NotificationSender().send(notifiable, notification)


async def notify_now(
    notifiable: Any,
    notification: Any,
    channels: list[str] | None = None,
) -> list[Any]:
    """Send a notification immediately."""
    return await NotificationSender().send_now(notifiable, notification, channels=channels)


def default_notifications_config() -> dict[str, Any]:
    return {
        "default": "mail",
        "channels": {
            "mail": {"driver": "mail"},
            "database": {"driver": "database"},
            "log": {"driver": "log"},
            "array": {"driver": "array"},
        },
    }
