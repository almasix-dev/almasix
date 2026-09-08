"""Paginators — JSON-serializable, Laravel-shaped.

Three of them, as Laravel has three. :class:`Paginator` counts the rows and so
knows how many pages there are; :class:`SimplePaginator` only knows whether
there is another one; :class:`CursorPaginator` knows where it stopped, which
is the only one of the three that stays correct while rows are being inserted.

All three know the URL they were reached at, so they can write the links to
the pages either side of them.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any
from urllib.parse import urlencode

from almasix.orm.collection import Collection


def _current_path() -> str:
    """The path the paginator was reached at, when there is a request."""
    from almasix.http.request import get_request

    request = get_request()
    return request.path if request is not None else "/"


def _current_query() -> dict[str, Any]:
    from almasix.http.request import get_request

    request = get_request()
    return dict(request.query()) if request is not None else {}


def _resolve_page(page_name: str) -> int:
    """The page the request asked for, or the first one."""
    from almasix.http.request import get_request

    request = get_request()
    if request is None:
        return 1
    try:
        page = int(str(request.query(page_name, 1)))
    except (TypeError, ValueError):
        return 1
    return page if page >= 1 else 1


def resolve_page(page_name: str = "page", page: int | None = None) -> int:
    """``page`` when given, otherwise whatever the request asked for."""
    return max(int(page), 1) if page is not None else _resolve_page(page_name)


class Cursor:
    """Where a cursor-paginated page stopped, and which way it was going.

    Laravel encodes the same thing: the ordered columns of the row at the
    edge of the page, plus whether the cursor points forwards.
    """

    def __init__(self, parameters: Mapping[str, Any], points_to_next_items: bool = True) -> None:
        self.parameters = dict(parameters)
        self.points_to_next_items = points_to_next_items

    def parameter(self, name: str) -> Any:
        if name not in self.parameters:
            raise ValueError(f"Unable to find cursor parameter {name!r}.")
        return self.parameters[name]

    def encode(self) -> str:
        payload = {**self.parameters, "_pointsToNextItems": self.points_to_next_items}
        raw = json.dumps(payload, default=str).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @classmethod
    def from_encoded(cls, encoded: str | None) -> Cursor | None:
        """A cursor from the query string, or ``None`` if it is not one."""
        if not encoded:
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            payload = json.loads(base64.urlsafe_b64decode(padded))
        except (ValueError, binascii.Error):
            return None
        if not isinstance(payload, dict):
            return None
        forwards = bool(payload.pop("_pointsToNextItems", True))
        return cls(payload, forwards)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Cursor):
            return NotImplemented
        return (
            self.parameters == other.parameters
            and self.points_to_next_items == other.points_to_next_items
        )

    def __repr__(self) -> str:
        return f"<Cursor {self.parameters} forwards={self.points_to_next_items}>"


class AbstractPaginator:
    """What every paginator knows: its items, its page, and its own URL."""

    #: What ``links()`` renders with, when the application has not said otherwise.
    default_view = "pagination.tailwind"
    default_simple_view = "pagination.simple-tailwind"

    def __init__(
        self,
        items: Collection[Any],
        per_page: int,
        current_page: int,
        *,
        path: str | None = None,
        page_name: str = "page",
        query: Mapping[str, Any] | None = None,
        fragment: str | None = None,
    ) -> None:
        self.items = items
        self.per_page = max(int(per_page), 1)
        self.current_page = max(int(current_page), 1)
        self.path = (path if path is not None else _current_path()).rstrip("/") or "/"
        self.page_name = page_name
        self.query: dict[str, Any] = dict(query or {})
        self._fragment = fragment

    # --- the items ----------------------------------------------------------

    def __iter__(self) -> Iterator[Any]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def count(self) -> int:
        return len(self.items)

    def is_empty(self) -> bool:
        return not len(self.items)

    def is_not_empty(self) -> bool:
        return bool(len(self.items))

    def through(self, callback: Callable[[Any], Any]) -> Any:
        """Run each item through ``callback``, keeping the page around it."""
        self.items = Collection([callback(item) for item in self.items])
        return self

    # --- the URL ------------------------------------------------------------

    def with_path(self, path: str) -> Any:
        """Say what URL the pages live at — Laravel's ``setPath`` / ``withPath``."""
        self.path = path.rstrip("/") or "/"
        return self

    set_path = with_path

    def appends(self, key: str | Mapping[str, Any], value: Any = None) -> Any:
        """Add to the query string every page link carries."""
        if isinstance(key, Mapping):
            self.query.update(key)
        else:
            self.query[key] = value
        return self

    append = appends

    def with_query_string(self) -> Any:
        """Carry the request's own query string onto every link."""
        query = _current_query()
        query.pop(self.page_name, None)
        self.query.update(query)
        return self

    def fragment(self, fragment: str | None = None) -> Any:
        """The ``#anchor`` every link ends with, or the one it already has."""
        if fragment is None:
            return self._fragment
        self._fragment = fragment.lstrip("#")
        return self

    def url(self, page: int) -> str:
        """The URL of one page."""
        page = max(int(page), 1)
        return self._build_url({self.page_name: page})

    def _build_url(self, parameters: Mapping[str, Any]) -> str:
        query = {**self.query, **parameters}
        url = self.path
        if query:
            url += ("&" if "?" in self.path else "?") + urlencode(query, doseq=True)
        if self._fragment:
            url += f"#{self._fragment}"
        return url

    def previous_page_url(self) -> str | None:
        if self.current_page <= 1:
            return None
        return self.url(self.current_page - 1)

    def next_page_url(self) -> str | None:
        if not self.has_more_pages():
            return None
        return self.url(self.current_page + 1)

    def on_first_page(self) -> bool:
        return self.current_page <= 1

    def has_more_pages(self) -> bool:  # pragma: no cover - each paginator answers
        raise NotImplementedError

    def has_pages(self) -> bool:
        """Whether there is more than this one page."""
        return self.current_page != 1 or self.has_more_pages()

    def get_options(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "page_name": self.page_name,
            "query": dict(self.query),
            "fragment": self._fragment,
        }

    # --- rendering ----------------------------------------------------------

    def links(self, view: str | None = None, data: Mapping[str, Any] | None = None) -> str:
        """The page links as HTML, rendered through Prism."""
        return self.render(view, data)

    def render(self, view: str | None = None, data: Mapping[str, Any] | None = None) -> str:
        from almasix.prism.helpers import render

        return render(view or self.default_view, {"paginator": self, **dict(data or {})})

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), default=str, **kwargs)

    def to_dict(self) -> dict[str, Any]:  # pragma: no cover - each paginator answers
        raise NotImplementedError


class Paginator(AbstractPaginator):
    """Length-aware paginator (`paginate`) — it counted, so it knows the last page."""

    def __init__(
        self,
        items: Collection[Any],
        total: int,
        per_page: int,
        current_page: int,
        *,
        path: str | None = None,
        page_name: str = "page",
        query: Mapping[str, Any] | None = None,
        fragment: str | None = None,
    ) -> None:
        super().__init__(
            items,
            per_page,
            current_page,
            path=path,
            page_name=page_name,
            query=query,
            fragment=fragment,
        )
        self.total = total
        self.last_page = max(math.ceil(total / self.per_page), 1) if total else 1

    @property
    def from_(self) -> int | None:
        if not len(self.items):
            return None
        return (self.current_page - 1) * self.per_page + 1

    def first_item(self) -> int | None:
        return self.from_

    @property
    def to(self) -> int | None:
        if not len(self.items):
            return None
        return (self.current_page - 1) * self.per_page + len(self.items)

    def last_item(self) -> int | None:
        return self.to

    def has_more_pages(self) -> bool:
        return self.current_page < self.last_page

    def on_last_page(self) -> bool:
        return not self.has_more_pages()

    def first_page_url(self) -> str:
        return self.url(1)

    def last_page_url(self) -> str:
        return self.url(self.last_page)

    def get_url_range(self, start: int, end: int) -> dict[int, str]:
        """The URLs of a run of pages — what a numbered link bar is built from."""
        return {page: self.url(page) for page in range(start, end + 1)}

    def link_collection(self) -> list[dict[str, Any]]:
        """Previous, every page, and next — the shape Laravel's JSON uses."""
        links: list[dict[str, Any]] = [
            {
                "url": self.previous_page_url(),
                "label": "&laquo; Previous",
                "active": False,
            }
        ]
        for page in range(1, self.last_page + 1):
            links.append(
                {"url": self.url(page), "label": str(page), "active": page == self.current_page}
            )
        links.append({"url": self.next_page_url(), "label": "Next &raquo;", "active": False})
        return links

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_page": self.current_page,
            "data": self.items.to_dict(),
            "first_page_url": self.first_page_url(),
            "from": self.from_,
            "last_page": self.last_page,
            "last_page_url": self.last_page_url(),
            "links": self.link_collection(),
            "next_page_url": self.next_page_url(),
            "path": self.path,
            "per_page": self.per_page,
            "prev_page_url": self.previous_page_url(),
            "to": self.to,
            "total": self.total,
        }


class SimplePaginator(AbstractPaginator):
    """Cursor-light paginator (`simple_paginate`) — knows only "is there more"."""

    default_view = AbstractPaginator.default_simple_view

    def __init__(
        self,
        items: Collection[Any],
        per_page: int,
        current_page: int,
        has_more: bool,
        *,
        path: str | None = None,
        page_name: str = "page",
        query: Mapping[str, Any] | None = None,
        fragment: str | None = None,
    ) -> None:
        super().__init__(
            items,
            per_page,
            current_page,
            path=path,
            page_name=page_name,
            query=query,
            fragment=fragment,
        )
        self._has_more = has_more

    @property
    def from_(self) -> int | None:
        if not len(self.items):
            return None
        return (self.current_page - 1) * self.per_page + 1

    def first_item(self) -> int | None:
        return self.from_

    @property
    def to(self) -> int | None:
        if not len(self.items):
            return None
        return (self.current_page - 1) * self.per_page + len(self.items)

    def last_item(self) -> int | None:
        return self.to

    def has_more_pages(self) -> bool:
        return self._has_more

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_page": self.current_page,
            "data": self.items.to_dict(),
            "first_page_url": self.url(1),
            "from": self.from_,
            "next_page_url": self.next_page_url(),
            "path": self.path,
            "per_page": self.per_page,
            "prev_page_url": self.previous_page_url(),
            "to": self.to,
            # Kept from the paginator Almasix shipped before URLs were known.
            "has_more": self._has_more,
        }


class CursorPaginator(AbstractPaginator):
    """Cursor paginator (`cursor_paginate`) — a page defined by where the last one ended.

    Rows inserted while a reader pages through do not shift the window, which
    is the whole point of it; the cost is that there are no page numbers and
    no jumping about.
    """

    def __init__(
        self,
        items: Collection[Any],
        per_page: int,
        cursor: Cursor | None,
        has_more: bool,
        *,
        parameters: Sequence[str] = (),
        path: str | None = None,
        cursor_name: str = "cursor",
        query: Mapping[str, Any] | None = None,
        fragment: str | None = None,
    ) -> None:
        super().__init__(
            items,
            per_page,
            1,
            path=path,
            page_name=cursor_name,
            query=query,
            fragment=fragment,
        )
        self.cursor = cursor
        self.cursor_name = cursor_name
        self.parameters = list(parameters)
        self._has_more = has_more

    def has_more_pages(self) -> bool:
        return self._has_more if self._points_forward() else True

    def on_first_page(self) -> bool:
        return self.cursor is None or (not self.cursor.points_to_next_items and not self._has_more)

    def on_last_page(self) -> bool:
        return not self.has_more_pages()

    def _points_forward(self) -> bool:
        return self.cursor is None or self.cursor.points_to_next_items

    def _cursor_for(self, item: Any, forwards: bool) -> Cursor:
        return Cursor({name: _read(item, name) for name in self.parameters}, forwards)

    def next_cursor(self) -> Cursor | None:
        if not self.has_more_pages() or not len(self.items):
            return None
        return self._cursor_for(self.items[-1], True)

    def previous_cursor(self) -> Cursor | None:
        if self.on_first_page() or not len(self.items):
            return None
        return self._cursor_for(self.items[0], False)

    def next_page_url(self) -> str | None:
        cursor = self.next_cursor()
        return None if cursor is None else self._build_url({self.cursor_name: cursor.encode()})

    def previous_page_url(self) -> str | None:
        cursor = self.previous_cursor()
        return None if cursor is None else self._build_url({self.cursor_name: cursor.encode()})

    def url(self, cursor: Cursor | str | int | None) -> str:
        """The URL a cursor leads to — the page-number argument has no meaning here."""
        if cursor is None:
            return self._build_url({})
        encoded = cursor.encode() if isinstance(cursor, Cursor) else str(cursor)
        return self._build_url({self.cursor_name: encoded})

    def has_pages(self) -> bool:
        return not self.on_first_page() or self.has_more_pages()

    def to_dict(self) -> dict[str, Any]:
        next_cursor = self.next_cursor()
        previous_cursor = self.previous_cursor()
        return {
            "data": self.items.to_dict(),
            "path": self.path,
            "per_page": self.per_page,
            "next_cursor": next_cursor.encode() if next_cursor else None,
            "next_page_url": self.next_page_url(),
            "prev_cursor": previous_cursor.encode() if previous_cursor else None,
            "prev_page_url": self.previous_page_url(),
        }


def _read(item: Any, name: str) -> Any:
    """One ordered column's value, from a model or a plain row."""
    if isinstance(item, Mapping):
        return item.get(name)
    return getattr(item, name, None)


__all__ = [
    "AbstractPaginator",
    "Cursor",
    "CursorPaginator",
    "Paginator",
    "SimplePaginator",
    "resolve_page",
]
