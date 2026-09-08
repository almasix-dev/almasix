"""Notifiable mixin — ``notify`` / ``notify_now`` / route helpers."""

from __future__ import annotations

from typing import Any


class Notifiable:
    """Mixin for models that receive notifications."""

    def route_notification_for(self, channel: str, notification: Any | None = None) -> Any:
        """Resolve the delivery address for ``channel`` (mail → email, …)."""
        del notification
        method = getattr(self, f"route_notification_for_{channel}", None)
        if callable(method):
            return method()
        if channel == "mail":
            return getattr(self, "email", None)
        if channel == "database":
            return self
        return None

    def route_notification_for_mail(self) -> str | None:
        return getattr(self, "email", None)

    async def notify(self, notification: Any) -> list[Any]:
        """Send via the notification sender (queues when marked)."""
        from almasix.notifications.sender import NotificationSender

        return await NotificationSender().send(self, notification)

    async def notify_now(self, notification: Any, channels: list[str] | None = None) -> list[Any]:
        """Force synchronous delivery (ignore ShouldQueue)."""
        from almasix.notifications.sender import NotificationSender

        return await NotificationSender().send_now(self, notification, channels=channels)

    async def unread_notifications(self) -> list[dict[str, Any]]:
        from almasix.notifications.database import DatabaseNotificationStore

        return await DatabaseNotificationStore().for_notifiable(self, unread_only=True)

    async def notifications(self) -> list[dict[str, Any]]:
        from almasix.notifications.database import DatabaseNotificationStore

        return await DatabaseNotificationStore().for_notifiable(self)

    async def mark_notification_as_read(self, notification_id: str) -> bool:
        from almasix.notifications.database import DatabaseNotificationStore

        return await DatabaseNotificationStore().mark_as_read(notification_id)
