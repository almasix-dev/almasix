"""Notification channels."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Channel(Protocol):
    async def send(self, notifiable: Any, notification: Any) -> Any: ...


class MailChannel:
    """Deliver via ``almasix.mail``."""

    name = "mail"

    async def send(self, notifiable: Any, notification: Any) -> Any:
        from almasix.mail import Mail, Mailable

        message = notification.to_mail(notifiable)
        route = notifiable.route_notification_for("mail", notification)
        if isinstance(message, Mailable):
            pending = Mail.to(route) if route else Mail.mailer()
            return pending.send(message)
        if isinstance(message, dict):
            # Lightweight dict payload → ad-hoc mailable
            from almasix.mail.mailable import Content, Envelope

            class _Inline(Mailable):
                def envelope(self) -> Envelope:
                    return Envelope(subject=str(message.get("subject") or "Notification"))

                def content(self) -> Content:
                    return Content(
                        html=message.get("html"),
                        text=message.get("text") or message.get("body"),
                    )

            pending = Mail.to(route) if route else Mail.mailer()
            return pending.send(_Inline())
        raise TypeError("to_mail() must return a Mailable or dict")


class DatabaseChannel:
    """Persist to the ``notifications`` table."""

    name = "database"

    async def send(self, notifiable: Any, notification: Any) -> Any:
        from almasix.notifications.database import DatabaseNotificationStore

        data = notification.to_database(notifiable)
        return await DatabaseNotificationStore().create(notifiable, notification, data)


class LogChannel:
    """Write notification payload to the logger."""

    name = "log"

    async def send(self, notifiable: Any, notification: Any) -> Any:
        payload = notification.to_array(notifiable)
        try:
            from almasix.log import log

            log().info(
                "notification %s notifiable=%s payload=%s",
                type(notification).__name__,
                type(notifiable).__name__,
                payload,
            )
        except Exception:
            print(f"[notification] {type(notification).__name__}: {payload}")
        return payload


class BroadcastChannel:
    """Broadcast the notification to the notifiable's own private channel.

    The channel is the one the notifiable names — `route_notification_for
    ("broadcast")` when it defines one, otherwise its model channel — so a
    user hears their own notifications and nobody else's.
    """

    name = "broadcast"

    async def send(self, notifiable: Any, notification: Any) -> Any:
        from almasix.broadcasting.channels import PrivateChannel, to_channels
        from almasix.broadcasting.helpers import get_broadcast_manager

        payload = self._payload(notifiable, notification)
        route = notifiable.route_notification_for("broadcast", notification)
        channels = to_channels(route) if route is not None else [PrivateChannel(notifiable)]

        await get_broadcast_manager().event(
            channels,
            self._event_name(notification),
            payload,
        )
        return payload

    def _payload(self, notifiable: Any, notification: Any) -> dict[str, Any]:
        """`to_broadcast()` if the notification has one, else `to_array()`.

        The id and type ride along either way, which is what a client needs
        to reconcile a live notification with the ones it already has.
        """
        builder = getattr(notification, "to_broadcast", None)
        data = builder(notifiable) if callable(builder) else notification.to_array(notifiable)
        message = dict(data) if isinstance(data, dict) else {"data": data}
        message.setdefault("id", getattr(notification, "id", None))
        message.setdefault("type", type(notification).__name__)
        return message

    def _event_name(self, notification: Any) -> str:
        alias = getattr(notification, "broadcast_as", None)
        if callable(alias):
            return str(alias())
        # Laravel's clients listen for the class that wraps a broadcast
        # notification; keeping the name means an Echo `.notification()`
        # handler needs no translating.
        return "BroadcastNotificationCreated"


class ArrayChannel:
    """Collect notifications in memory (tests)."""

    name = "array"
    messages: list[dict[str, Any]] = []

    async def send(self, notifiable: Any, notification: Any) -> Any:
        entry = {
            "notification": type(notification).__name__,
            "notifiable": type(notifiable).__name__,
            "payload": notification.to_array(notifiable),
        }
        ArrayChannel.messages.append(entry)
        return entry

    @classmethod
    def clear(cls) -> None:
        cls.messages.clear()
