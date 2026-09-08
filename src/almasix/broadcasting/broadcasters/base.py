"""What every broadcaster must be able to do."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any


class Broadcaster(ABC):
    """One way of getting an event onto a channel.

    Everything above this line — events, channels, authorization — is shared.
    A broadcaster only has to put a named payload on some channels, and say
    who it is when asked.
    """

    #: The driver name in `config/broadcasting.py`.
    driver = "broadcaster"

    def __init__(self, name: str = "", config: Mapping[str, Any] | None = None) -> None:
        self.name = name or self.driver
        self.config = dict(config or {})

    @abstractmethod
    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        """Send `payload` as `event` on every channel; skip the `socket` given.

        `socket` is the connection that caused the broadcast — the one
        `to_others()` means to leave out.
        """

    def auth_key(self) -> str:
        """The public half of the credential a client signs with."""
        return str(self.config.get("key") or "almasix")

    def auth_secret(self) -> str | None:
        """The secret this broadcaster signs authorization responses with."""
        secret = self.config.get("secret")
        return str(secret) if secret else None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name!r}>"
