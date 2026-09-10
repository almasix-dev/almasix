"""Built-in demo Counter (registered as ``counter``)."""

from __future__ import annotations

from almasix.conduit.component import Component


class Counter(Component):
    count = 0
    label = "world"

    def increment(self) -> None:
        self.count += 1

    def decrement(self) -> None:
        self.count -= 1

    def reset(self) -> None:
        self.count = 0

    def render(self) -> str:
        return "conduit::counter"
