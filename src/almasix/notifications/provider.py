"""Notifications service provider."""

from __future__ import annotations

from almasix.providers.provider import ServiceProvider


class NotificationServiceProvider(ServiceProvider):
    """Registers notification defaults and password-reset delivery."""

    def register(self) -> None:
        app = self.app
        if not app.config.get("notifications"):
            from almasix.notifications.helpers import default_notifications_config

            app.config.set("notifications", default_notifications_config())

    def boot(self) -> None:
        self._wire_password_reset_delivery()

    def _wire_password_reset_delivery(self) -> None:
        """Default password-reset send path → ResetPasswordNotification (mail)."""
        try:
            from almasix.auth.passwords import get_password_manager
            from almasix.notifications.messages import ResetPasswordNotification
        except Exception:
            return

        manager = get_password_manager()
        if getattr(manager, "_send_callback", None) is not None:
            return

        async def send_reset(user: object, token: str) -> None:
            notification = ResetPasswordNotification(token)
            notify = getattr(user, "notify", None)
            if callable(notify):
                result = notify(notification)
                if hasattr(result, "__await__"):
                    await result  # type: ignore[misc]
                return
            from almasix.notifications.helpers import notify as send

            await send(user, notification)

        manager.create_url_using(send_reset)
