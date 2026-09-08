"""Broadcasting over Redis pub/sub.

Publishes the same JSON envelope Laravel Echo's Redis backends expect, so a
socket server (Laravel Echo Server, soketi, or Almasix's own relay) can sit in
front of the application and fan the message out to browsers.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster


class RedisBroadcaster(Broadcaster):
    """One Redis `publish` per channel, on `{prefix}{channel}`."""

    driver = "redis"

    def __init__(
        self,
        name: str = "",
        config: Mapping[str, Any] | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(name, config)
        self._client = client

    @property
    def prefix(self) -> str:
        return str(self.config.get("prefix") or "")

    def client(self) -> Any:
        """The Redis client, resolved from the manager the first time it is needed."""
        if self._client is None:
            from almasix.framework.helpers import current_application
            from almasix.redis.manager import RedisManager

            application = current_application()
            manager = (
                application.make(RedisManager) if application is not None else RedisManager()
            )
            self._client = manager.connection(self.config.get("connection"))
        return self._client

    def set_client(self, client: Any) -> None:
        self._client = client

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        body = dict(payload)
        if socket is not None:
            body.setdefault("socket", socket)
        client = self.client()
        for channel in channels:
            message = json.dumps(
                {"event": event, "data": body, "socket": socket},
                default=str,
            )
            result = client.publish(f"{self.prefix}{channel}", message)
            if hasattr(result, "__await__"):
                await result
