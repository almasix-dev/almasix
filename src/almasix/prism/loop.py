"""Blade-shaped ``loop`` variable for ``@foreach`` / ``@forelse``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class Loop:
    """Mirrors Laravel's ``$loop`` object inside ``@foreach``."""

    def __init__(self, iterable: Sequence[Any] | list[Any], parent: Loop | None = None) -> None:
        self._items = list(iterable)
        self._index = -1
        self.parent = parent

    def __iter__(self) -> Loop:
        return self

    def __next__(self) -> Any:
        self._index += 1
        if self._index >= len(self._items):
            raise StopIteration
        return self._items[self._index]

    @property
    def index(self) -> int:
        return self._index

    @property
    def iteration(self) -> int:
        return self._index + 1

    @property
    def remaining(self) -> int:
        return max(0, len(self._items) - self._index - 1)

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def first(self) -> bool:
        return self._index == 0

    @property
    def last(self) -> bool:
        return self._index == len(self._items) - 1

    @property
    def even(self) -> bool:
        return self.iteration % 2 == 0

    @property
    def odd(self) -> bool:
        return self.iteration % 2 == 1

    @property
    def depth(self) -> int:
        depth = 1
        parent = self.parent
        while parent is not None:
            depth += 1
            parent = parent.parent
        return depth
