"""Blade-shaped view stacks for ``@push`` / ``@stack``."""

from __future__ import annotations

from collections import defaultdict


class StackBag:
    """Mutable stack bag shared across a layout + child render."""

    def __init__(self) -> None:
        self._stacks: dict[str, list[str]] = defaultdict(list)
        self._once: set[str] = set()

    def push(self, name: str, content: str, *, prepend: bool = False) -> None:
        if prepend:
            self._stacks[name].insert(0, content)
        else:
            self._stacks[name].append(content)

    def render(self, name: str) -> str:
        return "".join(self._stacks.get(name, []))

    def once(self, key: str) -> bool:
        """Return True the first time ``key`` is seen in this render."""
        if key in self._once:
            return False
        self._once.add(key)
        return True
