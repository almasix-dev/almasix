"""Paginators — JSON-serializable, Laravel-shaped."""

from __future__ import annotations

import math
from typing import Any

from almasix.orm.collection import Collection


class Paginator:
    """Length-aware paginator (`paginate`)."""

    def __init__(
        self,
        items: Collection[Any],
        total: int,
        per_page: int,
        current_page: int,
    ) -> None:
        self.items = items
        self.total = total
        self.per_page = max(int(per_page), 1)
        self.current_page = max(int(current_page), 1)
        self.last_page = max(math.ceil(total / self.per_page), 1) if total else 1

    def __iter__(self) -> Any:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    @property
    def from_(self) -> int | None:
        if not len(self.items):
            return None
        return (self.current_page - 1) * self.per_page + 1

    @property
    def to(self) -> int | None:
        if not len(self.items):
            return None
        return (self.current_page - 1) * self.per_page + len(self.items)

    def has_more_pages(self) -> bool:
        return self.current_page < self.last_page

    def on_first_page(self) -> bool:
        return self.current_page <= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.items.to_dict(),
            "current_page": self.current_page,
            "per_page": self.per_page,
            "total": self.total,
            "last_page": self.last_page,
            "from": self.from_,
            "to": self.to,
        }


class SimplePaginator:
    """Cursor-light paginator (`simple_paginate`) — knows only "is there more"."""

    def __init__(self, items: Collection[Any], per_page: int, current_page: int, has_more: bool):
        self.items = items
        self.per_page = max(int(per_page), 1)
        self.current_page = max(int(current_page), 1)
        self._has_more = has_more

    def __iter__(self) -> Any:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def has_more_pages(self) -> bool:
        return self._has_more

    def on_first_page(self) -> bool:
        return self.current_page <= 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.items.to_dict(),
            "current_page": self.current_page,
            "per_page": self.per_page,
            "has_more": self._has_more,
        }
