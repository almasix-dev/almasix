"""Notification sender — sync + queued delivery."""

from __future__ import annotations

from typing import Any

from almasix.notifications.channels import (
    ArrayChannel,
    DatabaseChannel,
    LogChannel,
    MailChannel,
)


class NotificationSender:
    """Resolve channels and deliver a notification."""

    def __init__(self, channels: dict[str, Any] | None = None) -> None:
        self.channels = channels or {
            "mail": MailChannel(),
            "database": DatabaseChannel(),
            "log": LogChannel(),
            "array": ArrayChannel(),
        }

    async def send(self, notifiable: Any, notification: Any) -> list[Any]:
        if getattr(notification, "should_queue", lambda: False)():
            if await self._try_queue(notifiable, notification):
                return [{"queued": True, "notification": type(notification).__name__}]
        return await self.send_now(notifiable, notification)

    async def send_now(
        self,
        notifiable: Any,
        notification: Any,
        *,
        channels: list[str] | None = None,
    ) -> list[Any]:
        names = channels or list(notification.via(notifiable))
        results: list[Any] = []
        for name in names:
            channel = self.channels.get(name)
            if channel is None:
                raise KeyError(f"Notification channel [{name}] is not configured.")
            results.append(await channel.send(notifiable, notification))
        return results

    async def _try_queue(self, notifiable: Any, notification: Any) -> bool:
        """Push to the queue. True = queued; False = caller should send now."""
        try:
            from almasix.notifications.jobs import SendQueuedNotification
            from almasix.queue.helpers import dispatch, get_manager
        except Exception:
            return False

        manager = get_manager()
        connection_name = manager.get_default_connection()
        connection = manager.connection(connection_name)
        # Sync driver runs in-process — deliver immediately.
        if type(connection).__name__ == "SyncQueue":
            return False

        notifiable_type = f"{type(notifiable).__module__}.{type(notifiable).__qualname__}"
        key_fn = getattr(notifiable, "get_key", None)
        notifiable_id = key_fn() if callable(key_fn) else getattr(notifiable, "id", None)
        notification_class = (
            f"{type(notification).__module__}.{type(notification).__qualname__}"
        )
        queue_name = (
            notification.queue_name() if hasattr(notification, "queue_name") else "default"
        )
        job = SendQueuedNotification(
            notifiable_type=notifiable_type,
            notifiable_id=notifiable_id,
            notification_class=notification_class,
            notification_data=dict(getattr(notification, "__dict__", {})),
            queue_name=queue_name,
        )
        try:
            await dispatch(job)
            return True
        except Exception:
            return False
