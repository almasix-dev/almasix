"""Eloquent-shaped collection — Support Collection + model helpers.

Several inherited methods are overridden to key off the models' primary keys
rather than the collection's own indexes, which is what Eloquent's collection
does: ``only``, ``except_``, ``contains``, ``diff``, ``intersect``, ``unique``,
and ``find``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from avalon.support.collection import Collection as SupportCollection
from avalon.support.collection import install_higher_order

if TYPE_CHECKING:  # pragma: no cover - typing only
    from avalon.orm.builder import QueryBuilder

T = TypeVar("T")


def _key_of(item: Any) -> Any:
    """The primary key of a model, or the value itself when it is a key."""
    getter = getattr(item, "get_key", None)
    return getter() if callable(getter) else item


class Collection(SupportCollection[T]):
    """Model collection returned from multi-row Articulate reads."""

    def model_keys(self) -> list[Any]:
        return [item.get_key() for item in self]  # type: ignore[attr-defined]

    def to_dict(self) -> list[Any]:
        result: list[Any] = []
        for item in self:
            serializer = getattr(item, "to_dict", None)
            result.append(serializer() if callable(serializer) else item)
        return result

    # --- lookups ------------------------------------------------------------

    def find(self, key: Any, default: Any = None) -> Any:
        """Find a model by primary key, or by another model's key."""
        if callable(key) and not isinstance(key, type):
            return next((item for item in self if key(item)), default)
        wanted = _key_of(key)
        return next((item for item in self if _key_of(item) == wanted), default)

    def contains(self, key: Any, operator: Any = None, value: Any = None) -> bool:
        """Whether the collection holds a given model, key, or match."""
        if operator is None and value is None and not callable(key):
            wanted = _key_of(key)
            return any(_key_of(item) == wanted for item in self)
        return super().contains(key, operator, value)

    # --- set operations, by model key --------------------------------------

    def only(self, *keys: Any) -> Collection[T]:
        """Keep only the models whose primary keys were given."""
        wanted = {_key_of(key) for key in _flatten(keys)}
        return self._new(item for item in self._items.values() if _key_of(item) in wanted)

    def except_(self, *keys: Any) -> Collection[T]:
        """Drop the models whose primary keys were given."""
        unwanted = {_key_of(key) for key in _flatten(keys)}
        return self._new(item for item in self._items.values() if _key_of(item) not in unwanted)

    def diff(self, items: Any) -> Collection[T]:
        """Models in this collection that are not in the given one."""
        other = {_key_of(item) for item in SupportCollection(items)._values_list()}
        return self._new(item for item in self._items.values() if _key_of(item) not in other)

    def intersect(self, items: Any) -> Collection[T]:
        """Models present in both collections."""
        other = {_key_of(item) for item in SupportCollection(items)._values_list()}
        return self._new(item for item in self._items.values() if _key_of(item) in other)

    def unique(self, key: Any = None, strict: bool = False) -> Collection[T]:
        """Deduplicate by primary key, or by the given key."""
        if key is not None:
            return super().unique(key, strict)
        seen: set[Any] = set()
        kept: list[Any] = []
        for item in self._items.values():
            marker = _key_of(item)
            if marker not in seen:
                seen.add(marker)
                kept.append(item)
        return self._new(kept)

    # --- serialization pass-throughs ---------------------------------------

    def make_hidden(self, *keys: str) -> Collection[T]:
        """Hide attributes on every model in the collection."""
        for item in self:
            item.make_hidden(*keys)  # type: ignore[attr-defined]
        return self

    def make_visible(self, *keys: str) -> Collection[T]:
        """Reveal attributes on every model in the collection."""
        for item in self:
            item.make_visible(*keys)  # type: ignore[attr-defined]
        return self

    def set_visible(self, keys: list[str]) -> Collection[T]:
        for item in self:
            item.set_visible(keys)  # type: ignore[attr-defined]
        return self

    def set_hidden(self, keys: list[str]) -> Collection[T]:
        for item in self:
            item.set_hidden(keys)  # type: ignore[attr-defined]
        return self

    def append(self, *keys: str) -> Collection[T]:
        """Append accessors on every model in the collection."""
        for item in self:
            item.append(*keys)  # type: ignore[attr-defined]
        return self

    # --- queries ------------------------------------------------------------

    def to_query(self) -> QueryBuilder:
        """A query scoped to the models in this collection (``toQuery``)."""
        items = self._values_list()
        if not items:
            raise ValueError("Cannot build a query from an empty collection.")
        model = type(items[0])
        return model.new_query().where_in(model.primary_key, self.model_keys())

    async def fresh(self, *relations: str) -> Collection[T]:
        """Reload every model from the database (``fresh``)."""
        items = self._values_list()
        if not items:
            return self
        model = type(items[0])
        query = model.new_query().where_in(model.primary_key, self.model_keys())
        if relations:
            query = query.with_(*relations)
        reloaded = {item.get_key(): item for item in await query.get()}
        return self._new(
            reloaded[key] for item in items if (key := item.get_key()) in reloaded  # type: ignore[attr-defined]
        )

    async def load(self, *relations: str) -> Collection[T]:
        """Lazy eager-load relations onto every model in the collection."""
        items = self._values_list()
        if not items:
            return self
        from avalon.orm.eager import eager_load

        await eager_load(items, relations)
        return self

    async def load_morph(self, relation: str, spec: Mapping[Any, Any]) -> Collection[T]:
        """Eager load per-type relations behind a `morph_to` (``loadMorph``)."""
        from avalon.orm.eager import load_morph

        await load_morph(self._values_list(), relation, spec)
        return self

    async def load_morph_count(self, relation: str, spec: Mapping[Any, Any]) -> Collection[T]:
        """Count per-type relations behind a `morph_to` (``loadMorphCount``)."""
        from avalon.orm.eager import load_morph_aggregate

        await load_morph_aggregate(self._values_list(), relation, spec)
        return self

    async def load_aggregate(
        self,
        relations: Any,
        column: str | None = None,
        function: str = "count",
        **constrained: Any,
    ) -> Collection[T]:
        """Attach an aggregate over a relation to every model in one query."""
        items = self._values_list()
        if not items:
            return self
        from avalon.orm.eager import load_aggregates

        names = relations if isinstance(relations, (list, tuple)) else [relations]
        await load_aggregates(items, names, function, column, constrained)
        return self

    async def load_count(self, *relations: Any, **constrained: Any) -> Collection[T]:
        return await self.load_aggregate(list(relations), None, "count", **constrained)

    async def load_exists(self, *relations: Any, **constrained: Any) -> Collection[T]:
        return await self.load_aggregate(list(relations), None, "exists", **constrained)

    async def load_sum(self, relations: Any, column: str, **constrained: Any) -> Collection[T]:
        return await self.load_aggregate(relations, column, "sum", **constrained)

    async def load_avg(self, relations: Any, column: str, **constrained: Any) -> Collection[T]:
        return await self.load_aggregate(relations, column, "avg", **constrained)

    async def load_min(self, relations: Any, column: str, **constrained: Any) -> Collection[T]:
        return await self.load_aggregate(relations, column, "min", **constrained)

    async def load_max(self, relations: Any, column: str, **constrained: Any) -> Collection[T]:
        return await self.load_aggregate(relations, column, "max", **constrained)

    async def load_missing(self, *relations: str) -> Collection[T]:
        items = self._values_list()
        pending = [
            name
            for name in relations
            if any(not item.relation_loaded(name.split(".")[0]) for item in items)  # type: ignore[attr-defined]
        ]
        if pending:
            await self.load(*pending)
        return self


def _flatten(keys: tuple[Any, ...]) -> list[Any]:
    """Accept `only(1, 2)` and `only([1, 2])` alike."""
    flat: list[Any] = []
    for key in keys:
        if isinstance(key, (list, tuple, set)):
            flat.extend(key)
        else:
            flat.append(key)
    return flat


# The overrides below (`contains`, `unique`) must keep answering higher order
# messages, so wrap this class's own methods too.
install_higher_order(Collection)
