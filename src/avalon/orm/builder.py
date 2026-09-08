"""Eloquent-shaped query builder over SQLAlchemy Core."""

from __future__ import annotations

import dataclasses
import functools
import inspect
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.sql import ClauseElement
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.selectable import TableClause

from avalon.orm.collection import Collection
from avalon.orm.pagination import Paginator, SimplePaginator

if TYPE_CHECKING:
    from avalon.orm.model import Model

_OPERATORS = {
    "=": lambda c, v: c == v,
    "==": lambda c, v: c == v,
    "!=": lambda c, v: c != v,
    "<>": lambda c, v: c != v,
    ">": lambda c, v: c > v,
    ">=": lambda c, v: c >= v,
    "<": lambda c, v: c < v,
    "<=": lambda c, v: c <= v,
    "like": lambda c, v: c.like(v),
    "not like": lambda c, v: ~c.like(v),
    "ilike": lambda c, v: c.ilike(v),
    "not ilike": lambda c, v: ~c.ilike(v),
    "in": lambda c, v: c.in_(list(v)),
    "not in": lambda c, v: ~c.in_(list(v)),
}

_JOIN_TYPES = {"inner", "left", "right", "cross"}


class _Missing:
    """Sentinel so `where("a", None)` stays distinguishable from omission."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "<missing>"


_MISSING = _Missing()


class ModelNotFoundError(LookupError):
    """Raised by `find_or_fail` / `first_or_fail` when nothing matches."""

    def __init__(self, model: str, identifier: Any = None) -> None:
        self.model = model
        self.identifier = identifier
        suffix = f" with key {identifier!r}" if identifier is not None else ""
        super().__init__(f"No query results for model [{model}]{suffix}.")


@dataclasses.dataclass(frozen=True)
class _Aggregate:
    """One pending `with_count` / `with_sum` / ... on a builder."""

    relation: str
    function: str
    column: str | None
    alias: str
    callback: Callable[[Any], Any] | None = None


def _split_alias(relation: str) -> tuple[str, str, str | None]:
    """Split Laravel's `"posts as published_count"` relation syntax."""
    name, separator, alias = str(relation).partition(" as ")
    return name.strip(), separator, alias.strip() or None


def _morph_targets(relation: Any, types: Any) -> list[tuple[str, Any]]:
    """Resolve `where_has_morph` type arguments to (alias, model) pairs."""
    if types in ("*", None):
        return list(relation.types.items())
    if isinstance(types, Mapping):
        return list(types.items())
    if isinstance(types, str) or not isinstance(types, Iterable):
        types = [types]

    by_model = {model: alias for alias, model in relation.types.items()}
    resolved: list[tuple[str, Any]] = []
    for entry in types:
        if isinstance(entry, str):
            if entry not in relation.types:
                raise LookupError(f"Unmapped morph type {entry!r} for {relation.morph_name!r}")
            resolved.append((entry, relation.types[entry]))
        elif entry in by_model:
            resolved.append((by_model[entry], entry))
        else:
            raise LookupError(f"Unmapped morph type {entry!r} for {relation.morph_name!r}")
    return resolved


def _call_morph_callback(callback: Callable[..., Any], alias: str, builder: Any) -> Any:
    """Morph callbacks may take the type alias as a second argument."""
    try:
        arity = len(inspect.signature(callback).parameters)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        arity = 1
    return callback(builder, alias) if arity >= 2 else callback(builder)


class QueryBuilder:
    """Fluent builder producing models (or dicts for table queries)."""

    def __init__(
        self,
        *,
        model: type[Model] | None = None,
        table: str | None = None,
        connection: str | None = None,
        tables: dict[str, TableClause] | None = None,
    ) -> None:
        if model is None and table is None:
            raise ValueError("QueryBuilder needs either a model or a table name")
        self.model = model
        self.table = table or (model.get_table() if model else "")
        self._connection_name = connection or (model.connection if model else None)
        self._tables: dict[str, TableClause] = tables if tables is not None else {}

        self._wheres: list[tuple[str, ClauseElement]] = []
        self._havings: list[tuple[str, ClauseElement]] = []
        self._orders: list[Any] = []
        self._groups: list[Any] = []
        self._selects: list[Any] = []
        self._joins: list[tuple[str, str, Any]] = []
        self._limit: int | None = None
        self._offset: int | None = None
        self._distinct = False
        self._eager: dict[str, Callable[[QueryBuilder], Any] | None] = {}
        self._eager_counts: list[_Aggregate] = []
        self._without_scopes: set[str] = set()
        self._all_scopes_disabled = False
        self._casts: dict[str, Any] = {}

    # --- plumbing -----------------------------------------------------------

    @classmethod
    def for_table(cls, table: str, connection: str | None = None) -> QueryBuilder:
        return cls(table=table, connection=connection)

    def clone(self) -> QueryBuilder:
        clone = QueryBuilder(
            model=self.model,
            table=self.table,
            connection=self._connection_name,
            tables=self._tables,
        )
        clone._wheres = list(self._wheres)
        clone._havings = list(self._havings)
        clone._orders = list(self._orders)
        clone._groups = list(self._groups)
        clone._selects = list(self._selects)
        clone._joins = list(self._joins)
        clone._limit = self._limit
        clone._offset = self._offset
        clone._distinct = self._distinct
        clone._eager = dict(self._eager)
        clone._eager_counts = list(self._eager_counts)
        clone._without_scopes = set(self._without_scopes)
        clone._all_scopes_disabled = self._all_scopes_disabled
        clone._casts = dict(self._casts)
        return clone

    def _table_clause(self, name: str) -> TableClause:
        if name not in self._tables:
            self._tables[name] = sa.table(name)
        return self._tables[name]

    def column(self, reference: str | ColumnClause | ClauseElement) -> Any:
        """Resolve `"column"` or `"table.column"` into a SQL column."""
        if not isinstance(reference, str):
            return reference
        if "." in reference:
            table_name, _, column_name = reference.rpartition(".")
        else:
            table_name, column_name = self.table, reference
        clause = self._table_clause(table_name)
        if column_name not in clause.c:
            clause.append_column(sa.column(column_name))
        return clause.c[column_name]

    def get_connection(self) -> Any:
        from avalon.orm.facade import get_manager

        return get_manager().connection(self._connection_name)

    # --- where --------------------------------------------------------------

    def _push_where(self, boolean: str, clause: ClauseElement) -> QueryBuilder:
        self._wheres.append((boolean, clause))
        return self

    @staticmethod
    def _operator_and_value(operator: Any, value: Any) -> tuple[Any, Any]:
        """Laravel's two-arg shortcut: the middle argument is `=` when omitted.

        Canonical:  ``where("votes", ">", 100)``
        Shortcut:   ``where("votes", 100)``  →  ``where("votes", "=", 100)``

        The shortcut never inspects the second argument. ``where("op", ">")``
        is ``op = '>'``, not a greater-than with a missing value.
        """
        if value is _MISSING:
            return "=", operator
        return operator, value

    def _condition(self, column: Any, operator: Any, value: Any) -> ClauseElement:
        operator, value = self._operator_and_value(operator, value)
        key = str(operator).strip().lower()
        if key not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {operator!r}")
        return _OPERATORS[key](self.column(column), value)

    def _nested(self, callback: Callable[[QueryBuilder], Any]) -> ClauseElement | None:
        nested = QueryBuilder(
            model=self.model,
            table=self.table,
            connection=self._connection_name,
            tables=self._tables,
        )
        callback(nested)
        return nested._compile_wheres()

    def where(
        self,
        column: str | Callable[[QueryBuilder], Any],
        operator: Any = _MISSING,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """``where("col", "=", val)`` is canonical; ``where("col", val)`` assumes ``=``."""
        if callable(column):
            clause = self._nested(column)
            return self._push_where(boolean, clause) if clause is not None else self
        if operator is _MISSING:
            raise TypeError("where() requires where(column, value) or where(column, operator, value)")
        return self._push_where(boolean, self._condition(column, operator, value))

    def or_where(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        return self.where(column, operator, value, boolean="or")

    def where_in(self, column: str, values: Iterable[Any], boolean: str = "and") -> QueryBuilder:
        return self._push_where(boolean, self.column(column).in_(list(values)))

    def or_where_in(self, column: str, values: Iterable[Any]) -> QueryBuilder:
        return self.where_in(column, values, boolean="or")

    def where_not_in(self, column: str, values: Iterable[Any]) -> QueryBuilder:
        return self._push_where("and", ~self.column(column).in_(list(values)))

    def where_null(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self._push_where(boolean, self.column(column).is_(None))

    def or_where_null(self, column: str) -> QueryBuilder:
        return self.where_null(column, boolean="or")

    def where_not_null(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self._push_where(boolean, self.column(column).isnot(None))

    def or_where_not_null(self, column: str) -> QueryBuilder:
        return self.where_not_null(column, boolean="or")

    def where_between(self, column: str, low: Any, high: Any) -> QueryBuilder:
        return self._push_where("and", self.column(column).between(low, high))

    def where_not_between(self, column: str, low: Any, high: Any) -> QueryBuilder:
        return self._push_where("and", ~self.column(column).between(low, high))

    def where_column(
        self,
        first: str,
        operator: Any,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        operator, second = self._operator_and_value(operator, second)
        key = str(operator).strip().lower()
        return self._push_where("and", _OPERATORS[key](self.column(first), self.column(second)))

    def where_like(self, column: str, pattern: str) -> QueryBuilder:
        return self._push_where("and", self.column(column).like(pattern))

    def _where_date_part(self, part: str, column: str, value: Any) -> QueryBuilder:
        extracted = sa.extract(part, self.column(column))
        return self._push_where("and", extracted == value)

    def where_year(self, column: str, value: Any) -> QueryBuilder:
        return self._where_date_part("year", column, value)

    def where_month(self, column: str, value: Any) -> QueryBuilder:
        return self._where_date_part("month", column, value)

    def where_day(self, column: str, value: Any) -> QueryBuilder:
        return self._where_date_part("day", column, value)

    def where_date(self, column: str, value: Any) -> QueryBuilder:
        return self._push_where("and", sa.func.date(self.column(column)) == value)

    def where_raw(self, sql: str, boolean: str = "and") -> QueryBuilder:
        return self._push_where(boolean, sa.text(sql))

    def where_key(self, value: Any) -> QueryBuilder:
        if self.model is None:
            raise RuntimeError("where_key() requires a model")
        return self.where(self.model.primary_key, "=", value)

    def _compile_wheres(self) -> ClauseElement | None:
        return _combine(self._wheres)

    # --- select / order / group --------------------------------------------

    def select(self, *columns: Any) -> QueryBuilder:
        self._selects = [self.column(item) if isinstance(item, str) else item for item in columns]
        return self

    def add_select(self, *columns: Any) -> QueryBuilder:
        self._selects.extend(
            self.column(item) if isinstance(item, str) else item for item in columns
        )
        return self

    def select_raw(self, sql: str) -> QueryBuilder:
        self._selects.append(sa.literal_column(sql))
        return self

    def distinct(self, value: bool = True) -> QueryBuilder:
        self._distinct = value
        return self

    def order_by(self, column: Any, direction: str = "asc") -> QueryBuilder:
        target = self.column(column)
        self._orders.append(target.desc() if direction.lower() == "desc" else target.asc())
        return self

    def order_by_desc(self, column: Any) -> QueryBuilder:
        return self.order_by(column, "desc")

    def latest(self, column: str | None = None) -> QueryBuilder:
        return self.order_by(column or self._timestamp_column(), "desc")

    def oldest(self, column: str | None = None) -> QueryBuilder:
        return self.order_by(column or self._timestamp_column(), "asc")

    def in_random_order(self) -> QueryBuilder:
        self._orders.append(sa.func.random())
        return self

    def reorder(self, column: Any = None, direction: str = "asc") -> QueryBuilder:
        self._orders = []
        return self.order_by(column, direction) if column is not None else self

    def group_by(self, *columns: Any) -> QueryBuilder:
        self._groups.extend(
            self.column(item) if isinstance(item, str) else item for item in columns
        )
        return self

    def having(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        if not isinstance(column, str):
            self._havings.append(("and", column))
            return self
        if operator is _MISSING:
            raise TypeError("having() requires having(column, value) or having(column, operator, value)")
        operator, value = self._operator_and_value(operator, value)
        key = str(operator).strip().lower()
        if key not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {operator!r}")
        self._havings.append(("and", _OPERATORS[key](self.column(column), value)))
        return self

    def having_raw(self, sql: str) -> QueryBuilder:
        self._havings.append(("and", sa.text(sql)))
        return self

    def limit(self, count: int) -> QueryBuilder:
        self._limit = count
        return self

    def offset(self, count: int) -> QueryBuilder:
        self._offset = count
        return self

    take = limit
    skip = offset

    def for_page(self, page: int, per_page: int) -> QueryBuilder:
        return self.offset(max(page - 1, 0) * per_page).limit(per_page)

    # --- joins --------------------------------------------------------------

    def join(
        self,
        table: str,
        first: str,
        operator: Any = _MISSING,
        second: Any = _MISSING,
        kind: str = "inner",
    ) -> QueryBuilder:
        if kind not in _JOIN_TYPES:
            raise ValueError(f"Unsupported join type: {kind!r}")
        self._table_clause(table)
        if kind == "cross":
            self._joins.append((kind, table, None))
            return self
        operator, second = self._operator_and_value(operator, second)
        key = str(operator).strip().lower()
        if key not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {operator!r}")
        onclause = _OPERATORS[key](self.column(first), self.column(second))
        self._joins.append((kind, table, onclause))
        return self

    def left_join(
        self,
        table: str,
        first: str,
        operator: Any = _MISSING,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        return self.join(table, first, operator, second, kind="left")

    def right_join(
        self,
        table: str,
        first: str,
        operator: Any = _MISSING,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        return self.join(table, first, operator, second, kind="right")

    def cross_join(self, table: str) -> QueryBuilder:
        return self.join(table, "", kind="cross")

    # --- conditional --------------------------------------------------------

    def when(
        self,
        condition: Any,
        callback: Callable[[QueryBuilder], Any],
        default: Callable[[QueryBuilder], Any] | None = None,
    ) -> QueryBuilder:
        if condition:
            callback(self)
        elif default is not None:
            default(self)
        return self

    def unless(
        self,
        condition: Any,
        callback: Callable[[QueryBuilder], Any],
        default: Callable[[QueryBuilder], Any] | None = None,
    ) -> QueryBuilder:
        return self.when(not condition, callback, default)

    def tap(self, callback: Callable[[QueryBuilder], Any]) -> QueryBuilder:
        callback(self)
        return self

    # --- scopes -------------------------------------------------------------

    def without_global_scope(self, name: str) -> QueryBuilder:
        self._without_scopes.add(name)
        return self

    def without_global_scopes(self) -> QueryBuilder:
        self._all_scopes_disabled = True
        return self

    def _apply_global_scopes(self, builder: QueryBuilder) -> QueryBuilder:
        if self.model is None or self._all_scopes_disabled:
            return builder
        for name, scope in self.model.get_global_scopes().items():
            if name not in self._without_scopes:
                scope(builder)
        return builder

    def __getattr__(self, name: str) -> Any:
        # Local scopes: `Post.query().published()` → `scope_published`.
        model = self.__dict__.get("model")
        if model is not None and not name.startswith("_"):
            scope = getattr(model, f"scope_{name}", None)
            if callable(scope):

                def call(*args: Any, **kwargs: Any) -> QueryBuilder:
                    result = _invoke_scope(scope, model, self, args, kwargs)
                    return result if isinstance(result, QueryBuilder) else self

                return call
        raise AttributeError(name)

    # --- eager loading ------------------------------------------------------

    def with_(self, *relations: Any, **constrained: Callable[[QueryBuilder], Any]) -> QueryBuilder:
        for relation in relations:
            if isinstance(relation, dict):
                self._eager.update(relation)
            else:
                self._eager[str(relation)] = None
        self._eager.update(constrained)
        return self

    def without(self, *relations: str) -> QueryBuilder:
        for relation in relations:
            self._eager.pop(relation, None)
        return self

    def with_casts(self, casts: Mapping[str, Any]) -> QueryBuilder:
        """Cast columns for this query only — Laravel's ``withCasts``."""
        clone = self.clone()
        clone._casts.update(casts)
        return clone

    def with_count(self, *relations: Any, **constrained: Callable[[QueryBuilder], Any]) -> Any:
        """Count related rows without loading them — ``withCount``.

        Accepts names, `{"posts as published_count": callback}` mappings, and
        `posts=callback` keywords.
        """
        return self._with_aggregate_group("count", None, relations, constrained)

    def with_exists(self, *relations: Any, **constrained: Callable[[QueryBuilder], Any]) -> Any:
        return self._with_aggregate_group("exists", None, relations, constrained)

    def with_sum(self, relation: Any, column: str, **constrained: Any) -> Any:
        return self._with_aggregate_group("sum", column, (relation,), constrained)

    def with_avg(self, relation: Any, column: str, **constrained: Any) -> Any:
        return self._with_aggregate_group("avg", column, (relation,), constrained)

    def with_min(self, relation: Any, column: str, **constrained: Any) -> Any:
        return self._with_aggregate_group("min", column, (relation,), constrained)

    def with_max(self, relation: Any, column: str, **constrained: Any) -> Any:
        return self._with_aggregate_group("max", column, (relation,), constrained)

    def with_aggregate(
        self,
        relation: str,
        function: str,
        column: str | None = None,
        alias: str | None = None,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> QueryBuilder:
        from avalon.orm.eager import aggregate_alias

        name, _, explicit = _split_alias(relation)
        self._eager_counts.append(
            _Aggregate(
                relation=name,
                function=function,
                column=column,
                alias=alias or explicit or aggregate_alias(name, function, column),
                callback=callback,
            )
        )
        return self

    def _with_aggregate_group(
        self,
        function: str,
        column: str | None,
        relations: Sequence[Any],
        constrained: Mapping[str, Any],
    ) -> QueryBuilder:
        for relation in relations:
            if isinstance(relation, Mapping):
                for name, callback in relation.items():
                    self.with_aggregate(str(name), function, column, callback=callback)
            else:
                self.with_aggregate(str(relation), function, column)
        for name, callback in constrained.items():
            self.with_aggregate(name, function, column, callback=callback)
        return self

    def has(self, relation: str, operator: str = ">=", count: int = 1) -> QueryBuilder:
        return self._relation_existence(relation, operator, count, negate=False)

    def or_has(self, relation: str, operator: str = ">=", count: int = 1) -> QueryBuilder:
        return self._relation_existence(relation, operator, count, negate=False, boolean="or")

    def doesnt_have(self, relation: str) -> QueryBuilder:
        return self._relation_existence(relation, ">=", 1, negate=True)

    def or_doesnt_have(self, relation: str) -> QueryBuilder:
        return self._relation_existence(relation, ">=", 1, negate=True, boolean="or")

    def where_has(
        self,
        relation: str,
        callback: Callable[[QueryBuilder], Any] | None = None,
        operator: str = ">=",
        count: int = 1,
    ) -> QueryBuilder:
        return self._relation_existence(relation, operator, count, negate=False, callback=callback)

    def or_where_has(
        self,
        relation: str,
        callback: Callable[[QueryBuilder], Any] | None = None,
        operator: str = ">=",
        count: int = 1,
    ) -> QueryBuilder:
        return self._relation_existence(
            relation, operator, count, negate=False, callback=callback, boolean="or"
        )

    def where_doesnt_have(
        self,
        relation: str,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> QueryBuilder:
        return self._relation_existence(relation, ">=", 1, negate=True, callback=callback)

    def or_where_doesnt_have(
        self,
        relation: str,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> QueryBuilder:
        return self._relation_existence(
            relation, ">=", 1, negate=True, callback=callback, boolean="or"
        )

    def with_where_has(
        self,
        relation: str,
        callback: Callable[[QueryBuilder], Any] | None = None,
    ) -> QueryBuilder:
        """Filter on a relation and eager load it under the same constraint."""
        self.where_has(relation, callback)
        return self.with_(**{relation: callback}) if callback is not None else self.with_(relation)

    def where_relation(
        self,
        relation: str,
        column: str,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        """Inline existence query — ``whereRelation``."""
        operator, value = self._operator_and_value(operator, value)
        return self.where_has(relation, lambda query: query.where(column, operator, value))

    def or_where_relation(
        self,
        relation: str,
        column: str,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        return self.or_where_has(relation, lambda query: query.where(column, operator, value))

    def _relation_existence(
        self,
        relation: str,
        operator: str,
        count: int,
        *,
        negate: bool,
        callback: Callable[[QueryBuilder], Any] | None = None,
        boolean: str = "and",
    ) -> QueryBuilder:
        if self.model is None:
            raise RuntimeError("Relation constraints require a model")

        head, _, tail = relation.partition(".")
        if tail:
            # "posts.comments" asks for a post that has comments, so the count
            # and the callback belong to the innermost relation.
            def nested(builder: QueryBuilder) -> None:
                builder._relation_existence(tail, operator, count, negate=False, callback=callback)

            return self._relation_existence(
                head, ">=", 1, negate=negate, callback=nested, boolean=boolean
            )

        instance = self.model()
        relation_obj = instance.get_relation(relation)
        subquery = relation_obj.existence_query(self, callback)
        if negate:
            return self._push_where(boolean, ~sa.exists(subquery))
        if operator == ">=" and count <= 1:
            return self._push_where(boolean, sa.exists(subquery))
        counted = subquery.with_only_columns(sa.func.count(), maintain_column_froms=True).order_by(
            None
        )
        return self._push_where(boolean, _OPERATORS[operator](counted.scalar_subquery(), count))

    def _guess_belongs_to(self, related: type[Any]) -> str:
        """Find the `belongs_to` on this model that points at ``related``."""
        from avalon.orm.model import RelationDescriptor
        from avalon.orm.relations import BelongsTo

        assert self.model is not None
        instance = self.model()
        for name in dir(self.model):
            if not isinstance(getattr(self.model, name, None), RelationDescriptor):
                continue
            candidate = instance.get_relation(name)
            if isinstance(candidate, BelongsTo) and candidate.related is related:
                return name
        raise RuntimeError(
            f"{self.model.__name__} has no belongs_to relation to {related.__name__}"
        )

    def where_belongs_to(
        self,
        parent: Any,
        relation: str | None = None,
        boolean: str = "and",
    ) -> QueryBuilder:
        """Constrain to children of a parent model — Laravel's ``whereBelongsTo``.

        Pass one model or many; the relation name is guessed from the parent's
        class when you leave it out.
        """
        from avalon.orm.model import Model as ModelBase

        if self.model is None:
            raise RuntimeError("Relation constraints require a model")

        parents = [parent] if isinstance(parent, ModelBase) else list(parent)
        if not parents:
            raise ValueError("where_belongs_to needs at least one parent model")

        name = relation or self._guess_belongs_to(type(parents[0]))
        relation_obj = self.model().get_relation(name)
        keys = [model.get_raw_attribute(relation_obj.owner_key) for model in parents]
        if len(keys) == 1:
            return self._push_where(boolean, self.column(relation_obj.foreign_key) == keys[0])
        return self._push_where(boolean, self.column(relation_obj.foreign_key).in_(keys))

    def or_where_belongs_to(self, parent: Any, relation: str | None = None) -> QueryBuilder:
        return self.where_belongs_to(parent, relation, boolean="or")

    # --- morph to existence -------------------------------------------------

    def has_morph(
        self,
        relation: str,
        types: Any = "*",
        callback: Callable[..., Any] | None = None,
        *,
        negate: bool = False,
        boolean: str = "and",
    ) -> QueryBuilder:
        """Existence across a `morph_to` relation's possible types."""
        if self.model is None:
            raise RuntimeError("Relation constraints require a model")
        instance = self.model()
        relation_obj = instance.get_relation(relation)
        if not hasattr(relation_obj, "existence_query_for"):
            raise TypeError(f"Relation {relation!r} is not a morph_to relation")

        clauses = []
        for alias, target in _morph_targets(relation_obj, types):
            scoped = None
            if callback is not None:
                scoped = functools.partial(_call_morph_callback, callback, alias)
            subquery = relation_obj.existence_query_for(target, self, scoped)
            morph_type = self.column(f"{self.table}.{relation_obj.morph_type}")
            clauses.append(sa.and_(morph_type == alias, sa.exists(subquery)))

        if not clauses:
            return self._push_where(boolean, sa.false())
        clause = sa.or_(*clauses)
        return self._push_where(boolean, ~clause if negate else clause)

    def or_has_morph(
        self,
        relation: str,
        types: Any = "*",
        callback: Callable[..., Any] | None = None,
    ) -> QueryBuilder:
        return self.has_morph(relation, types, callback, boolean="or")

    def doesnt_have_morph(self, relation: str, types: Any = "*") -> QueryBuilder:
        return self.has_morph(relation, types, negate=True)

    def or_doesnt_have_morph(self, relation: str, types: Any = "*") -> QueryBuilder:
        return self.has_morph(relation, types, negate=True, boolean="or")

    def where_has_morph(
        self,
        relation: str,
        types: Any = "*",
        callback: Callable[..., Any] | None = None,
    ) -> QueryBuilder:
        return self.has_morph(relation, types, callback)

    def or_where_has_morph(
        self,
        relation: str,
        types: Any = "*",
        callback: Callable[..., Any] | None = None,
    ) -> QueryBuilder:
        return self.has_morph(relation, types, callback, boolean="or")

    def where_doesnt_have_morph(
        self,
        relation: str,
        types: Any = "*",
        callback: Callable[..., Any] | None = None,
    ) -> QueryBuilder:
        return self.has_morph(relation, types, callback, negate=True)

    def or_where_doesnt_have_morph(
        self,
        relation: str,
        types: Any = "*",
        callback: Callable[..., Any] | None = None,
    ) -> QueryBuilder:
        return self.has_morph(relation, types, callback, negate=True, boolean="or")

    def where_morph_relation(
        self,
        relation: str,
        types: Any,
        column: str,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        return self.where_has_morph(
            relation, types, lambda query, _type: query.where(column, operator, value)
        )

    def or_where_morph_relation(
        self,
        relation: str,
        types: Any,
        column: str,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        return self.or_where_has_morph(
            relation, types, lambda query, _type: query.where(column, operator, value)
        )

    # --- compilation --------------------------------------------------------

    def _timestamp_column(self) -> str:
        return self.model.created_at if self.model else "created_at"

    def _base_select(self, columns: Sequence[Any] | None = None) -> Any:
        selected = list(columns or self._selects)
        if not selected:
            star = f"{self.table}.*" if self._joins else "*"
            selected = [sa.literal_column(star)]
        statement = sa.select(*selected).select_from(self._table_clause(self.table))

        for kind, table_name, onclause in self._joins:
            target = self._table_clause(table_name)
            if kind == "cross":
                statement = statement.join(target, sa.literal(True))
            elif kind == "left":
                statement = statement.outerjoin(target, onclause)
            else:
                statement = statement.join(target, onclause, isouter=(kind == "right"))

        clause = self._compile_wheres()
        if clause is not None:
            statement = statement.where(clause)
        if self._groups:
            statement = statement.group_by(*self._groups)
        having = _combine(self._havings)
        if having is not None:
            statement = statement.having(having)
        if self._distinct:
            statement = statement.distinct()
        return statement

    def to_select(self) -> Any:
        builder = self.clone()
        self._apply_global_scopes(builder)
        statement = builder._base_select()
        for order in builder._orders:
            statement = statement.order_by(order)
        if builder._limit is not None:
            statement = statement.limit(builder._limit)
        if builder._offset is not None:
            statement = statement.offset(builder._offset)
        return statement

    def to_sql(self) -> str:
        statement = self.to_select()
        try:
            dialect = self.get_connection().engine.dialect
        except Exception:  # noqa: BLE001 — to_sql must work without a connection
            dialect = None
        compiled = statement.compile(
            dialect=dialect,
            compile_kwargs={"literal_binds": True},
        )
        return str(compiled)

    # --- reads --------------------------------------------------------------

    async def get(self) -> Collection[Any]:
        rows = await self.get_raw()
        if self.model is None:
            return Collection(rows)
        models = [self.model._hydrate(row, casts=self._casts) for row in rows]
        if models and (self._eager or self._eager_counts):
            await self._load_eager(models)
        return self.model.new_collection(models)

    async def get_raw(self) -> list[dict[str, Any]]:
        connection = self.get_connection()
        return await connection.select(self.to_select())

    async def _load_eager(self, models: list[Any]) -> None:
        from avalon.orm.eager import eager_load, eager_load_aggregate

        if self._eager:
            await eager_load(models, self._eager)
        for pending in self._eager_counts:
            await eager_load_aggregate(
                models,
                pending.relation,
                pending.alias,
                pending.function,
                pending.column,
                pending.callback,
            )

    async def first(self) -> Any:
        results = await self.clone().limit(1).get()
        return results.first()

    async def first_or_fail(self) -> Any:
        found = await self.first()
        if found is None:
            raise ModelNotFoundError(self.model.__name__ if self.model else self.table)
        return found

    async def find(self, key: Any) -> Any:
        if isinstance(key, (list, tuple, set)):
            return await self.find_many(list(key))
        return await self.clone().where_key(key).first()

    async def find_many(self, keys: Iterable[Any]) -> Collection[Any]:
        if self.model is None:
            raise RuntimeError("find_many() requires a model")
        return await self.clone().where_in(self.model.primary_key, list(keys)).get()

    async def find_or_fail(self, key: Any) -> Any:
        found = await self.find(key)
        if found is None:
            raise ModelNotFoundError(self.model.__name__ if self.model else self.table, key)
        return found

    async def all(self) -> Collection[Any]:
        return await self.get()

    async def value(self, column: str) -> Any:
        row = await self.clone().select(column).limit(1).get_raw()
        if not row:
            return None
        return next(iter(row[0].values()), None)

    async def pluck(self, column: str, key: str | None = None) -> Any:
        columns = [column] if key is None else [key, column]
        rows = await self.clone().select(*columns).get_raw()
        short = column.rpartition(".")[2]
        if key is None:
            return Collection(row.get(short) for row in rows)
        short_key = key.rpartition(".")[2]
        return {row.get(short_key): row.get(short) for row in rows}

    async def exists(self) -> bool:
        statement = sa.select(sa.literal(1)).select_from(
            self.clone().limit(1).to_select().subquery()
        )
        rows = await self.get_connection().select(statement)
        return bool(rows)

    async def doesnt_exist(self) -> bool:
        return not await self.exists()

    async def _aggregate(self, function: Any, column: str | None = None) -> Any:
        builder = self.clone()
        builder._orders = []
        target = sa.literal_column("*") if column is None else builder.column(column)
        statement = builder._apply_global_scopes(builder)._base_select([function(target)])
        rows = await self.get_connection().select(statement)
        return next(iter(rows[0].values()), None) if rows else None

    async def count(self, column: str | None = None) -> int:
        result = await self._aggregate(sa.func.count, column)
        return int(result or 0)

    async def sum(self, column: str) -> Any:
        return await self._aggregate(sa.func.sum, column)

    async def avg(self, column: str) -> Any:
        return await self._aggregate(sa.func.avg, column)

    async def max(self, column: str) -> Any:
        return await self._aggregate(sa.func.max, column)

    async def min(self, column: str) -> Any:
        return await self._aggregate(sa.func.min, column)

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

    async def chunk_by_id(
        self,
        size: int,
        callback: Callable[[Collection[Any]], Any],
        column: str | None = None,
    ) -> bool:
        """Chunk by ascending id, so writes during the walk cannot skip rows.

        Offset paging (:meth:`chunk`) loses rows when the callback updates the
        column it is ordering by; keyset paging does not.
        """
        key = column or self._key_column()
        last: Any = None
        while True:
            query = self.clone().reorder(key, "asc").limit(size)
            if last is not None:
                query = query.where(key, ">", last)
            results = await query.get()
            if not len(results):
                return True
            outcome = callback(results)
            if hasattr(outcome, "__await__"):
                outcome = await outcome
            if outcome is False:
                return False
            last = _value_of(results[-1], key)
            if len(results) < size:
                return True

    async def each_by_id(
        self,
        callback: Callable[[Any], Any],
        size: int = 100,
        column: str | None = None,
    ) -> bool:
        """Walk every row by id, one at a time."""

        async def handle(chunk: Collection[Any]) -> Any:
            for item in chunk:
                outcome = callback(item)
                if hasattr(outcome, "__await__"):
                    outcome = await outcome
                if outcome is False:
                    return False
            return True

        return await self.chunk_by_id(size, handle, column)

    async def lazy(self, size: int = 1000) -> AsyncIterator[Any]:
        """Iterate the whole result set in chunks, yielding one row at a time."""
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

    async def lazy_by_id(self, size: int = 1000, column: str | None = None) -> AsyncIterator[Any]:
        """Like :meth:`lazy`, but paged by ascending id."""
        key = column or self._key_column()
        last: Any = None
        while True:
            query = self.clone().reorder(key, "asc").limit(size)
            if last is not None:
                query = query.where(key, ">", last)
            results = await query.get()
            if not len(results):
                return
            for item in results:
                yield item
            last = _value_of(results[-1], key)
            if len(results) < size:
                return

    async def cursor(self, size: int = 100) -> AsyncIterator[Any]:
        """Stream rows from the database, hydrating one model at a time.

        Unlike :meth:`lazy`, this holds a single result set open instead of
        issuing one query per chunk, so nothing but the current row is in
        memory. Eager loads need the whole set, so they are not applied here.
        """
        connection = self.get_connection()
        async for row in connection.stream(self.to_select(), chunk_size=size):
            yield self.model._hydrate(row, casts=self._casts) if self.model else row

    def _key_column(self) -> str:
        """The column keyset paging should walk."""
        if self.model is not None:
            return self.model.primary_key
        return "id"

    # --- pagination ---------------------------------------------------------

    async def paginate(self, per_page: int | None = None, page: int = 1) -> Paginator:
        size = per_page or (self.model.per_page if self.model else 15)
        total = await self.count()
        items = await self.clone().for_page(page, size).get()
        return Paginator(items, total, size, page)

    async def simple_paginate(self, per_page: int | None = None, page: int = 1) -> SimplePaginator:
        size = per_page or (self.model.per_page if self.model else 15)
        results = await self.clone().for_page(page, size + 1).get()
        has_more = len(results) > size
        return SimplePaginator(results.take(size), size, page, has_more)

    # --- writes -------------------------------------------------------------

    async def insert(self, values: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> int:
        payload = [dict(values)] if isinstance(values, Mapping) else [dict(v) for v in values]
        if not payload:
            return 0
        statement = sa.insert(self._table_clause(self.table))
        for row in payload:
            for key in row:
                self.column(key)
        result = await self.get_connection().execute(statement, payload)
        return int(result.rowcount or 0)

    async def insert_get_id(self, values: Mapping[str, Any]) -> Any:
        row = dict(values)
        for key in row:
            self.column(key)
        primary = self.model.primary_key if self.model else "id"
        connection = self.get_connection()
        statement = sa.insert(self._table_clause(self.table)).values(**row)

        # Lightweight table clauses carry no primary-key metadata, so ask the
        # dialect for RETURNING where it exists and fall back to lastrowid.
        if connection.engine.dialect.insert_returning:
            statement = statement.returning(self.column(primary))
            result = await connection.execute(statement)
            returned = result.scalar()
            if returned is not None:
                return returned
            return row.get(primary)

        result = await connection.execute(statement)
        lastrowid = getattr(result, "lastrowid", None)
        if lastrowid:
            return lastrowid
        return row.get(primary)

    async def update(self, values: Mapping[str, Any]) -> int:
        payload = {key: value for key, value in values.items()}
        for key in payload:
            self.column(key)
        builder = self.clone()
        self._apply_global_scopes(builder)
        statement = sa.update(self._table_clause(self.table)).values(**payload)
        clause = builder._compile_wheres()
        if clause is not None:
            statement = statement.where(clause)
        result = await self.get_connection().execute(statement)
        return int(result.rowcount or 0)

    async def delete(self) -> int:
        builder = self.clone()
        self._apply_global_scopes(builder)
        statement = sa.delete(self._table_clause(self.table))
        clause = builder._compile_wheres()
        if clause is not None:
            statement = statement.where(clause)
        result = await self.get_connection().execute(statement)
        return int(result.rowcount or 0)

    async def increment(self, column: str, amount: int = 1, **extra: Any) -> int:
        target = self.column(column)
        return await self.update({column: target + amount, **extra})

    async def decrement(self, column: str, amount: int = 1, **extra: Any) -> int:
        target = self.column(column)
        return await self.update({column: target - amount, **extra})

    async def upsert(
        self,
        values: Sequence[Mapping[str, Any]] | Mapping[str, Any],
        unique_by: Sequence[str],
        update: Sequence[str] | None = None,
    ) -> int:
        """Insert or update on conflict — dialect-native when the driver supports it.

        ``unique_by`` columns must have a UNIQUE index/constraint (same as Laravel).
        SQLite / PostgreSQL use ``ON CONFLICT … DO UPDATE``; MySQL uses
        ``ON DUPLICATE KEY UPDATE``. Other dialects fall back to probe-then-write.
        """
        payload = [dict(values)] if isinstance(values, Mapping) else [dict(v) for v in values]
        if not payload:
            return 0
        unique = list(unique_by)
        if not unique:
            raise ValueError("upsert() requires unique_by columns")

        for row in payload:
            for key in row:
                self.column(key)
            for key in unique:
                self.column(key)

        columns = update
        if columns is None:
            columns = [key for key in payload[0] if key not in unique]

        dialect = self.get_connection().dialect
        statement = _native_upsert(
            self._table_clause(self.table),
            payload,
            unique,
            list(columns),
            dialect,
        )
        if statement is not None:
            result = await self.get_connection().execute(statement)
            return int(result.rowcount or 0)

        return await self._upsert_probe(payload, unique, list(columns))

    async def _upsert_probe(
        self,
        payload: Sequence[Mapping[str, Any]],
        unique: Sequence[str],
        columns: Sequence[str],
    ) -> int:
        """Fallback for dialects without a native upsert construct."""
        affected = 0
        for row in payload:
            keys = {name: row[name] for name in unique if name in row}
            probe = QueryBuilder(
                model=self.model,
                table=self.table,
                connection=self._connection_name,
            ).without_global_scopes()
            for name, value in keys.items():
                probe.where(name, "=", value)
            if await probe.exists():
                changes = {name: row[name] for name in columns if name in row}
                if changes:  # pragma: no branch
                    affected += await probe.clone().update(changes)
            else:
                affected += await self.clone().insert(row)
        return affected

    async def first_or_create(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> Any:
        probe = self.clone()
        for key, value in attributes.items():
            probe.where(key, "=", value)
        found = await probe.first()
        if found is not None:
            return found
        if self.model is None:
            raise RuntimeError("first_or_create() requires a model")
        return await self.model.create({**attributes, **(values or {})})

    async def first_or_new(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> Any:
        probe = self.clone()
        for key, value in attributes.items():
            probe.where(key, "=", value)
        found = await probe.first()
        if found is not None:
            return found
        if self.model is None:
            raise RuntimeError("first_or_new() requires a model")
        instance = self.model()
        instance.force_fill({**attributes, **(values or {})})
        return instance

    async def update_or_create(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> Any:
        probe = self.clone()
        for key, value in attributes.items():
            probe.where(key, "=", value)
        found = await probe.first()
        if found is not None:
            found.force_fill(dict(values or {}))
            await found.save()
            return found
        if self.model is None:
            raise RuntimeError("update_or_create() requires a model")
        return await self.model.create({**attributes, **(values or {})})


def _native_upsert(
    table: TableClause,
    payload: Sequence[Mapping[str, Any]],
    unique_by: Sequence[str],
    update: Sequence[str],
    dialect: str,
) -> Any | None:
    """Build a dialect-specific upsert statement, or None to fall back."""
    name = str(dialect).lower()
    if name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    elif name in {"postgresql", "postgres"}:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    elif name == "mysql":
        from sqlalchemy.dialects.mysql import insert as dialect_insert
    else:
        return None

    statement = dialect_insert(table).values(list(payload))
    if name == "mysql":
        if not update:
            # MySQL still needs an update clause; no-op assignment on the first key.
            key = unique_by[0]
            return statement.on_duplicate_key_update(**{key: statement.inserted[key]})
        return statement.on_duplicate_key_update(
            **{column: statement.inserted[column] for column in update}
        )

    if not update:
        return statement.on_conflict_do_nothing(index_elements=list(unique_by))
    return statement.on_conflict_do_update(
        index_elements=list(unique_by),
        set_={column: statement.excluded[column] for column in update},
    )


def _invoke_scope(scope: Any, model: type, builder: QueryBuilder, args: tuple, kwargs: dict) -> Any:
    """Laravel local scopes: `scopeXxx($query, ...)` — query is the first argument.

    Accepts a classmethod (`scope_published(cls, query)`), a plain function
    (`scope_published(query)`), or an instance-style `(self, query)`.
    """
    if inspect.ismethod(scope):
        return scope(builder, *args, **kwargs)
    try:
        names = list(inspect.signature(scope).parameters)
    except (TypeError, ValueError):
        names = []
    if names and names[0] in {"self", "cls"}:
        return scope(model, builder, *args, **kwargs)
    return scope(builder, *args, **kwargs)


def _combine(clauses: Sequence[tuple[str, ClauseElement]]) -> ClauseElement | None:
    if not clauses:
        return None
    combined = clauses[0][1]
    for boolean, clause in clauses[1:]:
        combined = sa.or_(combined, clause) if boolean == "or" else sa.and_(combined, clause)
    return combined


def _value_of(row: Any, key: str) -> Any:
    """Read a column from a model or a plain row."""
    getter = getattr(row, "get_raw_attribute", None)
    if callable(getter):
        return getter(key)
    return row[key]
