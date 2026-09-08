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
