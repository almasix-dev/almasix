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
        from almasix.notifications.mail_message import MailMessage

        message = notification.to_mail(notifiable)
        route = notifiable.route_notification_for("mail", notification)
        if isinstance(message, MailMessage):
            message = message.to_mailable()
        if isinstance(message, Mailable):
            preferred = _preferred_locale(notifiable)
            if preferred and not getattr(message, "locale", None):
                message.set_locale(preferred)
            notif_locale = getattr(notification, "locale", None)
            if notif_locale and not getattr(message, "locale", None):
                message.set_locale(notif_locale)
            mailer_name = getattr(message, "mailer_name", None)
            mailer = Mail.mailer(mailer_name)
            pending = mailer.to(route) if route else mailer.to()
            return pending.send(message)
        if isinstance(message, dict):
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
        raise TypeError("to_mail() must return a Mailable, MailMessage, or dict")


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
    """Broadcast the notification to the notifiable's own private channel."""

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


class VonageChannel:
    """SMS via Vonage (Nexmo) HTTP API."""

    name = "vonage"

    async def send(self, notifiable: Any, notification: Any) -> Any:
        from almasix.client import Http
        from almasix.notifications.messages_builders import VonageMessage

        message = notification.to_vonage(notifiable)
        if isinstance(message, VonageMessage):
            payload = message.to_payload()
        elif isinstance(message, dict):
            payload = dict(message)
        else:
            payload = {"text": str(message)}
        to = notifiable.route_notification_for("vonage", notification) or notifiable.route_notification_for(
            "sms", notification
        )
        if not to:
            raise ValueError("No Vonage route for notifiable")
        svc = _services("vonage")
        payload.setdefault("from", svc.get("sms_from") or svc.get("from"))
        payload["to"] = to
        key = svc.get("key") or ""
        secret = svc.get("secret") or ""
        response = (
            Http.with_basic_auth(str(key), str(secret))
            .accept_json()
            .post("https://rest.nexmo.com/sms/json", payload)
        )
        if hasattr(response, "successful") and not response.successful():
            raise RuntimeError(f"Vonage send failed: {getattr(response, 'status', '?')}")
        return payload


class SlackChannel:
    """Slack incoming webhook / chat.postMessage."""

    name = "slack"

    async def send(self, notifiable: Any, notification: Any) -> Any:
        from almasix.client import Http
        from almasix.notifications.messages_builders import SlackMessage

        message = notification.to_slack(notifiable)
        if isinstance(message, SlackMessage):
            payload = message.to_payload()
        elif isinstance(message, dict):
            payload = dict(message)
        else:
            payload = {"text": str(message)}
        route = notifiable.route_notification_for("slack", notification)
        svc = _services("slack")
        notifications_cfg = (svc.get("notifications") or {}) if isinstance(svc, dict) else {}
        token = notifications_cfg.get("bot_user_oauth_token") or svc.get("token")
        default_channel = notifications_cfg.get("channel") or svc.get("channel")
        if isinstance(route, str) and route.startswith("https://"):
            response = Http.accept_json().post(route, payload)
        else:
            channel = route or payload.get("channel") or default_channel
            if channel:
                payload["channel"] = channel
            response = (
                Http.with_token(str(token or ""))
                .accept_json()
                .post("https://slack.com/api/chat.postMessage", payload)
            )
        if hasattr(response, "successful") and not response.successful():
            raise RuntimeError(f"Slack send failed: {getattr(response, 'status', '?')}")
        return payload


def _services(key: str) -> dict[str, Any]:
    try:
        from almasix.config import config

        section = config(f"services.{key}") or {}
        return dict(section) if isinstance(section, dict) else {}
    except Exception:
        return {}


def _preferred_locale(notifiable: Any) -> str | None:
    from almasix.notifications.notification import HasLocalePreference

    if isinstance(notifiable, HasLocalePreference) or hasattr(notifiable, "preferred_locale"):
        method = getattr(notifiable, "preferred_locale", None)
        if callable(method):
            return method()
    return None


def default_channel_map() -> dict[str, Channel]:
    return {
        "mail": MailChannel(),
        "database": DatabaseChannel(),
        "log": LogChannel(),
        "broadcast": BroadcastChannel(),
        "array": ArrayChannel(),
        "vonage": VonageChannel(),
        "slack": SlackChannel(),
    }
