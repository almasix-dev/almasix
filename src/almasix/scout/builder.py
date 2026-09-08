"""The search query — what `Model.search("...")` hands back.

A search builder is not a SQL builder. It carries a phrase, a handful of
equality filters an engine can honour, an ordering, and a limit; everything
else — eager loads, extra constraints — belongs on the database query that
turns matching keys back into models, which is what `query_using()` is for.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import Any

from almasix.support.lazy import AsyncLazyCollection

#: The flag Scout writes on an indexed record when it is soft deleted.
SOFT_DELETED = "__soft_deleted"


class SearchBuilder:
    """A pending search against one model's index."""

    def __init__(
        self,
        model: Any,
        query: str = "",
        callback: Callable[..., Any] | None = None,
        *,
        soft_delete: bool = False,
    ) -> None:
        self.model = model
        #: The phrase being searched for; engines read this.
        self.query = str(query or "")
        #: An engine-specific hook, given the raw client and the query.
        self.callback = callback
        self.index: str | None = None
        self.wheres: dict[str, Any] = {}
        self.where_ins: dict[str, list[Any]] = {}
        self.where_not_ins: dict[str, list[Any]] = {}
        self.orders: list[dict[str, str]] = []
        self.limit: int | None = None
        #: Applied to the database query that hydrates the results.
        self.query_callback: Callable[[Any], Any] | None = None
        #: Passed straight through to the engine (Laravel's `options()`).
        self.search_options: dict[str, Any] = {}

        if soft_delete:
            self.wheres[SOFT_DELETED] = 0

    # --- shaping the search -------------------------------------------------

    def within(self, index: str) -> SearchBuilder:
        """Search a named index instead of the model's own."""
        self.index = index
        return self

    def where(self, field: str, value: Any) -> SearchBuilder:
        """An equality filter the engine applies before we see the results."""
        self.wheres[field] = value
        return self

    def where_in(self, field: str, values: Iterable[Any]) -> SearchBuilder:
        self.where_ins[field] = list(values)
        return self

    def where_not_in(self, field: str, values: Iterable[Any]) -> SearchBuilder:
        self.where_not_ins[field] = list(values)
        return self

    def order_by(self, column: str, direction: str = "asc") -> SearchBuilder:
        self.orders.append(
            {"column": column, "direction": "desc" if str(direction).lower() == "desc" else "asc"}
        )
        return self

    def latest(self, column: str | None = None) -> SearchBuilder:
        return self.order_by(column or self._timestamp_column(), "desc")

    def oldest(self, column: str | None = None) -> SearchBuilder:
        return self.order_by(column or self._timestamp_column(), "asc")

    def take(self, limit: int) -> SearchBuilder:
        self.limit = int(limit)
        return self

    def options(self, values: Mapping[str, Any] | None = None, **extra: Any) -> SearchBuilder:
        """Engine-specific search parameters, merged with what is already set."""
        self.search_options.update({**dict(values or {}), **extra})
        return self

    def query_using(self, callback: Callable[[Any], Any]) -> SearchBuilder:
        """Shape the database query that turns matching keys back into models.

        Laravel spells this `->query()`; a Python attribute and a method
        cannot share the name, and `builder.query` is the phrase.
        """
        self.query_callback = callback
        return self

    def with_trashed(self) -> SearchBuilder:
        """Include soft deleted records (`scout.soft_delete` must be on)."""
        self.wheres.pop(SOFT_DELETED, None)
        return self

    def only_trashed(self) -> SearchBuilder:
        """Only soft deleted records (`scout.soft_delete` must be on)."""
        self.wheres[SOFT_DELETED] = 1
        return self

    # --- conditionals -------------------------------------------------------

    def when(
        self,
        condition: Any,
        callback: Callable[[SearchBuilder, Any], Any],
        default: Callable[[SearchBuilder, Any], Any] | None = None,
    ) -> SearchBuilder:
        value = condition() if callable(condition) else condition
        if value:
            return callback(self, value) or self
        if default is not None:
            return default(self, value) or self
        return self

    def unless(
        self,
        condition: Any,
        callback: Callable[[SearchBuilder, Any], Any],
        default: Callable[[SearchBuilder, Any], Any] | None = None,
    ) -> SearchBuilder:
        value = condition() if callable(condition) else condition
        return self.when(not value, lambda builder, _: callback(builder, value), default)

    def tap(self, callback: Callable[[SearchBuilder], Any]) -> SearchBuilder:
        callback(self)
        return self

    # --- running it ---------------------------------------------------------

    def engine(self) -> Any:
        """The engine this model searches with."""
        return self.model.searchable_using()

    async def raw(self) -> Any:
        """The engine's own answer, before it is turned into models."""
        return await self.engine().search(self)

    async def keys(self) -> list[Any]:
        """The matching keys, in the order the engine ranked them."""
        return await self.engine().keys(self)

    async def get(self) -> Any:
        """The matching models, in the order the engine ranked them."""
        return await self.engine().get(self)

    async def first(self) -> Any:
        results = await self.take(1).get()
        return results.first()

    async def count(self) -> int:
        """How many records match — Laravel's `getTotalCount`."""
        return self.engine().total_count(await self.raw())

    def cursor(self) -> AsyncLazyCollection:
        """Stream the results one model at a time."""
        return AsyncLazyCollection(functools.partial(self._stream))

    async def _stream(self) -> AsyncIterator[Any]:
        for model in await self.get():
            yield model

    async def paginate(self, per_page: int | None = None, page: int = 1) -> Any:
        """A length-aware page of results."""
        from almasix.orm.pagination import Paginator

        size = self._per_page(per_page)
        results = await self.engine().paginate(self, size, page)
        engine = self.engine()
        models = await engine.map(self, results, self.model)
        return Paginator(models, engine.total_count(results), size, page)

    async def simple_paginate(self, per_page: int | None = None, page: int = 1) -> Any:
        """A page that knows only whether there is another one after it."""
        from almasix.orm.pagination import SimplePaginator

        size = self._per_page(per_page)
        engine = self.engine()
        results = await engine.paginate(self, size, page)
        models = await engine.map(self, results, self.model)
        has_more = size * max(int(page), 1) < engine.total_count(results)
        return SimplePaginator(models, size, page, has_more)

    async def paginate_raw(self, per_page: int | None = None, page: int = 1) -> Any:
        """The engine's own answer for a page, unmapped."""
        return await self.engine().paginate(self, self._per_page(per_page), page)

    async def simple_paginate_raw(self, per_page: int | None = None, page: int = 1) -> Any:
        return await self.paginate_raw(per_page, page)

    # --- the query behind the results --------------------------------------

    def model_query(self, keys: Sequence[Any]) -> Any:
        """The database query that fetches the models the engine matched."""
        model = self.model
        query = model.query_scout_models_by_ids(self, list(keys))
        if self.query_callback is not None:
            query = self.query_callback(query) or query
        return query

    def _per_page(self, per_page: int | None) -> int:
        return int(per_page or getattr(self.model, "per_page", 15))

    def _timestamp_column(self) -> str:
        return str(getattr(self.model, "created_at", None) or "created_at")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SearchBuilder({self.model.__name__} {self.query!r})"
