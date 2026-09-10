"""Pagination mixin for Conduit components (Livewire ``WithPagination``)."""

from __future__ import annotations

from typing import Any


class WithPagination:
    """Add ``page`` + ``paginate()`` helpers to a Conduit component.

    Expects the host class to be a :class:`~almasix.conduit.Component` (duck-typed).
    """

    page: int = 1
    per_page: int = 15

    def updating_page(self) -> None:
        """Hook when page changes (override in subclasses)."""

    def reset_page(self) -> None:
        self.page = 1  # type: ignore[misc]

    def paginate(self, query: Any, *, per_page: int | None = None) -> Any:
        """Paginate an Articulate / query-like object that exposes ``paginate``."""
        size = per_page if per_page is not None else int(getattr(self, "per_page", 15))
        page = max(1, int(getattr(self, "page", 1) or 1))
        if hasattr(query, "paginate"):
            return query.paginate(size, page=page)
        # Fallback: slice a sequence
        items = list(query)
        start = (page - 1) * size
        chunk = items[start : start + size]

        class _Simple:
            def __init__(self) -> None:
                self.items = chunk
                self.total = len(items)
                self.per_page = size
                self.current_page = page
                self.last_page = max(1, (len(items) + size - 1) // size)

        return _Simple()
