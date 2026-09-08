"""Almasix's own websocket broadcaster — no third party involved."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster
from almasix.broadcasting.sockets import SocketHub, get_hub


class WebsocketBroadcaster(Broadcaster):
    """Delivers straight to the connections held by this process.

    Good for a single worker, a dev server, or a dedicated socket process
    fed over Redis. Run more than one worker without Redis in front and each
    worker only reaches its own browsers.
    """

    driver = "websocket"

    def __init__(
        self,
        name: str = "",
        config: Mapping[str, Any] | None = None,
        hub: SocketHub | None = None,
    ) -> None:
        super().__init__(name, config)
        self._hub = hub

    @property
    def hub(self) -> SocketHub:
        return self._hub if self._hub is not None else get_hub()

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        await self.hub.publish(channels, event, dict(payload), socket=socket)

    def auth_secret(self) -> str | None:
        """Falls back to the application key, which every install already has."""
        secret = self.config.get("secret")
        if secret:
            return str(secret)
        from almasix.framework.helpers import current_application

        application = current_application()
        if application is None:
            return None
        return str(application.config.get("app.key") or "") or None
