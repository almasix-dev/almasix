"""Relationships — every Eloquent relation type."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.sql.util import ClauseAdapter

from almasix.orm.builder import _MISSING, QueryBuilder
from almasix.orm.collection import Collection
from almasix.orm.inflector import pivot_table, snake
from almasix.orm.morph import morph_alias, morph_map, morph_target

if TYPE_CHECKING:
    from almasix.orm.model import Model

PIVOT_PARENT = "__pivot_parent"


@dataclass(frozen=True)
class _OfMany:
    """Which columns and aggregates pick the one row per parent."""

    columns: Mapping[str, str]
    callback: Callable[[QueryBuilder], Any] | None = None


def _call_default(func: Callable[..., Any], instance: Any, parent: Any) -> Any:
    """Call a `with_default` callable with as many arguments as it takes."""
    try:
        count = len(inspect.signature(func).parameters)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        count = 1
    if count >= 2:
        return func(instance, parent)
    if count == 1:
        return func(instance)
    return func()


class Relation:
    """Base relation: proxies the builder and knows how to eager load."""

    def __init__(self, parent: Model, related: type[Model]) -> None:
        self.parent = parent
        self.related = related
        self._default: Any = None

    # --- builder proxy ------------------------------------------------------

    def query(self) -> QueryBuilder:
        raise NotImplementedError

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.query(), name)

    async def get(self) -> Collection[Any]:
        return await self.query().get()

    async def first(self) -> Any:
        return await self.query().first()

    async def count(self) -> int:
        return await self.query().count()

    async def exists(self) -> bool:
        return await self.query().exists()

    # --- eager loading contract --------------------------------------------

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        raise NotImplementedError

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        raise NotImplementedError

    def existence_query(
        self,
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        raise NotImplementedError

    def grouping_column(self) -> str:
        """Column `with_count` groups by to bucket rows per parent."""
        raise NotImplementedError

    def parent_match_key(self) -> str:
        """Parent attribute whose value matches `grouping_column`."""
        raise NotImplementedError

    # --- default models -----------------------------------------------------

    def with_default(self, default: Any = True) -> Any:
        """Return a placeholder model instead of ``None`` (``withDefault``).

        Pass a mapping to seed attributes, or a callable taking the default
        instance and (optionally) the parent.
        """
        self._default = default
        return self

    def _default_instance(self) -> Any:
        default = self._default
        if default is None or default is False:
            return None
        instance = self.related()
        if isinstance(default, Mapping):
            instance.force_fill(default)
        elif callable(default):
            outcome = _call_default(default, instance, self.parent)
            if isinstance(outcome, Mapping):
                instance.force_fill(outcome)
        return instance

    # --- helpers ------------------------------------------------------------

    def _related_builder(self) -> QueryBuilder:
        return self.related.new_query()

    @staticmethod
    def _keys(models: Sequence[Model], key: str) -> list[Any]:
        seen: list[Any] = []
        for model in models:
            value = model.get_raw_attribute(key)
            if value is not None and value not in seen:
                seen.append(value)
        return seen


class HasOneOrMany(Relation):
    """Shared behaviour for `has_one` / `has_many`."""

    def __init__(
        self,
        parent: Model,
        related: type[Model],
        foreign_key: str,
        local_key: str,
    ) -> None:
        super().__init__(parent, related)
        self.foreign_key = foreign_key
        self.local_key = local_key
        self._of_many: _OfMany | None = None
        self._chaperone: str | None = None

    def query(self) -> QueryBuilder:
        builder = self._related_builder().where(
            self.foreign_key, "=", self.parent.get_raw_attribute(self.local_key)
        )
        return self._apply_of_many(builder)

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        keys = self._keys(models, self.local_key)
        builder = self._related_builder().where_in(self.foreign_key, keys)
        return self._apply_of_many(builder)

    def _apply_of_many(self, builder: QueryBuilder) -> QueryBuilder:
        """Constrain to one row per parent with a correlated subquery.

        Picking in Python instead would mean loading every child row just to
        discard all but one per parent.
        """
        spec = self._of_many
        if spec is None:
            return builder

        table = self.related.get_table()
        key = self.related.primary_key

        # The callback runs against a stand-in table so that every column it
        # touches exists before we alias it, then gets rewritten onto the alias.
        probe = sa.table(table)
        extra = None
        if spec.callback is not None:
            scoped = QueryBuilder(
                table=table,
                connection=self.related.connection,
                tables={table: probe},
            )
            spec.callback(scoped)
            extra = scoped._compile_wheres()
        for name in (key, self.foreign_key, *spec.columns):
            if name not in probe.c:
                probe.append_column(sa.column(name))
        inner = probe.alias("of_many")
        if extra is not None:
            extra = ClauseAdapter(inner).traverse(extra)

        orders = []
        for name, aggregate in spec.columns.items():
            column = inner.c[name]
            orders.append(sa.desc(column) if aggregate == "max" else sa.asc(column))
        if key not in spec.columns:  # deterministic tie-break, as Laravel does
            last = next(iter(spec.columns.values()))
            orders.append(sa.desc(inner.c[key]) if last == "max" else sa.asc(inner.c[key]))

        picked = (
            sa.select(inner.c[key])
            .where(inner.c[self.foreign_key] == builder.column(f"{table}.{self.foreign_key}"))
            .order_by(*orders)
            .limit(1)
        )
        if extra is not None:
            picked = picked.where(extra)

        builder._push_where("and", builder.column(f"{table}.{key}") == picked.scalar_subquery())
        return builder

    def _resolve_single(self, matches: Sequence[Any], parent: Model) -> Any:
        """The single model for a has-one style relation, or its default."""
        if not matches:
            return self._default_instance()
        found = matches[0]
        if self._chaperone is not None:
            found.set_relation(self._chaperone, parent)
        return found

    def _group(self, results: Collection[Any]) -> dict[Any, list[Any]]:
        grouped: dict[Any, list[Any]] = {}
        for item in results:
            grouped.setdefault(item.get_raw_attribute(self.foreign_key), []).append(item)
        return grouped

    def grouping_column(self) -> str:
        return f"{self.related.get_table()}.{self.foreign_key}"

    def parent_match_key(self) -> str:
        return self.local_key

    def existence_query(
        self,
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        builder = self._related_builder()
        builder._apply_global_scopes(builder)
        if callback is not None:
            callback(builder)
        outer = parent_builder.column(f"{self.parent.get_table()}.{self.local_key}")
        builder._push_where(
            "and", builder.column(f"{self.related.get_table()}.{self.foreign_key}") == outer
        )
        return builder._base_select([sa.literal(1)])

    async def create(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        payload = {
            **(attributes or {}),
            **kwargs,
            self.foreign_key: self.parent.get_raw_attribute(self.local_key),
        }
        instance = self.related()
        instance.force_fill(payload)
        await instance.save()
        return instance

    async def save(self, model: Model) -> Any:
        model.set_attribute(self.foreign_key, self.parent.get_raw_attribute(self.local_key))
        await model.save()
        return model

    async def save_many(self, models: Iterable[Model]) -> list[Any]:
        return [await self.save(model) for model in models]

    async def create_many(self, records: Iterable[Mapping[str, Any]]) -> list[Any]:
        return [await self.create(record) for record in records]

    async def first_or_create(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> Any:
        found = await self._match(attributes)
        if found is not None:
            return found
        return await self.create({**attributes, **(values or {})})

    async def _match(self, attributes: Mapping[str, Any]) -> Any:
        probe = self.query()
        for key, value in attributes.items():
            probe.where(key, "=", value)
        return await probe.first()

    def make(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        """An unsaved related model with the foreign key already set."""
        instance = self.related()
        instance.force_fill(
            {
                **(attributes or {}),
                **kwargs,
                self.foreign_key: self.parent.get_raw_attribute(self.local_key),
            }
        )
        return instance

    def make_many(self, records: Iterable[Mapping[str, Any]]) -> list[Any]:
        return [self.make(record) for record in records]

    async def create_quietly(
        self,
        attributes: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Create without firing model events."""
        instance = self.make(attributes, **kwargs)
        await instance.save_quietly()
        return instance

    async def first_or_new(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> Any:
        found = await self._match(attributes)
        return found if found is not None else self.make({**attributes, **(values or {})})

    async def find_or_new(self, key: Any) -> Any:
        """The related model with this key, or an unsaved one."""
        found = await self.query().find(key)
        return found if found is not None else self.make()

    async def update_or_create(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> Any:
        found = await self._match(attributes)
        if found is None:
            return await self.create({**attributes, **(values or {})})
        found.fill(dict(values or {}))
        await found.save()
        return found

    # --- one of many --------------------------------------------------------

    def one(self) -> HasOne:
        """Narrow a "many" relation to a single model — Laravel's ``one()``."""
        relation = HasOne(self.parent, self.related, self.foreign_key, self.local_key)
        return self._copy_state_to(relation)

    def of_many(
        self,
        column: str | Mapping[str, str] = "id",
        aggregate: str = "max",
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> HasOne:
        """One related model per parent, chosen by an aggregate (``ofMany``).

        ``column`` may be a mapping of column to aggregate, which is how ties
        are broken on more than one column::

            self.has_many(Price).of_many({"published_at": "max", "id": "max"})
        """
        columns = {column: aggregate} if isinstance(column, str) else dict(column)
        relation = self.one()
        relation._of_many = _OfMany(columns, callback)
        return relation

    def latest_of_many(self, column: str | Mapping[str, str] = "id") -> HasOne:
        """The newest related model per parent (``latestOfMany``)."""
        return self.of_many(column, "max")

    def oldest_of_many(self, column: str | Mapping[str, str] = "id") -> HasOne:
        """The oldest related model per parent (``oldestOfMany``)."""
        return self.of_many(column, "min")

    def chaperone(self, name: str | None = None) -> HasOneOrMany:
        """Hydrate the inverse relation on each child (``chaperone``).

        Without this, iterating children and reading `child.parent` raises,
        because the relation was never loaded — even though the parent is the
        model you already have in hand.
        """
        self._chaperone = name or snake(type(self.parent).__name__)
        return self

    def _copy_state_to(self, relation: HasOneOrMany) -> Any:
        relation._of_many = self._of_many
        relation._chaperone = self._chaperone
        return relation

    def _hydrate_parents(self, children: Iterable[Any], name: str | None = None) -> None:
        """Set the inverse relation on children when chaperoning."""
        target = name or self._chaperone
        if target is None:
            return
        for child in children:
            child.set_relation(target, self.parent)


class HasMany(HasOneOrMany):
    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped = self._group(results)
        for model in models:
            key = model.get_raw_attribute(self.local_key)
            matches = grouped.get(key, [])
            if self._chaperone is not None:
                for child in matches:
                    child.set_relation(self._chaperone, model)
            model.set_relation(name, Collection(matches))

    async def get(self) -> Collection[Any]:
        results = await self.query().get()
        self._hydrate_parents(results)
        return results


class HasOne(HasOneOrMany):
    async def get(self) -> Any:  # type: ignore[override]
        found = await self.query().first()
        return self._resolve_single([found] if found is not None else [], self.parent)

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped = self._group(results)
        for model in models:
            matches = grouped.get(model.get_raw_attribute(self.local_key), [])
            model.set_relation(name, self._resolve_single(matches, model))


class BelongsTo(Relation):
    def __init__(
        self,
        child: Model,
        related: type[Model],
        foreign_key: str,
        owner_key: str,
    ) -> None:
        super().__init__(child, related)
        self.foreign_key = foreign_key
        self.owner_key = owner_key

    def query(self) -> QueryBuilder:
        return self._related_builder().where(
            self.owner_key, "=", self.parent.get_raw_attribute(self.foreign_key)
        )

    async def get(self) -> Any:  # type: ignore[override]
        found = await self.query().first()
        return found if found is not None else self._default_instance()

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        keys = self._keys(models, self.foreign_key)
        return self._related_builder().where_in(self.owner_key, keys)

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        index = {item.get_raw_attribute(self.owner_key): item for item in results}
        for model in models:
            found = index.get(model.get_raw_attribute(self.foreign_key))
            model.set_relation(name, found if found is not None else self._default_instance())

    def existence_query(
        self,
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        builder = self._related_builder()
        builder._apply_global_scopes(builder)
        if callback is not None:
            callback(builder)
        outer = parent_builder.column(f"{self.parent.get_table()}.{self.foreign_key}")
        builder._push_where(
            "and", builder.column(f"{self.related.get_table()}.{self.owner_key}") == outer
        )
        return builder._base_select([sa.literal(1)])

    def grouping_column(self) -> str:
        return f"{self.related.get_table()}.{self.owner_key}"

    def parent_match_key(self) -> str:
        return self.foreign_key

    def associate(self, model: Model | Any) -> Model:
        value = model.get_raw_attribute(self.owner_key) if hasattr(model, "get_raw_attribute") else model
        self.parent.set_attribute(self.foreign_key, value)
        return self.parent

    def dissociate(self) -> Model:
        self.parent.set_attribute(self.foreign_key, None)
        return self.parent


class BelongsToMany(Relation):
    """Many-to-many through a pivot table."""

    def __init__(
        self,
        parent: Model,
        related: type[Model],
        table: str | None = None,
        foreign_pivot_key: str | None = None,
        related_pivot_key: str | None = None,
    ) -> None:
        super().__init__(parent, related)
        self.pivot = table or pivot_table(type(parent).__name__, related.__name__)
        self.foreign_pivot_key = foreign_pivot_key or type(parent).get_foreign_key()
        self.related_pivot_key = related_pivot_key or related.get_foreign_key()
        self.parent_key = type(parent).primary_key
        self.related_key = related.primary_key
        self._pivot_columns: list[str] = []
        self._pivot_accessor = "pivot"
        self._pivot_class: type[Any] | None = None
        self._pivot_timestamps = False
        self._pivot_wheres: list[tuple[str, str, Any, Any]] = []
        self._pivot_orders: list[tuple[str, str]] = []

    def with_pivot(self, *columns: str) -> BelongsToMany:
        self._pivot_columns.extend(columns)
        return self

    @property
    def pivot_class(self) -> type[Any]:
        from almasix.orm.pivot import Pivot

        return self._pivot_class or Pivot

    def using(self, pivot_class: type[Any]) -> BelongsToMany:
        """Hydrate pivot rows into a custom `Pivot` subclass (``using``)."""
        self._pivot_class = pivot_class
        return self

    def as_(self, accessor: str) -> BelongsToMany:
        """Rename the pivot accessor — Laravel's ``as``."""
        self._pivot_accessor = accessor
        return self

    def with_timestamps(
        self,
        created_at: str = "created_at",
        updated_at: str = "updated_at",
    ) -> BelongsToMany:
        """Maintain timestamps on the intermediate table."""
        self._pivot_timestamps = True
        self._pivot_created_at = created_at
        self._pivot_updated_at = updated_at
        self.with_pivot(created_at, updated_at)
        return self

    # --- pivot filtering and ordering ---------------------------------------

    def _add_pivot_where(self, column: str, kind: str, *values: Any) -> BelongsToMany:
        self._pivot_wheres.append((kind, column, values[0] if values else None, values))
        return self

    def where_pivot_in(self, column: str, values: Iterable[Any]) -> BelongsToMany:
        return self._add_pivot_where(column, "in", list(values))

    def where_pivot_not_in(self, column: str, values: Iterable[Any]) -> BelongsToMany:
        return self._add_pivot_where(column, "not_in", list(values))

    def where_pivot_null(self, column: str) -> BelongsToMany:
        return self._add_pivot_where(column, "null")

    def where_pivot_not_null(self, column: str) -> BelongsToMany:
        return self._add_pivot_where(column, "not_null")

    def where_pivot_between(self, column: str, low: Any, high: Any) -> BelongsToMany:
        return self._add_pivot_where(column, "between", low, high)

    def order_by_pivot(self, column: str, direction: str = "asc") -> BelongsToMany:
        self._pivot_orders.append((column, direction))
        return self

    def _apply_pivot_constraints(self, builder: QueryBuilder) -> QueryBuilder:
        for kind, column, first, values in self._pivot_wheres:
            qualified = f"{self.pivot}.{column}"
            if kind == "in":
                builder.where_in(qualified, first)
            elif kind == "not_in":
                builder.where_not_in(qualified, first)
            elif kind == "null":
                builder.where_null(qualified)
            elif kind == "not_null":
                builder.where_not_null(qualified)
            else:
                builder.where_between(qualified, values[0], values[1])
        for column, direction in self._pivot_orders:
            builder.order_by(f"{self.pivot}.{column}", direction)
        return builder

    # --- pivot hydration ----------------------------------------------------

    def _hydrate_pivot(self, model: Any, parent_key: Any = _MISSING) -> Any:
        """Attach the intermediate row to a result as `model.pivot`."""
        from almasix.orm.pivot import new_pivot

        if parent_key is _MISSING:
            parent_key = self.parent.get_raw_attribute(self.parent_key)
        attributes: dict[str, Any] = {
            self.foreign_pivot_key: parent_key,
            self.related_pivot_key: model.get_raw_attribute(self.related_key),
        }
        for column in self._pivot_columns:
            key = f"pivot_{column}"
            if key in model._attributes:
                attributes[column] = model._attributes[key]
        model.set_relation(self._pivot_accessor, new_pivot(self, attributes))
        return model

    def _join(self, builder: QueryBuilder) -> QueryBuilder:
        related_table = self.related.get_table()
        builder.join(
            self.pivot,
            f"{self.pivot}.{self.related_pivot_key}",
            "=",
            f"{related_table}.{self.related_key}",
        )
        selects: list[Any] = [sa.literal_column(f"{related_table}.*")]
        for column in self._pivot_columns:
            selects.append(builder.column(f"{self.pivot}.{column}").label(f"pivot_{column}"))
        builder.select(*selects)
        return builder

    def query(self) -> QueryBuilder:
        builder = self._join(self._related_builder())
        builder.where(
            f"{self.pivot}.{self.foreign_pivot_key}",
            "=",
            self.parent.get_raw_attribute(self.parent_key),
        )
        return self._apply_pivot_constraints(builder)

    async def get(self) -> Collection[Any]:
        results = await self.query().get()
        for model in results:
            self._hydrate_pivot(model)
        return results

    async def first(self) -> Any:
        found = await self.query().first()
        return self._hydrate_pivot(found) if found is not None else None

    def where_pivot(
        self,
        column: str,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        return self.query().where(f"{self.pivot}.{column}", operator, value)

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        keys = self._keys(models, self.parent_key)
        builder = self._join(self._related_builder())
        builder.add_select(
            builder.column(f"{self.pivot}.{self.foreign_pivot_key}").label(PIVOT_PARENT)
        )
        builder.where_in(f"{self.pivot}.{self.foreign_pivot_key}", keys)
        return self._apply_pivot_constraints(builder)

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped: dict[Any, list[Any]] = {}
        for item in results:
            marker = item.get_raw_attribute(PIVOT_PARENT)
            item._attributes.pop(PIVOT_PARENT, None)
            grouped.setdefault(marker, []).append(item)
        for model in models:
            key = model.get_raw_attribute(self.parent_key)
            matches = grouped.get(key, [])
            for match in matches:
                self._hydrate_pivot(match, key)
            model.set_relation(name, Collection(matches))

    def existence_query(
        self,
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        builder = self._join(self._related_builder())
        builder._apply_global_scopes(builder)
        if callback is not None:
            callback(builder)
        outer = parent_builder.column(f"{self.parent.get_table()}.{self.parent_key}")
        builder._push_where(
            "and", builder.column(f"{self.pivot}.{self.foreign_pivot_key}") == outer
        )
        builder._selects = []
        return builder._base_select([sa.literal(1)])

    def grouping_column(self) -> str:
        return f"{self.pivot}.{self.foreign_pivot_key}"

    def parent_match_key(self) -> str:
        return self.parent_key

    # --- pivot mutations ----------------------------------------------------

    def _pivot_query(self) -> QueryBuilder:
        return QueryBuilder.for_table(self.pivot, connection=self.related.connection)

    async def attach(
        self,
        ids: Any,
        attributes: Mapping[str, Any] | None = None,
    ) -> int:
        """Attach ids, optionally with pivot attributes.

        `ids` may be a mapping of id to per-row attributes, which is how you
        attach several rows with different pivot data in one call.
        """
        rows = []
        for identifier, extra in _as_pairs(ids).items():
            rows.append(
                {
                    self.foreign_pivot_key: self.parent.get_raw_attribute(self.parent_key),
                    self.related_pivot_key: identifier,
                    **(attributes or {}),
                    **extra,
                    **self._timestamps(fresh=True),
                }
            )
        if not rows:
            return 0
        return await self._pivot_query().insert(rows)

    def _timestamps(self, *, fresh: bool) -> dict[str, Any]:
        """Pivot timestamp columns, when `with_timestamps` asked for them."""
        if not self._pivot_timestamps:
            return {}
        now = self.parent._fresh_timestamp()
        stamps = {self._pivot_updated_at: now}
        if fresh:
            stamps[self._pivot_created_at] = now
        return stamps

    async def detach(self, ids: Any = None) -> int:
        builder = self._pivot_query().where(
            self.foreign_pivot_key, "=", self.parent.get_raw_attribute(self.parent_key)
        )
        if ids is not None:
            builder.where_in(self.related_pivot_key, _as_keys(ids))
        return await builder.delete()

    async def sync(self, ids: Any, detaching: bool = True) -> dict[str, list[Any]]:
        """Make the pivot match `ids`, reporting what changed.

        `ids` may be a mapping of id to pivot attributes; ids already attached
        with different attributes are updated and reported under `updated`.
        """
        desired = _as_pairs(ids)
        current = await self.pivot_ids()
        attached = [key for key in desired if key not in current]
        detached = [key for key in current if key not in desired] if detaching else []
        updated: list[Any] = []

        if detached:
            await self.detach(detached)
        if attached:
            await self.attach({key: desired[key] for key in attached})
        for key, extra in desired.items():
            if key not in attached and extra:
                changed = await self.update_existing_pivot(key, extra)
                if changed:
                    updated.append(key)
        return {"attached": attached, "detached": detached, "updated": updated}

    async def sync_without_detaching(self, ids: Any) -> dict[str, list[Any]]:
        """Sync without removing ids that are missing from the list."""
        return await self.sync(ids, detaching=False)

    async def toggle(self, ids: Any) -> dict[str, list[Any]]:
        requested = _as_keys(ids)
        current = await self.pivot_ids()
        attach = [key for key in requested if key not in current]
        detach = [key for key in requested if key in current]
        if detach:
            await self.detach(detach)
        if attach:
            await self.attach(attach)
        return {"attached": attach, "detached": detach}

    async def update_existing_pivot(self, identifier: Any, attributes: Mapping[str, Any]) -> int:
        payload = {**dict(attributes), **self._timestamps(fresh=False)}
        if not payload:
            return 0
        return await (
            self._pivot_query()
            .where(self.foreign_pivot_key, "=", self.parent.get_raw_attribute(self.parent_key))
            .where(self.related_pivot_key, "=", identifier)
            .update(payload)
        )

    async def pivot_ids(self) -> list[Any]:
        rows = await (
            self._pivot_query()
            .where(self.foreign_pivot_key, "=", self.parent.get_raw_attribute(self.parent_key))
            .select(self.related_pivot_key)
            .get_raw()
        )
        return [row[self.related_pivot_key] for row in rows]


class HasManyThrough(Relation):
    """`Country -> has_many_through(Post, User)`."""

    def __init__(
        self,
        parent: Model,
        related: type[Model],
        through: type[Model],
        first_key: str | None = None,
        second_key: str | None = None,
    ) -> None:
        super().__init__(parent, related)
        self.through = through
        self.first_key = first_key or type(parent).get_foreign_key()
        self.second_key = second_key or through.get_foreign_key()
        self.local_key = type(parent).primary_key
        self.through_key = through.primary_key

    def _join(self, builder: QueryBuilder) -> QueryBuilder:
        through_table = self.through.get_table()
        related_table = self.related.get_table()
        builder.join(
            through_table,
            f"{through_table}.{self.through_key}",
            "=",
            f"{related_table}.{self.second_key}",
        )
        return builder

    def query(self) -> QueryBuilder:
        builder = self._join(self._related_builder())
        builder.select(sa.literal_column(f"{self.related.get_table()}.*"))
        return builder.where(
            f"{self.through.get_table()}.{self.first_key}",
            "=",
            self.parent.get_raw_attribute(self.local_key),
        )

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        keys = self._keys(models, self.local_key)
        through_table = self.through.get_table()
        builder = self._join(self._related_builder())
        builder.select(sa.literal_column(f"{self.related.get_table()}.*"))
        builder.add_select(
            builder.column(f"{through_table}.{self.first_key}").label(PIVOT_PARENT)
        )
        return builder.where_in(f"{through_table}.{self.first_key}", keys)

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped: dict[Any, list[Any]] = {}
        for item in results:
            marker = item.get_raw_attribute(PIVOT_PARENT)
            item._attributes.pop(PIVOT_PARENT, None)
            grouped.setdefault(marker, []).append(item)
        for model in models:
            key = model.get_raw_attribute(self.local_key)
            model.set_relation(name, Collection(grouped.get(key, [])))

    def existence_query(
        self,
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        builder = self._join(self._related_builder())
        builder._apply_global_scopes(builder)
        if callback is not None:
            callback(builder)
        outer = parent_builder.column(f"{self.parent.get_table()}.{self.local_key}")
        builder._push_where(
            "and",
            builder.column(f"{self.through.get_table()}.{self.first_key}") == outer,
        )
        builder._selects = []
        return builder._base_select([sa.literal(1)])

    def grouping_column(self) -> str:
        return f"{self.through.get_table()}.{self.first_key}"

    def parent_match_key(self) -> str:
        return self.local_key


class HasOneThrough(HasManyThrough):
    async def get(self) -> Any:  # type: ignore[override]
        return await self.query().first()

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped: dict[Any, list[Any]] = {}
        for item in results:
            marker = item.get_raw_attribute(PIVOT_PARENT)
            item._attributes.pop(PIVOT_PARENT, None)
            grouped.setdefault(marker, []).append(item)
        for model in models:
            key = model.get_raw_attribute(self.local_key)
            matches = grouped.get(key, [])
            model.set_relation(name, matches[0] if matches else None)


class MorphOneOrMany(HasOneOrMany):
    """Polymorphic child relation keyed by `{name}_id` / `{name}_type`."""

    def __init__(self, parent: Model, related: type[Model], name: str) -> None:
        super().__init__(parent, related, f"{name}_id", type(parent).primary_key)
        self.morph_name = name
        self.morph_type = f"{name}_type"
        self.morph_class = morph_alias(type(parent))

    def query(self) -> QueryBuilder:
        return super().query().where(self.morph_type, "=", self.morph_class)

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        return super().eager_query(models).where(self.morph_type, "=", self.morph_class)

    def existence_query(
        self,
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        def constrained(builder: QueryBuilder) -> None:
            builder.where(f"{self.related.get_table()}.{self.morph_type}", "=", self.morph_class)
            if callback is not None:  # pragma: no branch
                callback(builder)

        return super().existence_query(parent_builder, constrained)

    async def create(self, attributes: Mapping[str, Any] | None = None, **kwargs: Any) -> Any:
        payload = {**(attributes or {}), **kwargs, self.morph_type: self.morph_class}
        return await super().create(payload)

    def one(self) -> Any:
        """Narrow to a single model, keeping the morph type constraint."""
        relation = MorphOne(self.parent, self.related, self.morph_name)
        return self._copy_state_to(relation)


class MorphMany(MorphOneOrMany):
    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped = self._group(results)
        for model in models:
            matches = grouped.get(model.get_raw_attribute(self.local_key), [])
            if self._chaperone is not None:
                for child in matches:
                    child.set_relation(self._chaperone, model)
            model.set_relation(name, Collection(matches))

    async def get(self) -> Collection[Any]:
        results = await self.query().get()
        self._hydrate_parents(results)
        return results


class MorphOne(MorphOneOrMany):
    async def get(self) -> Any:  # type: ignore[override]
        found = await self.query().first()
        return self._resolve_single([found] if found is not None else [], self.parent)

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        grouped = self._group(results)
        for model in models:
            matches = grouped.get(model.get_raw_attribute(self.local_key), [])
            model.set_relation(name, self._resolve_single(matches, model))


class MorphTo(Relation):
    """Inverse polymorphic relation — resolves `{name}_type` to a model."""

    def __init__(
        self,
        child: Model,
        name: str,
        types: Mapping[str, type[Model]] | None = None,
    ) -> None:
        super().__init__(child, type(child))
        self.morph_name = name
        self.morph_id = f"{name}_id"
        self.morph_type = f"{name}_type"
        # Without an explicit map, fall back to the globally registered one.
        self.types = dict(types) if types is not None else morph_map()

    def _target(self, alias: str | None) -> type[Model] | None:
        return self.types.get(str(alias)) or morph_target(str(alias))

    def query(self) -> QueryBuilder:
        target = self._target(self.parent.get_raw_attribute(self.morph_type))
        if target is None:
            raise LookupError(
                f"Unmapped morph type "
                f"{self.parent.get_raw_attribute(self.morph_type)!r} for {self.morph_name!r}"
            )
        return target.new_query().where(
            target.primary_key, "=", self.parent.get_raw_attribute(self.morph_id)
        )

    async def get(self) -> Any:  # type: ignore[override]
        # A row with no type or no id points at nothing; only a stored type
        # that the map does not know is an error.
        if self.parent.get_raw_attribute(self.morph_id) is None:
            return None
        if not self.parent.get_raw_attribute(self.morph_type):
            return None
        return await self.query().first()

    def existence_query_for(
        self,
        target: type[Model],
        parent_builder: QueryBuilder,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> Any:
        """Existence subquery against one of the morph target tables."""
        builder = target.new_query()
        builder._apply_global_scopes(builder)
        if callback is not None:
            callback(builder)
        outer = parent_builder.column(f"{type(self.parent).get_table()}.{self.morph_id}")
        builder._push_where(
            "and", builder.column(f"{target.get_table()}.{target.primary_key}") == outer
        )
        return builder._base_select([sa.literal(1)])

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:  # pragma: no cover
        raise NotImplementedError("morph_to eager loading uses eager_load_morph_to")

    def match(self, models: Sequence[Model], results: Collection[Any], name: str) -> None:
        raise NotImplementedError  # pragma: no cover

    async def eager_load_into(self, models: Sequence[Model], name: str) -> None:
        buckets: dict[str, list[Model]] = {}
        for model in models:
            alias = model.get_raw_attribute(self.morph_type)
            if alias:  # pragma: no branch
                buckets.setdefault(str(alias), []).append(model)

        for alias, group in buckets.items():
            target = self._target(alias)
            if target is None:
                for model in group:
                    model.set_relation(name, None)
                continue
            keys = [model.get_raw_attribute(self.morph_id) for model in group]
            found = await target.new_query().where_in(target.primary_key, keys).get()
            index = {item.get_raw_attribute(target.primary_key): item for item in found}
            for model in group:
                model.set_relation(name, index.get(model.get_raw_attribute(self.morph_id)))


class MorphToMany(BelongsToMany):
    """Polymorphic many-to-many (`taggables`-style pivot)."""

    def __init__(
        self,
        parent: Model,
        related: type[Model],
        name: str,
        table: str | None = None,
        inverse: bool = False,
    ) -> None:
        pivot = table or f"{name}s"
        morph_owner = related if inverse else type(parent)
        other = type(parent) if inverse else related
        super().__init__(
            parent,
            related,
            table=pivot,
            foreign_pivot_key=f"{name}_id" if not inverse else other.get_foreign_key(),
            related_pivot_key=related.get_foreign_key() if not inverse else f"{name}_id",
        )
        self.morph_name = name
        self.morph_type = f"{name}_type"
        self.inverse = inverse
        self.morph_class = morph_alias(morph_owner if inverse else type(parent))

    def query(self) -> QueryBuilder:
        return super().query().where(f"{self.pivot}.{self.morph_type}", "=", self.morph_class)

    def eager_query(self, models: Sequence[Model]) -> QueryBuilder:
        return (
            super()
            .eager_query(models)
            .where(f"{self.pivot}.{self.morph_type}", "=", self.morph_class)
        )

    async def attach(self, ids: Any, attributes: Mapping[str, Any] | None = None) -> int:
        return await super().attach(ids, {**(attributes or {}), self.morph_type: self.morph_class})

    async def detach(self, ids: Any = None) -> int:
        builder = (
            self._pivot_query()
            .where(self.foreign_pivot_key, "=", self.parent.get_raw_attribute(self.parent_key))
            .where(self.morph_type, "=", self.morph_class)
        )
        if ids is not None:
            builder.where_in(self.related_pivot_key, _as_keys(ids))
        return await builder.delete()


def _as_pairs(ids: Any) -> dict[Any, dict[str, Any]]:
    """Normalize attach/sync ids into `{id: pivot attributes}`."""
    if isinstance(ids, Mapping):
        return {key: dict(value or {}) for key, value in ids.items()}
    return {key: {} for key in _as_keys(ids)}


def _as_keys(ids: Any) -> list[Any]:
    if isinstance(ids, (list, tuple, set, Collection)):
        return [_key_of(item) for item in ids]
    return [_key_of(ids)]


def _key_of(value: Any) -> Any:
    getter = getattr(value, "get_key", None)
    return getter() if callable(getter) else value


__all__ = [
    "BelongsTo",
    "BelongsToMany",
    "HasMany",
    "HasManyThrough",
    "HasOne",
    "HasOneThrough",
    "MorphMany",
    "MorphOne",
    "MorphTo",
    "MorphToMany",
    "Relation",
]
