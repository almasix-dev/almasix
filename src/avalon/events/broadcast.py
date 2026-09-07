"""Broadcasting hook — full implementation lands in M26."""

from __future__ import annotations

from typing import Any, Protocol


class ShouldBroadcast(Protocol):
    """Marker protocol for events that should broadcast (M26).

    Avalon recognizes the marker today so apps can annotate events early.
    Dispatch still runs local listeners only until Broadcasting ships.
    """

    def broadcast_on(self) -> list[Any]:  # pragma: no cover - protocol stub
        """Return the channels the event should broadcast on."""
        ...
