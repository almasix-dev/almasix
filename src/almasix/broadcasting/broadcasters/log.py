"""The broadcaster that writes to the log — how you see what would have gone out."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster


class LogBroadcaster(Broadcaster):
    """Records every broadcast in the application log, and sends nothing.

    This is the default connection, so a new application can fire broadcast
    events before it has decided how they will reach a browser.
    """

    driver = "log"

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        line = "Broadcasting [{event}] on channels [{channels}] with payload:\n{payload}".format(
            event=event,
            channels=", ".join(channels),
            payload=json.dumps(dict(payload), indent=2, default=str),
        )
        if socket:
            line = f"{line}\n(excluding socket {socket})"
        try:
            from almasix.log import log

            log().info(line)
        except Exception:
            print(f"[broadcast] {line}")
