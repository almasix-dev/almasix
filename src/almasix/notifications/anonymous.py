"""On-demand / anonymous notifiable (Laravel AnonymousNotifiable)."""

from __future__ import annotations

from typing import Any


class AnonymousNotifiable:
    """Route notifications without a persisted model."""

    def __init__(self) -> None:
        self.routes: dict[str, Any] = {}

    def route(self, channel: str, route: Any) -> AnonymousNotifiable:
        self.routes[channel] = route
        return self

    def route_notification_for(self, channel: str, notification: Any | None = None) -> Any:
        del notification
        return self.routes.get(channel)

    async def notify(self, notification: Any) -> list[Any]:
        from almasix.notifications.sender import NotificationSender

        return await NotificationSender().send(self, notification)

    async def notify_now(self, notification: Any, channels: list[str] | None = None) -> list[Any]:
        from almasix.notifications.sender import NotificationSender

        return await NotificationSender().send_now(self, notification, channels=channels)
