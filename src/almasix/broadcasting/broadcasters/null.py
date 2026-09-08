"""The broadcaster that does nothing — the off switch."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster


class NullBroadcaster(Broadcaster):
    """Accepts every broadcast and forgets it.

    Useful in tests and in environments where the websocket half is not
    running: the application still fires its events, and nothing goes out.
    """

    driver = "null"

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        return None
