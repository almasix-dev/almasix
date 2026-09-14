"""Notification sender — sync + queued delivery."""

from __future__ import annotations

from typing import Any

from almasix.notifications.channels import Channel, default_channel_map


class NotificationSender:
    """Resolve channels and deliver a notification."""

    def __init__(self, channels: dict[str, Any] | None = None) -> None:
        self.channels = channels or default_channel_map()

    async def send(self, notifiable: Any, notification: Any) -> list[Any]:
        _apply_preferred_locale(notifiable, notification)
        if getattr(notification, "should_queue", lambda: False)():
            if await self._try_queue(notifiable, notification):
                return [{"queued": True, "notification": type(notification).__name__}]
        return await self.send_now(notifiable, notification)

    async def send_now(
        self,
        notifiable: Any,
        notification: Any,
        *,
        channels: list[Any] | None = None,
    ) -> list[Any]:
        _apply_preferred_locale(notifiable, notification)
        locale_token = _push_notification_locale(notifiable, notification)
        try:
            names = channels if channels is not None else list(notification.via(notifiable))
            results: list[Any] = []
            for entry in names:
                channel_name, channel = self._resolve_channel(entry)
                if not _fire_sending(notifiable, notification, channel_name):
                    continue
                response = await channel.send(notifiable, notification)
                _fire_sent(notifiable, notification, channel_name, response)
                results.append(response)
            return results
        finally:
            _pop_locale(locale_token)

    def _resolve_channel(self, entry: Any) -> tuple[str, Channel]:
        if isinstance(entry, str):
            channel = self.channels.get(entry)
            if channel is None:
                raise KeyError(f"Notification channel [{entry}] is not configured.")
            return entry, channel
        if isinstance(entry, type):
            instance = entry()
            name = getattr(instance, "name", entry.__name__)
            return str(name), instance
        if hasattr(entry, "send"):
            name = getattr(entry, "name", type(entry).__name__)
            return str(name), entry
        raise TypeError(f"Unsupported notification channel: {entry!r}")

    async def _try_queue(self, notifiable: Any, notification: Any) -> bool:
        """Push to the queue. True = queued; False = caller should send now."""
        try:
            from almasix.notifications.jobs import SendQueuedNotification
            from almasix.queue.helpers import dispatch, get_manager

            manager = get_manager()
            connection_name = (
                getattr(notification, "connection", None) or manager.get_default_connection()
            )
            connection = manager.connection(connection_name)
            if type(connection).__name__ == "SyncQueue":
                return False

            notifiable_type = f"{type(notifiable).__module__}.{type(notifiable).__qualname__}"
            key_fn = getattr(notifiable, "get_key", None)
            notifiable_id = key_fn() if callable(key_fn) else getattr(notifiable, "id", None)
            notification_class = (
                f"{type(notification).__module__}.{type(notification).__qualname__}"
            )
            via_queues = {}
            if hasattr(notification, "via_queues"):
                via_queues = dict(notification.via_queues() or {})
            queue_name = (
                notification.queue_name() if hasattr(notification, "queue_name") else "default"
            )
            if via_queues:
                # Prefer first channel-specific queue when present
                queue_name = next(iter(via_queues.values()), queue_name)
            job = SendQueuedNotification(
                notifiable_type=notifiable_type,
                notifiable_id=notifiable_id,
                notification_class=notification_class,
                notification_data=dict(getattr(notification, "__dict__", {})),
                queue_name=queue_name,
            )
            delay = float(getattr(notification, "delay", 0) or 0)
            if delay:
                job.delay = delay  # type: ignore[attr-defined]
            if getattr(notification, "connection", None):
                job.connection = notification.connection  # type: ignore[attr-defined]
            await dispatch(job)
            return True
        except Exception:
            return False


def _apply_preferred_locale(notifiable: Any, notification: Any) -> None:
    if getattr(notification, "locale", None):
        return
    preferred = None
    method = getattr(notifiable, "preferred_locale", None)
    if callable(method):
        preferred = method()
    if preferred:
        notification.locale = preferred


def _push_notification_locale(notifiable: Any, notification: Any) -> Any:
    locale = getattr(notification, "locale", None)
    if not locale:
        method = getattr(notifiable, "preferred_locale", None)
        if callable(method):
            locale = method()
    if not locale:
        return None
    from almasix.translation.locale import get_locale, set_locale

    previous = get_locale()
    set_locale(locale)
    return previous


def _pop_locale(previous: Any) -> None:
    if previous is None:
        return
    from almasix.translation.locale import set_locale

    set_locale(previous)


def _fire_sending(notifiable: Any, notification: Any, channel: str) -> bool:
    try:
        from almasix.events.helpers import get_dispatcher
        from almasix.notifications.events import NotificationSending

        result = get_dispatcher().dispatch(
            NotificationSending(
                notifiable=notifiable,
                notification=notification,
                channel=channel,
            ),
            halt=True,
        )
        if result is False:
            return False
    except Exception:
        pass
    return True


def _fire_sent(notifiable: Any, notification: Any, channel: str, response: Any) -> None:
    try:
        from almasix.events.helpers import get_dispatcher
        from almasix.notifications.events import NotificationSent

        get_dispatcher().dispatch(
            NotificationSent(
                notifiable=notifiable,
                notification=notification,
                channel=channel,
                response=response,
            )
        )
    except Exception:
        pass
