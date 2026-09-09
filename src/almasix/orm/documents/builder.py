"""The document query builder — Articulate's fluent surface over a store.

Everything a `QueryBuilder` can honestly do against a collection is here,
spelled the same way. Everything it cannot — joins, `group_by`, raw SQL —
raises rather than pretending.
"""

from __future__ import annotations

import functools
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import Any

from almasix.orm.builder import ModelNotFoundError
from almasix.orm.collection import Collection
from almasix.orm.documents.filters import Condition, Order, Query, UnsupportedQueryError
from almasix.orm.pagination import Paginator, SimplePaginator
from almasix.support.lazy import AsyncLazyCollection


class _Missing:
    """Sentinel: `where("f", None)` must mean "equals None", not "no value"."""


#: Distinguishes "no operator given" from a real `None`.
_MISSING = _Missing()


#: SQL-only methods, and what to say when someone reaches for one.
SQL_ONLY = {
    "join": "a document store has no joins; keep the key and load the other side",
    "left_join": "a document store has no joins",
    "right_join": "a document store has no joins",
    "cross_join": "a document store has no joins",
    "group_by": "group in an aggregation pipeline with raw_aggregate()",
    "having": "filter after grouping in raw_aggregate()",
    "having_raw": "filter after grouping in raw_aggregate()",
    "select_raw": "there is no SQL to write here",
    "where_column": "compare two fields with raw_aggregate() and $expr",
    "union": "a document store has no UNION",
}


class DocumentBuilder:
    """Fluent queries against one collection."""

    def __init__(
        self,
        *,
        model: Any = None,
        collection: str | None = None,
        connection: str | None = None,
    ) -> None:
        if model is None and collection is None:
            raise ValueError("DocumentBuilder needs either a model or a collection name")
        self.model = model
        self.table = collection or (model.get_table() if model else "")
        self._connection_name = connection or (model.connection if model else None)

        self._wheres: list[Condition] = []
        self._orders: list[Order] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._selects: tuple[str, ...] = ()
        self._distinct: str | None = None
        self._eager: dict[str, Callable[[DocumentBuilder], Any] | None] = {}
        self._eager_counts: list[tuple[str, str]] = []
        self._without_scopes: set[str] = set()
        self._all_scopes_disabled = False
        self._casts: dict[str, Any] = {}

    # --- plumbing -----------------------------------------------------------

    @classmethod
    def for_collection(cls, collection: str, connection: str | None = None) -> DocumentBuilder:
        return cls(collection=collection, connection=connection)

    def clone(self) -> DocumentBuilder:
        clone = DocumentBuilder(
            model=self.model,
            collection=self.table,
            connection=self._connection_name,
        )
        clone._wheres = list(self._wheres)
        clone._orders = [Order(order.column, order.direction) for order in self._orders]
        clone._limit = self._limit
        clone._offset = self._offset
        clone._selects = self._selects
        clone._distinct = self._distinct
        clone._eager = dict(self._eager)
        clone._eager_counts = list(self._eager_counts)
        clone._without_scopes = set(self._without_scopes)
        clone._all_scopes_disabled = self._all_scopes_disabled
        clone._casts = dict(self._casts)
        return clone

    def get_store(self) -> Any:
        from almasix.orm.facade import get_manager

        return get_manager().store(self._connection_name)

    def field(self, reference: str) -> str:
        """`posts.title` and `title` name the same field inside a document."""
        prefix = f"{self.table}."
        return reference.removeprefix(prefix)

    def to_query(self) -> Query:
        """The query this builder describes, with global scopes applied."""
        scoped = self.clone()
        self._apply_global_scopes(scoped)
        return Query(
            collection=self.table,
            wheres=scoped._wheres,
            orders=scoped._orders,
            limit=scoped._limit,
            offset=scoped._offset,
            projection=scoped._selects,
            distinct=scoped._distinct,
        )

    def __getattr__(self, name: str) -> Any:
        """Local scopes, and an honest refusal for the SQL-only calls."""
        if name.startswith("_"):
            raise AttributeError(name)
        if name in SQL_ONLY:
            raise UnsupportedQueryError(f"{name}() is SQL-only — {SQL_ONLY[name]}")
        scope = getattr(self.model, f"scope_{name}", None) if self.model else None
        if scope is not None:

            def call(*args: Any, **kwargs: Any) -> DocumentBuilder:
                result = scope(self, *args, **kwargs)
                return self if result is None else result

            return call
        raise AttributeError(f"{type(self).__name__} has no attribute {name!r}")

    # --- where --------------------------------------------------------------

    def _push(self, condition: Condition) -> DocumentBuilder:
        self._wheres.append(condition)
        return self

    @staticmethod
    def _operator_and_value(operator: Any, value: Any) -> tuple[Any, Any]:
        """`where("age", 30)` and `where("age", ">", 30)` both work."""
        if value is _MISSING:
            return "=", operator
        return operator, value

    def where(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> DocumentBuilder:
        """`where("f", "=", v)` is canonical; `where("f", v)` assumes `=`."""
        if callable(column):
            nested = self.new_query()
            column(nested)
            if nested._wheres:
                self._push(Condition("", "group", nested._wheres, boolean))
            return self
        if isinstance(column, Mapping):
            for key, item in column.items():
                self.where(key, "=", item, boolean)
            return self
        if operator is _MISSING:
            raise TypeError("where() requires where(field, value) or where(field, operator, value)")
        real_operator, real_value = self._operator_and_value(operator, value)
        return self._push(
            Condition(self.field(column), str(real_operator).strip().lower(), real_value, boolean)
        )

    def or_where(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> DocumentBuilder:
        return self.where(column, operator, value, boolean="or")

    def where_in(self, column: str, values: Iterable[Any], boolean: str = "and") -> DocumentBuilder:
        return self._push(Condition(self.field(column), "in", list(values), boolean))

    def or_where_in(self, column: str, values: Iterable[Any]) -> DocumentBuilder:
        return self.where_in(column, values, "or")

    def where_not_in(
        self, column: str, values: Iterable[Any], boolean: str = "and"
    ) -> DocumentBuilder:
        return self._push(Condition(self.field(column), "not in", list(values), boolean))

    def where_null(self, column: str, boolean: str = "and") -> DocumentBuilder:
        return self._push(Condition(self.field(column), "null", None, boolean))

    def or_where_null(self, column: str) -> DocumentBuilder:
        return self.where_null(column, "or")

    def where_not_null(self, column: str, boolean: str = "and") -> DocumentBuilder:
        return self._push(Condition(self.field(column), "not null", None, boolean))

    def or_where_not_null(self, column: str) -> DocumentBuilder:
        return self.where_not_null(column, "or")

    def where_between(self, column: str, low: Any, high: Any) -> DocumentBuilder:
        return self._push(Condition(self.field(column), "between", (low, high)))

    def where_not_between(self, column: str, low: Any, high: Any) -> DocumentBuilder:
        return self._push(Condition(self.field(column), "not between", (low, high)))

    def where_like(self, column: str, pattern: str) -> DocumentBuilder:
        return self._push(Condition(self.field(column), "like", pattern))

    def where_key(self, value: Any) -> DocumentBuilder:
        key = self.model.primary_key if self.model else "_id"
        return self.where(key, "=", value)

    # --- document-native where ---------------------------------------------

    def where_regex(self, column: str, pattern: str) -> DocumentBuilder:
        """Match a field against a regular expression."""
        return self._push(Condition(self.field(column), "regex", pattern))

    def where_exists_field(self, column: str, exists: bool = True) -> DocumentBuilder:
        """Documents that carry the field at all — missing is not null."""
        return self._push(Condition(self.field(column), "exists", exists))

    def where_all(self, column: str, values: Iterable[Any]) -> DocumentBuilder:
        """An array field containing every one of these values."""
        return self._push(Condition(self.field(column), "all", list(values)))

    def where_size(self, column: str, size: int) -> DocumentBuilder:
        """An array field of exactly this length."""
        return self._push(Condition(self.field(column), "size", size))

    def where_raw(
        self,
        filter: Mapping[str, Any] | Callable[[Mapping[str, Any]], bool],
        boolean: str = "and",
    ) -> DocumentBuilder:
        """A filter Almasix did not write.

        A mapping goes to the engine as it is; a callable is a predicate the
        memory store can run, since it has no query language to hand it to.
        """
        value = filter if callable(filter) else dict(filter)
        return self._push(Condition("", "raw", value, boolean))

    # --- shaping ------------------------------------------------------------

    def select(self, *columns: str) -> DocumentBuilder:
        self._selects = tuple(self.field(column) for column in columns)
        return self

    def add_select(self, *columns: str) -> DocumentBuilder:
        self._selects = (*self._selects, *(self.field(column) for column in columns))
        return self

    def distinct(self, column: str) -> DocumentBuilder:
        self._distinct = self.field(column)
        return self

    def order_by(self, column: str, direction: str = "asc") -> DocumentBuilder:
        self._orders.append(Order(self.field(column), direction))
        return self

    def order_by_desc(self, column: str) -> DocumentBuilder:
        return self.order_by(column, "desc")

    def latest(self, column: str | None = None) -> DocumentBuilder:
        return self.order_by(column or self._timestamp_column(), "desc")

    def oldest(self, column: str | None = None) -> DocumentBuilder:
        return self.order_by(column or self._timestamp_column(), "asc")

    def reorder(self, column: str | None = None, direction: str = "asc") -> DocumentBuilder:
        self._orders = []
        return self.order_by(column, direction) if column else self

    def limit(self, count: int) -> DocumentBuilder:
        self._limit = count
        return self

    def take(self, count: int) -> DocumentBuilder:
        return self.limit(count)

    def offset(self, count: int) -> DocumentBuilder:
        self._offset = count
        return self

    def skip(self, count: int) -> DocumentBuilder:
        return self.offset(count)

    def for_page(self, page: int, per_page: int) -> DocumentBuilder:
        return self.offset(max(0, (page - 1) * per_page)).limit(per_page)

    def when(
        self,
        condition: Any,
        callback: Callable[..., Any],
        otherwise: Callable[..., Any] | None = None,
    ) -> DocumentBuilder:
        if condition:
            return callback(self, condition) or self
        if otherwise is not None:
            return otherwise(self, condition) or self
        return self

    def unless(
        self,
        condition: Any,
        callback: Callable[..., Any],
        otherwise: Callable[..., Any] | None = None,
    ) -> DocumentBuilder:
        return self.when(not condition, callback, otherwise)

    def tap(self, callback: Callable[[DocumentBuilder], Any]) -> DocumentBuilder:
        callback(self)
        return self

    def _timestamp_column(self) -> str:
        return self.model.created_at if self.model else "created_at"

    def new_query(self) -> DocumentBuilder:
        return DocumentBuilder(
            model=self.model, collection=self.table, connection=self._connection_name
        )

    # --- scopes -------------------------------------------------------------

    def without_global_scope(self, name: str) -> DocumentBuilder:
        self._without_scopes.add(name)
        return self

    def without_global_scopes(self) -> DocumentBuilder:
        self._all_scopes_disabled = True
        return self

    def _apply_global_scopes(self, builder: DocumentBuilder) -> DocumentBuilder:
        if self.model is None or self._all_scopes_disabled:
            return builder
        for name, scope in self.model.get_global_scopes().items():
            if name not in self._without_scopes:
                scope(builder)
        return builder

    # --- eager loading ------------------------------------------------------

    def with_(self, *relations: Any, **constrained: Callable[[Any], Any]) -> DocumentBuilder:
        for relation in relations:
            if isinstance(relation, Mapping):
                self._eager.update(relation)
            else:
                self._eager[relation] = None
        self._eager.update(constrained)
        return self

    def without(self, *relations: str) -> DocumentBuilder:
        for relation in relations:
            self._eager.pop(relation, None)
        return self

    def with_casts(self, casts: Mapping[str, Any]) -> DocumentBuilder:
        self._casts.update(casts)
        return self

    def with_count(self, *relations: str) -> DocumentBuilder:
        """`{relation}_count`, counted in the store rather than in Python."""
        for relation in relations:
            name, _, alias = str(relation).partition(" as ")
            self._eager_counts.append((name, alias or f"{name}_count"))
        return self

    async def _load_eager(self, models: list[Any]) -> None:
        from almasix.orm.documents.eager import load_document_counts, load_document_relations

        if not models:
            return
        if self._eager:
            await load_document_relations(models, self._eager)
        for name, alias in self._eager_counts:
            await load_document_counts(models, name, alias)

    # --- reads --------------------------------------------------------------

    def hydrate(self, rows: Sequence[Mapping[str, Any]]) -> Collection[Any]:
        if self.model is None:
            return Collection([dict(row) for row in rows])
        return self.model.new_collection(
            [self.model._hydrate(dict(row), casts=self._casts) for row in rows]
        )

    async def get(self) -> Collection[Any]:
        rows = await self.get_store().find(self.to_query())
        results = self.hydrate(rows)
        await self._load_eager(list(results))
        return results

    async def get_raw(self) -> list[dict[str, Any]]:
        return await self.get_store().find(self.to_query())

    async def first(self) -> Any:
        results = await self.clone().limit(1).get()
        return results[0] if len(results) else None

    async def first_or_fail(self) -> Any:
        found = await self.first()
        if found is None:
            raise ModelNotFoundError(self.model.__name__ if self.model else self.table)
        return found

    async def find(self, key: Any) -> Any:
        return await self.clone().where_key(key).first()

    async def find_many(self, keys: Iterable[Any]) -> Collection[Any]:
        column = self.model.primary_key if self.model else "_id"
        return await self.clone().where_in(column, keys).get()

    async def find_or_fail(self, key: Any) -> Any:
        found = await self.find(key)
        if found is None:
            raise ModelNotFoundError(self.model.__name__ if self.model else self.table, key)
        return found

    async def all(self) -> Collection[Any]:
        return await self.get()

    async def value(self, column: str) -> Any:
        row = await self.clone().select(column).first()
        if row is None:
            return None
        return row.get_raw_attribute(self.field(column)) if self.model else row[self.field(column)]

    async def pluck(self, column: str, key: str | None = None) -> Any:
        rows = await self.clone().get_raw()
        field = self.field(column)
        if key is None:
            return Collection([row.get(field) for row in rows])
        return Collection({row.get(self.field(key)): row.get(field) for row in rows})

    async def exists(self) -> bool:
        return await self.count() > 0

    async def doesnt_exist(self) -> bool:
        return not await self.exists()

    async def count(self, column: str | None = None) -> int:
        query = self.to_query()
        if column is not None:
            query.wheres.append(Condition(self.field(column), "not null"))
        return await self.get_store().count(query)

    async def sum(self, column: str) -> Any:
        return await self.get_store().aggregate(self.to_query(), "sum", self.field(column))

    async def avg(self, column: str) -> Any:
        return await self.get_store().aggregate(self.to_query(), "avg", self.field(column))

    async def min(self, column: str) -> Any:
        return await self.get_store().aggregate(self.to_query(), "min", self.field(column))

    async def max(self, column: str) -> Any:
        return await self.get_store().aggregate(self.to_query(), "max", self.field(column))

    async def raw_aggregate(self, pipeline: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Run an engine-native aggregation pipeline."""
        store = self.get_store()
        runner = getattr(store, "raw_aggregate", None)
        if runner is None:
            raise UnsupportedQueryError(
                f"The {store.driver!r} store has no aggregation pipeline to run"
            )
        return await runner(self.table, pipeline)

    # --- chunking -----------------------------------------------------------

    async def chunk(self, size: int, callback: Callable[[Collection[Any]], Any]) -> bool:
        page = 1
        while True:
            results = await self.clone().for_page(page, size).get()
            if not len(results):
                return True
            outcome = callback(results)
            if hasattr(outcome, "__await__"):
                outcome = await outcome
            if outcome is False:
                return False
            if len(results) < size:
                return True
            page += 1

    async def each(self, callback: Callable[[Any], Any], size: int = 100) -> bool:
        async def handle(chunk: Collection[Any]) -> Any:
            for item in chunk:
                outcome = callback(item)
                if hasattr(outcome, "__await__"):
                    outcome = await outcome
                if outcome is False:
                    return False
            return True

        return await self.chunk(size, handle)

    async def _stream_lazy(self, size: int = 1000) -> AsyncIterator[Any]:
        page = 1
        while True:
            results = await self.clone().for_page(page, size).get()
            if not len(results):
                return
            for item in results:
                yield item
            if len(results) < size:
                return
            page += 1

    def lazy(self, size: int = 1000) -> AsyncLazyCollection:
        return AsyncLazyCollection(functools.partial(self._stream_lazy, size))

    # --- pagination ---------------------------------------------------------

    async def paginate(self, per_page: int | None = None, page: int = 1) -> Paginator:
        size = per_page or (self.model.per_page if self.model else 15)
        total = await self.clone().count()
        items = await self.clone().for_page(page, size).get()
        return Paginator(items, total, size, page)

    async def simple_paginate(self, per_page: int | None = None, page: int = 1) -> SimplePaginator:
        size = per_page or (self.model.per_page if self.model else 15)
        results = await self.clone().for_page(page, size + 1).get()
        has_more = len(results) > size
        return SimplePaginator(results.take(size), size, page, has_more)

    # --- writes -------------------------------------------------------------

    async def insert(self, values: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> int:
        rows = [dict(values)] if isinstance(values, Mapping) else [dict(row) for row in values]
        if not rows:
            return 0
        return len(await self.get_store().insert(self.table, rows))

    async def insert_get_id(self, values: Mapping[str, Any]) -> Any:
        keys = await self.get_store().insert(self.table, [dict(values)])
        return keys[0]

    async def update(self, values: Mapping[str, Any]) -> int:
        return await self.get_store().update(self.to_query(), dict(values))

    async def delete(self) -> int:
        return await self.get_store().delete(self.to_query())

    async def increment(self, column: str, amount: int = 1, **extra: Any) -> int:
        return await self.get_store().increment(
            self.to_query(), {self.field(column): amount}, extra
        )

    async def decrement(self, column: str, amount: int = 1, **extra: Any) -> int:
        return await self.increment(column, -amount, **extra)

    async def upsert(
        self,
        values: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        unique_by: Sequence[str],
        update: Sequence[str] | None = None,
    ) -> int:
        """Insert, or set the named fields on the document already there."""
        rows = [dict(values)] if isinstance(values, Mapping) else [dict(row) for row in values]
        unique = list(unique_by)
        if not unique:
            raise ValueError("upsert() requires unique_by fields")
        affected = 0
        for row in rows:
            columns = update if update is not None else [key for key in row if key not in unique]
            probe = self.new_query()
            for field in unique:
                probe.where(field, "=", row.get(field))
            if await probe.clone().count():
                affected += await probe.update({key: row[key] for key in columns if key in row})
            else:
                await self.get_store().insert(self.table, [row])
                affected += 1
        return affected

    async def truncate(self) -> None:
        """Drop the collection — indexes and all."""
        await self.get_store().drop_collection(self.table)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<DocumentBuilder {self.table} wheres={len(self._wheres)}>"
