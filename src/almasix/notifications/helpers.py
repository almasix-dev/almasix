"""Notification helpers and default config."""

from __future__ import annotations

from typing import Any

from almasix.notifications.sender import NotificationSender

_sender: NotificationSender | None = None


def set_sender(sender: NotificationSender | None) -> None:
    """Swap the sender every notification goes through (`Notification::fake()`)."""
    global _sender  # noqa: PLW0603 — one sender, like every other façade here
    _sender = sender


def get_sender() -> NotificationSender:
    return _sender if _sender is not None else NotificationSender()


async def notify(notifiable: Any, notification: Any) -> list[Any]:
    """Send a notification (respects ``ShouldQueue``)."""
    return await get_sender().send(notifiable, notification)


async def notify_now(
    notifiable: Any,
    notification: Any,
    channels: list[str] | None = None,
) -> list[Any]:
    """Send a notification immediately."""
    return await get_sender().send_now(notifiable, notification, channels=channels)


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
