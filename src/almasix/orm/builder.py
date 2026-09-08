"""Eloquent-shaped query builder over SQLAlchemy Core."""

from __future__ import annotations

import dataclasses
import datetime
import functools
import inspect
import json
import re
from collections.abc import AsyncIterator, Callable, Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy.sql import ClauseElement, operators
from sqlalchemy.sql.elements import ColumnClause
from sqlalchemy.sql.selectable import TableClause

from almasix.orm.collection import Collection
from almasix.orm.dialects import quote_ident
from almasix.orm.grammar import (
    CaseSensitiveLike,
    FullText,
    JsonContains,
    JsonContainsKey,
    JsonLength,
    JsonSet,
    UnsupportedByDialectError,
    VectorDistance,
    is_json_path,
    json_value,
    split_json_path,
)
from almasix.orm.pagination import Paginator, SimplePaginator
from almasix.support.lazy import AsyncLazyCollection

if TYPE_CHECKING:
    from almasix.orm.model import Model

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

#: SQLite keeps autoincrement counters here — but only once one has been used.
_SQLITE_SEQUENCE = "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"

#: One clause object per table name, shared by every builder in the process.
#
# SQLAlchemy decides a subquery is correlated by comparing FROM objects by
# identity, so a subquery that names the outer query's table has to be holding
# the very same clause. Building `sa.table("users")` afresh per builder gives
# two objects that look alike and correlate to nothing.
_TABLE_CLAUSES: dict[str, TableClause] = {}


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


class MultipleRecordsFoundError(LookupError):
    """Raised by `sole` when the query it was promised was unique is not."""

    def __init__(self, model: str, count: int) -> None:
        self.model = model
        self.count = count
        super().__init__(f"{count} records were found for [{model}], not one.")


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
        self._tables: dict[str, TableClause] = tables if tables is not None else _TABLE_CLAUSES

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
        # Subquery aliases belong to one builder, not to every builder that
        # happens to use the same name for something else.
        self._local_tables: dict[str, Any] = {}
        self._from: Any = None
        self._unions: list[tuple[bool, QueryBuilder]] = []
        self._lock: str | None = None
        self._pending_attributes: dict[str, Any] = {}

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
        clone._local_tables = dict(self._local_tables)
        clone._from = self._from
        clone._unions = list(self._unions)
        clone._lock = self._lock
        clone._pending_attributes = dict(self._pending_attributes)
        return clone

    def _table_clause(self, name: str) -> TableClause:
        if name in self._local_tables:
            return self._local_tables[name]
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
        if column_name in clause.c:
            return clause.c[column_name]
        if not hasattr(clause, "append_column"):
            # A subquery alias is fixed once built; name its column directly.
            return sa.literal_column(f"{table_name}.{column_name}")
        clause.append_column(sa.column(column_name))
        return clause.c[column_name]

    def get_connection(self) -> Any:
        from almasix.orm.facade import get_manager

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

    def _comparable(self, reference: Any, sample: Any = None) -> Any:
        """What a comparison reads: a column, a JSON path, or a subquery.

        ``where("options->dining->meal", "salad")`` reaches inside a JSON
        document; the value being compared decides the type it is read back
        as, the way Laravel's JSON where clauses do.
        """
        if isinstance(reference, QueryBuilder):
            return reference.to_select().scalar_subquery()
        if is_json_path(reference):
            name, path = split_json_path(reference)
            return json_value(self.column(name), path, sample)
        return self.column(reference)

    @staticmethod
    def _scalar(value: Any) -> Any:
        """A builder handed in where a value belongs is a scalar subquery."""
        if isinstance(value, QueryBuilder):
            return value.to_select().scalar_subquery()
        return value

    @staticmethod
    def _resolve_operator(operator: Any) -> Callable[[Any, Any], Any]:
        key = str(operator).strip().lower()
        if key not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {operator!r}")
        return _OPERATORS[key]

    def _condition(self, column: Any, operator: Any, value: Any) -> ClauseElement:
        operator, value = self._operator_and_value(operator, value)
        apply = self._resolve_operator(operator)
        return apply(self._comparable(column, value), self._scalar(value))

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
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """``where("col", "=", val)`` is canonical; ``where("col", val)`` assumes ``=``.

        A callable groups its clauses in parentheses, a mapping applies one
        equality per key, and a sequence of triples applies each in turn.
        """
        if callable(column) and not isinstance(column, QueryBuilder):
            clause = self._nested(column)
            return self._push_where(boolean, clause) if clause is not None else self
        if isinstance(column, Mapping):
            return self.where(lambda query: [query.where(k, "=", v) for k, v in column.items()], boolean=boolean)
        if isinstance(column, (list, tuple)) and column and isinstance(column[0], (list, tuple)):
            return self.where(lambda query: [query.where(*entry) for entry in column], boolean=boolean)
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

    def where_not(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """Negate a group of constraints — Laravel's ``whereNot``."""
        probe = QueryBuilder(
            model=self.model,
            table=self.table,
            connection=self._connection_name,
            tables=self._tables,
        )
        probe.where(column, operator, value)
        clause = probe._compile_wheres()
        return self._push_where(boolean, sa.not_(clause)) if clause is not None else self

    def or_where_not(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
    ) -> QueryBuilder:
        return self.where_not(column, operator, value, boolean="or")

    # --- the same constraint across several columns -------------------------

    def _across(
        self,
        columns: Sequence[str],
        operator: Any,
        value: Any,
        *,
        combine: Callable[..., Any],
        negate: bool,
        boolean: str,
    ) -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        clauses = [self._condition(column, operator, value) for column in columns]
        if not clauses:
            return self
        clause = combine(*clauses)
        return self._push_where(boolean, sa.not_(clause) if negate else clause)

    def where_any(
        self,
        columns: Sequence[str],
        operator: Any,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """True when *any* of the columns matches — Laravel's ``whereAny``."""
        return self._across(columns, operator, value, combine=sa.or_, negate=False, boolean=boolean)

    def or_where_any(self, columns: Sequence[str], operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self.where_any(columns, operator, value, boolean="or")

    def where_all(
        self,
        columns: Sequence[str],
        operator: Any,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """True when *every* column matches — Laravel's ``whereAll``."""
        return self._across(columns, operator, value, combine=sa.and_, negate=False, boolean=boolean)

    def or_where_all(self, columns: Sequence[str], operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self.where_all(columns, operator, value, boolean="or")

    def where_none(
        self,
        columns: Sequence[str],
        operator: Any,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """True when *no* column matches — Laravel's ``whereNone``."""
        return self._across(columns, operator, value, combine=sa.or_, negate=True, boolean=boolean)

    def or_where_none(self, columns: Sequence[str], operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self.where_none(columns, operator, value, boolean="or")

    # --- membership ---------------------------------------------------------

    def where_in(
        self,
        column: str,
        values: Iterable[Any] | QueryBuilder,
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """Membership in a list — or in another query's single selected column."""
        target = self._comparable(column, _first_sample(values))
        if isinstance(values, QueryBuilder):
            clause = target.in_(values.to_select().scalar_subquery())
        else:
            clause = target.in_(list(values))
        return self._push_where(boolean, ~clause if negate else clause)

    def or_where_in(self, column: str, values: Iterable[Any] | QueryBuilder) -> QueryBuilder:
        return self.where_in(column, values, boolean="or")

    def where_not_in(
        self,
        column: str,
        values: Iterable[Any] | QueryBuilder,
        boolean: str = "and",
    ) -> QueryBuilder:
        return self.where_in(column, values, boolean=boolean, negate=True)

    def or_where_not_in(self, column: str, values: Iterable[Any] | QueryBuilder) -> QueryBuilder:
        return self.where_in(column, values, boolean="or", negate=True)

    def where_integer_in_raw(
        self,
        column: str,
        values: Iterable[Any],
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """A large integer list inlined rather than bound, one parameter each.

        Every value is cast to `int` first, so nothing but an integer can
        reach the SQL — the same guarantee Laravel's `whereIntegerInRaw` makes.
        """
        inlined = ", ".join(str(int(value)) for value in values)
        if not inlined:
            return self._push_where(boolean, sa.true() if negate else sa.false())
        operator = "not in" if negate else "in"
        rendered = self.column(column).compile(compile_kwargs={"literal_binds": True})
        return self._push_where(boolean, sa.text(f"{rendered} {operator} ({inlined})"))

    def or_where_integer_in_raw(self, column: str, values: Iterable[Any]) -> QueryBuilder:
        return self.where_integer_in_raw(column, values, boolean="or")

    def where_integer_not_in_raw(self, column: str, values: Iterable[Any], boolean: str = "and") -> QueryBuilder:
        return self.where_integer_in_raw(column, values, boolean=boolean, negate=True)

    def or_where_integer_not_in_raw(self, column: str, values: Iterable[Any]) -> QueryBuilder:
        return self.where_integer_in_raw(column, values, boolean="or", negate=True)

    # --- null ---------------------------------------------------------------

    def where_null(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self._push_where(boolean, self._comparable(column).is_(None))

    def or_where_null(self, column: str) -> QueryBuilder:
        return self.where_null(column, boolean="or")

    def where_not_null(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self._push_where(boolean, self._comparable(column).isnot(None))

    def or_where_not_null(self, column: str) -> QueryBuilder:
        return self.where_not_null(column, boolean="or")

    def where_null_safe_equals(self, column: str, value: Any, boolean: str = "and") -> QueryBuilder:
        """Equality that counts two NULLs as equal — Laravel's ``whereNullSafeEquals``."""
        return self._push_where(boolean, self._comparable(column, value).is_not_distinct_from(value))

    def or_where_null_safe_equals(self, column: str, value: Any) -> QueryBuilder:
        return self.where_null_safe_equals(column, value, boolean="or")

    # --- ranges -------------------------------------------------------------

    def where_between(
        self,
        column: str,
        low: Any,
        high: Any = _MISSING,
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """``where_between("votes", 1, 100)`` — or pass the pair as one argument."""
        low, high = _pair(low, high)
        clause = self._comparable(column, low).between(low, high)
        return self._push_where(boolean, ~clause if negate else clause)

    def or_where_between(self, column: str, low: Any, high: Any = _MISSING) -> QueryBuilder:
        return self.where_between(column, low, high, boolean="or")

    def where_not_between(
        self,
        column: str,
        low: Any,
        high: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        return self.where_between(column, low, high, boolean=boolean, negate=True)

    def or_where_not_between(self, column: str, low: Any, high: Any = _MISSING) -> QueryBuilder:
        return self.where_between(column, low, high, boolean="or", negate=True)

    def where_between_columns(
        self,
        column: str,
        columns: Sequence[str],
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """A column between two other columns of the same row."""
        low, high = (self.column(name) for name in columns)
        clause = self._comparable(column).between(low, high)
        return self._push_where(boolean, ~clause if negate else clause)

    def or_where_between_columns(self, column: str, columns: Sequence[str]) -> QueryBuilder:
        return self.where_between_columns(column, columns, boolean="or")

    def where_not_between_columns(self, column: str, columns: Sequence[str], boolean: str = "and") -> QueryBuilder:
        return self.where_between_columns(column, columns, boolean=boolean, negate=True)

    def or_where_not_between_columns(self, column: str, columns: Sequence[str]) -> QueryBuilder:
        return self.where_between_columns(column, columns, boolean="or", negate=True)

    def where_value_between(
        self,
        value: Any,
        columns: Sequence[str],
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """A value between two columns — ``where_value_between(100, ["min", "max"])``."""
        low, high = (self.column(name) for name in columns)
        clause = sa.literal(value).between(low, high)
        return self._push_where(boolean, ~clause if negate else clause)

    def or_where_value_between(self, value: Any, columns: Sequence[str]) -> QueryBuilder:
        return self.where_value_between(value, columns, boolean="or")

    def where_value_not_between(self, value: Any, columns: Sequence[str], boolean: str = "and") -> QueryBuilder:
        return self.where_value_between(value, columns, boolean=boolean, negate=True)

    def or_where_value_not_between(self, value: Any, columns: Sequence[str]) -> QueryBuilder:
        return self.where_value_between(value, columns, boolean="or", negate=True)

    # --- column to column ---------------------------------------------------

    def where_column(
        self,
        first: str,
        operator: Any,
        second: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        operator, second = self._operator_and_value(operator, second)
        apply = self._resolve_operator(operator)
        return self._push_where(boolean, apply(self.column(first), self.column(second)))

    def or_where_column(self, first: str, operator: Any, second: Any = _MISSING) -> QueryBuilder:
        return self.where_column(first, operator, second, boolean="or")

    # --- pattern matching ---------------------------------------------------

    def where_like(
        self,
        column: str,
        pattern: str,
        case_sensitive: bool = False,
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """``LIKE`` that means the same thing on every engine.

        Laravel's default is case-insensitive, which is what most engines do
        anyway and PostgreSQL does not; the insensitive form compiles to
        ``ILIKE`` there and a lowered comparison elsewhere.
        """
        target = self._comparable(column, pattern)
        if case_sensitive:
            return self._push_where(boolean, CaseSensitiveLike(target, pattern, negate=negate))
        clause = target.ilike(pattern)
        return self._push_where(boolean, ~clause if negate else clause)

    def or_where_like(self, column: str, pattern: str, case_sensitive: bool = False) -> QueryBuilder:
        return self.where_like(column, pattern, case_sensitive, boolean="or")

    def where_not_like(
        self,
        column: str,
        pattern: str,
        case_sensitive: bool = False,
        boolean: str = "and",
    ) -> QueryBuilder:
        return self.where_like(column, pattern, case_sensitive, boolean=boolean, negate=True)

    def or_where_not_like(self, column: str, pattern: str, case_sensitive: bool = False) -> QueryBuilder:
        return self.where_like(column, pattern, case_sensitive, boolean="or", negate=True)

    # --- dates and times ----------------------------------------------------

    def _where_date_part(
        self,
        part: str,
        column: str,
        operator: Any,
        value: Any,
        boolean: str,
    ) -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        apply = self._resolve_operator(operator)
        extracted = sa.extract(part, self._comparable(column))
        return self._push_where(boolean, apply(extracted, value))

    def where_year(self, column: str, operator: Any, value: Any = _MISSING, boolean: str = "and") -> QueryBuilder:
        return self._where_date_part("year", column, operator, value, boolean)

    def or_where_year(self, column: str, operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self._where_date_part("year", column, operator, value, "or")

    def where_month(self, column: str, operator: Any, value: Any = _MISSING, boolean: str = "and") -> QueryBuilder:
        return self._where_date_part("month", column, operator, value, boolean)

    def or_where_month(self, column: str, operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self._where_date_part("month", column, operator, value, "or")

    def where_day(self, column: str, operator: Any, value: Any = _MISSING, boolean: str = "and") -> QueryBuilder:
        return self._where_date_part("day", column, operator, value, boolean)

    def or_where_day(self, column: str, operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self._where_date_part("day", column, operator, value, "or")

    def where_date(self, column: str, operator: Any, value: Any = _MISSING, boolean: str = "and") -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        apply = self._resolve_operator(operator)
        target = sa.func.date(self._comparable(column))
        return self._push_where(boolean, apply(target, _as_date_text(value)))

    def or_where_date(self, column: str, operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self.where_date(column, operator, value, boolean="or")

    def where_time(self, column: str, operator: Any, value: Any = _MISSING, boolean: str = "and") -> QueryBuilder:
        operator, value = self._operator_and_value(operator, value)
        apply = self._resolve_operator(operator)
        target = sa.func.time(self._comparable(column))
        return self._push_where(boolean, apply(target, _as_time_text(value)))

    def or_where_time(self, column: str, operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self.where_time(column, operator, value, boolean="or")

    def where_past(self, column: str, boolean: str = "and") -> QueryBuilder:
        """A moment already gone — the column is before now."""
        return self.where(column, "<", _clock_now(), boolean=boolean)

    def or_where_past(self, column: str) -> QueryBuilder:
        return self.where_past(column, boolean="or")

    def where_future(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where(column, ">", _clock_now(), boolean=boolean)

    def or_where_future(self, column: str) -> QueryBuilder:
        return self.where_future(column, boolean="or")

    def where_now_or_past(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where(column, "<=", _clock_now(), boolean=boolean)

    def or_where_now_or_past(self, column: str) -> QueryBuilder:
        return self.where_now_or_past(column, boolean="or")

    def where_now_or_future(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where(column, ">=", _clock_now(), boolean=boolean)

    def or_where_now_or_future(self, column: str) -> QueryBuilder:
        return self.where_now_or_future(column, boolean="or")

    def where_today(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where_date(column, "=", _clock_today(), boolean=boolean)

    def or_where_today(self, column: str) -> QueryBuilder:
        return self.where_today(column, boolean="or")

    def where_before_today(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where_date(column, "<", _clock_today(), boolean=boolean)

    def or_where_before_today(self, column: str) -> QueryBuilder:
        return self.where_before_today(column, boolean="or")

    def where_after_today(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where_date(column, ">", _clock_today(), boolean=boolean)

    def or_where_after_today(self, column: str) -> QueryBuilder:
        return self.where_after_today(column, boolean="or")

    def where_today_or_before(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where_date(column, "<=", _clock_today(), boolean=boolean)

    def or_where_today_or_before(self, column: str) -> QueryBuilder:
        return self.where_today_or_before(column, boolean="or")

    def where_today_or_after(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where_date(column, ">=", _clock_today(), boolean=boolean)

    def or_where_today_or_after(self, column: str) -> QueryBuilder:
        return self.where_today_or_after(column, boolean="or")

    # --- existence ----------------------------------------------------------

    def where_exists(
        self,
        query: QueryBuilder | Any,
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """Correlate against another query — Laravel's ``whereExists``.

        Laravel hands a closure a table-less builder that has to call `from`
        anyway; Almasix takes the built query, so `DB.table("orders")…` is the
        whole subquery and correlation is an ordinary `where_column`.
        """
        statement = query.to_select() if isinstance(query, QueryBuilder) else query
        clause = sa.exists(statement)
        return self._push_where(boolean, ~clause if negate else clause)

    def or_where_exists(self, query: QueryBuilder | Any) -> QueryBuilder:
        return self.where_exists(query, boolean="or")

    def where_not_exists(self, query: QueryBuilder | Any, boolean: str = "and") -> QueryBuilder:
        return self.where_exists(query, boolean=boolean, negate=True)

    def or_where_not_exists(self, query: QueryBuilder | Any) -> QueryBuilder:
        return self.where_exists(query, boolean="or", negate=True)

    # --- JSON ---------------------------------------------------------------

    def where_json_contains(
        self,
        column: str,
        value: Any,
        boolean: str = "and",
        negate: bool = False,
    ) -> QueryBuilder:
        """Is this value in the JSON array at ``column``?"""
        name, path = split_json_path(column)
        clause = JsonContains(self.column(name), value, path)
        return self._push_where(boolean, sa.not_(clause) if negate else clause)

    def or_where_json_contains(self, column: str, value: Any) -> QueryBuilder:
        return self.where_json_contains(column, value, boolean="or")

    def where_json_doesnt_contain(self, column: str, value: Any, boolean: str = "and") -> QueryBuilder:
        return self.where_json_contains(column, value, boolean=boolean, negate=True)

    def or_where_json_doesnt_contain(self, column: str, value: Any) -> QueryBuilder:
        return self.where_json_contains(column, value, boolean="or", negate=True)

    def where_json_contains_key(self, column: str, boolean: str = "and", negate: bool = False) -> QueryBuilder:
        """Does the document have this key, whatever its value?"""
        name, path = split_json_path(column)
        clause = JsonContainsKey(self.column(name), path)
        return self._push_where(boolean, sa.not_(clause) if negate else clause)

    def or_where_json_contains_key(self, column: str) -> QueryBuilder:
        return self.where_json_contains_key(column, boolean="or")

    def where_json_doesnt_contain_key(self, column: str, boolean: str = "and") -> QueryBuilder:
        return self.where_json_contains_key(column, boolean=boolean, negate=True)

    def or_where_json_doesnt_contain_key(self, column: str) -> QueryBuilder:
        return self.where_json_contains_key(column, boolean="or", negate=True)

    def where_json_length(
        self,
        column: str,
        operator: Any,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        """How many entries the JSON array holds."""
        operator, value = self._operator_and_value(operator, value)
        apply = self._resolve_operator(operator)
        name, path = split_json_path(column)
        return self._push_where(boolean, apply(JsonLength(self.column(name), path), value))

    def or_where_json_length(self, column: str, operator: Any, value: Any = _MISSING) -> QueryBuilder:
        return self.where_json_length(column, operator, value, boolean="or")

    # --- full text ----------------------------------------------------------

    def where_full_text(
        self,
        columns: str | Sequence[str],
        value: str,
        mode: str = "natural",
        language: str = "english",
        boolean: str = "and",
    ) -> QueryBuilder:
        """A match against a full-text index — MySQL/MariaDB and PostgreSQL."""
        names = [columns] if isinstance(columns, str) else list(columns)
        clause = FullText([self.column(name) for name in names], value, mode, language)
        return self._push_where(boolean, clause)

    def or_where_full_text(
        self,
        columns: str | Sequence[str],
        value: str,
        mode: str = "natural",
        language: str = "english",
    ) -> QueryBuilder:
        return self.where_full_text(columns, value, mode, language, boolean="or")

    # --- vector similarity --------------------------------------------------

    def where_vector_similar_to(
        self,
        column: str,
        vector: Any,
        min_similarity: float = 0.0,
        order: bool = True,
        boolean: str = "and",
    ) -> QueryBuilder:
        """Rows whose vector is close to ``vector`` — pgvector and MariaDB.

        ``min_similarity`` runs 0.0 to 1.0, where 1.0 is identical. Results
        are ordered most-similar-first unless ``order=False``.

        Almasix takes a vector, never a phrase: Laravel embeds a plain string
        through its AI SDK, and Almasix has no equivalent to embed with.
        """
        distance = VectorDistance(self.column(column), vector)
        self._push_where(boolean, distance <= (1.0 - min_similarity))
        if order:
            self._orders.append(distance.asc())
        return self

    def select_vector_distance(self, column: str, vector: Any, alias: str = "distance") -> QueryBuilder:
        """Add the cosine distance to the selected columns."""
        self._selects.append(VectorDistance(self.column(column), vector).label(alias))
        return self

    def where_vector_distance_less_than(
        self,
        column: str,
        vector: Any,
        max_distance: float,
        boolean: str = "and",
    ) -> QueryBuilder:
        distance = VectorDistance(self.column(column), vector)
        return self._push_where(boolean, distance < max_distance)

    def order_by_vector_distance(self, column: str, vector: Any, direction: str = "asc") -> QueryBuilder:
        distance = VectorDistance(self.column(column), vector)
        self._orders.append(distance.desc() if direction.lower() == "desc" else distance.asc())
        return self

    # --- raw ----------------------------------------------------------------

    def where_raw(
        self,
        sql: str,
        boolean: str = "and",
        bindings: Mapping[str, Any] | None = None,
    ) -> QueryBuilder:
        """Raw SQL, with `:name` placeholders bound rather than interpolated."""
        clause = sa.text(sql)
        if bindings:
            clause = clause.bindparams(**dict(bindings))
        return self._push_where(boolean, clause)

    def or_where_raw(self, sql: str, bindings: Mapping[str, Any] | None = None) -> QueryBuilder:
        return self.where_raw(sql, boolean="or", bindings=bindings)

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
        """Raw SQL as a selected column; a trailing ``as name`` names the result."""
        expression, alias = _split_select_alias(sql)
        column = sa.literal_column(expression)
        self._selects.append(column.label(alias) if alias else column)
        return self

    def distinct(self, value: bool = True) -> QueryBuilder:
        self._distinct = value
        return self

    def select_sub(self, query: QueryBuilder | Any, alias: str) -> QueryBuilder:
        """Add a subquery as a selected column — Laravel's ``selectSub``."""
        statement = query.to_select() if isinstance(query, QueryBuilder) else query
        self._selects.append(statement.scalar_subquery().label(alias))
        return self

    def add_select_sub(self, query: QueryBuilder | Any, alias: str) -> QueryBuilder:
        return self.select_sub(query, alias)

    def order_by(self, column: Any, direction: str = "asc") -> QueryBuilder:
        target = self._orderable(column)
        self._orders.append(target.desc() if direction.lower() == "desc" else target.asc())
        return self

    def _orderable(self, column: Any) -> Any:
        """What an ordering reads — a column, a JSON path, or a subquery."""
        if isinstance(column, QueryBuilder):
            return column.to_select().scalar_subquery()
        if is_json_path(column):
            name, path = split_json_path(column)
            return json_value(self.column(name), path, None)
        return self.column(column)

    def order_by_desc(self, column: Any) -> QueryBuilder:
        return self.order_by(column, "desc")

    def order_by_sub(self, query: QueryBuilder | Any, direction: str = "asc") -> QueryBuilder:
        """Order by what a correlated subquery returns."""
        return self.order_by(query, direction)

    def order_by_raw(self, sql: str) -> QueryBuilder:
        self._orders.append(sa.text(sql))
        return self

    def group_by_raw(self, sql: str) -> QueryBuilder:
        self._groups.append(sa.text(sql))
        return self

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

    def reorder_desc(self, column: Any) -> QueryBuilder:
        return self.reorder(column, "desc")

    def group_by(self, *columns: Any) -> QueryBuilder:
        self._groups.extend(
            self.column(item) if isinstance(item, str) else item for item in columns
        )
        return self

    def _having_column(self, column: str) -> Any:
        """A `having` usually names an aggregate this query gave a name to."""
        for selected in self._selects:
            if isinstance(selected, sa.Label) and selected.name == column:
                return selected.element
        return self.column(column)

    def having(
        self,
        column: Any,
        operator: Any = _MISSING,
        value: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        if not isinstance(column, str):
            self._havings.append((boolean, column))
            return self
        if operator is _MISSING:
            raise TypeError("having() requires having(column, value) or having(column, operator, value)")
        operator, value = self._operator_and_value(operator, value)
        apply = self._resolve_operator(operator)
        self._havings.append((boolean, apply(self._having_column(column), value)))
        return self

    def or_having(self, column: Any, operator: Any = _MISSING, value: Any = _MISSING) -> QueryBuilder:
        return self.having(column, operator, value, boolean="or")

    def having_between(
        self,
        column: str,
        low: Any,
        high: Any = _MISSING,
        boolean: str = "and",
    ) -> QueryBuilder:
        low, high = _pair(low, high)
        self._havings.append((boolean, self._having_column(column).between(low, high)))
        return self

    def or_having_between(self, column: str, low: Any, high: Any = _MISSING) -> QueryBuilder:
        return self.having_between(column, low, high, boolean="or")

    def having_raw(self, sql: str, boolean: str = "and") -> QueryBuilder:
        self._havings.append((boolean, sa.text(sql)))
        return self

    def or_having_raw(self, sql: str) -> QueryBuilder:
        return self.having_raw(sql, boolean="or")

    def having_null(self, column: str, boolean: str = "and") -> QueryBuilder:
        self._havings.append((boolean, self._having_column(column).is_(None)))
        return self

    def having_not_null(self, column: str, boolean: str = "and") -> QueryBuilder:
        self._havings.append((boolean, self._having_column(column).isnot(None)))
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
        first: str | Callable[[JoinClause], Any] = "",
        operator: Any = _MISSING,
        second: Any = _MISSING,
        kind: str = "inner",
    ) -> QueryBuilder:
        """Join a table on one condition, or on a clause a callable builds.

        ``join("contacts", "users.id", "=", "contacts.user_id")`` is the short
        form; pass a callable instead and it receives a :class:`JoinClause`
        that takes `on` / `or_on` and the whole `where` family, the way
        Laravel's advanced join clauses do.
        """
        if kind not in _JOIN_TYPES:
            raise ValueError(f"Unsupported join type: {kind!r}")
        self._table_clause(table)
        if kind == "cross":
            self._joins.append((kind, table, None))
            return self
        if callable(first):
            clause = JoinClause(
                table=table,
                connection=self._connection_name,
                tables=self._tables,
            )
            clause._local_tables = self._local_tables
            first(clause)
            onclause = clause._compile_wheres()
            if onclause is None:
                raise ValueError(f"The join on {table!r} has no condition.")
        else:
            operator, second = self._operator_and_value(operator, second)
            onclause = self._resolve_operator(operator)(self.column(first), self.column(second))
        self._joins.append((kind, table, onclause))
        return self

    def left_join(
        self,
        table: str,
        first: str | Callable[[JoinClause], Any] = "",
        operator: Any = _MISSING,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        return self.join(table, first, operator, second, kind="left")

    def right_join(
        self,
        table: str,
        first: str | Callable[[JoinClause], Any] = "",
        operator: Any = _MISSING,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        return self.join(table, first, operator, second, kind="right")

    def cross_join(self, table: str) -> QueryBuilder:
        return self.join(table, "", kind="cross")

    # --- subquery and lateral joins ------------------------------------------

    def _alias_subquery(self, query: QueryBuilder | Any, alias: str) -> Any:
        """Name a subquery so its columns can be reached as ``alias.column``."""
        statement = query.to_select() if isinstance(query, QueryBuilder) else query
        aliased = statement.subquery(alias)
        self._local_tables[alias] = aliased
        return aliased

    def join_sub(
        self,
        query: QueryBuilder | Any,
        alias: str,
        first: str | Callable[[JoinClause], Any] = "",
        operator: Any = _MISSING,
        second: Any = _MISSING,
        kind: str = "inner",
    ) -> QueryBuilder:
        """Join a subquery under a name — Laravel's ``joinSub``."""
        self._alias_subquery(query, alias)
        return self.join(alias, first, operator, second, kind=kind)

    def left_join_sub(
        self,
        query: QueryBuilder | Any,
        alias: str,
        first: str | Callable[[JoinClause], Any] = "",
        operator: Any = _MISSING,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        return self.join_sub(query, alias, first, operator, second, kind="left")

    def right_join_sub(
        self,
        query: QueryBuilder | Any,
        alias: str,
        first: str | Callable[[JoinClause], Any] = "",
        operator: Any = _MISSING,
        second: Any = _MISSING,
    ) -> QueryBuilder:
        return self.join_sub(query, alias, first, operator, second, kind="right")

    def cross_join_sub(self, query: QueryBuilder | Any, alias: str) -> QueryBuilder:
        self._alias_subquery(query, alias)
        return self.join(alias, "", kind="cross")

    def join_lateral(
        self,
        query: QueryBuilder | Any,
        alias: str,
        kind: str = "inner",
    ) -> QueryBuilder:
        """Join a subquery that may read the outer row — ``joinLateral``.

        A lateral join carries no `on` clause of its own; the subquery says
        what it correlates with, so the join condition is simply true.
        """
        statement = query.to_select() if isinstance(query, QueryBuilder) else query
        lateral = statement.lateral(alias)
        self._local_tables[alias] = lateral
        self._joins.append((kind, alias, sa.true()))
        return self

    def left_join_lateral(self, query: QueryBuilder | Any, alias: str) -> QueryBuilder:
        return self.join_lateral(query, alias, kind="left")

    def from_sub(self, query: QueryBuilder | Any, alias: str) -> QueryBuilder:
        """Select from a subquery instead of a table — Laravel's ``fromSub``."""
        self._from = self._alias_subquery(query, alias)
        self.table = alias
        return self

    # --- unions ---------------------------------------------------------------

    def union(self, query: QueryBuilder, all_rows: bool = False) -> QueryBuilder:
        """Append another query's rows — duplicates dropped unless ``all_rows``."""
        self._unions.append((all_rows, query))
        return self

    def union_all(self, query: QueryBuilder) -> QueryBuilder:
        return self.union(query, all_rows=True)

    # --- pessimistic locking --------------------------------------------------

    def lock_for_update(self) -> QueryBuilder:
        """Hold the selected rows against other writers until this commits."""
        self._lock = "update"
        return self

    def shared_lock(self) -> QueryBuilder:
        """Hold the selected rows against other writers' updates, not reads."""
        self._lock = "share"
        return self

    def lock(self, value: bool | str = True) -> QueryBuilder:
        """``lock(True)`` is `for update`, ``lock(False)`` releases the intent."""
        if value is True:
            return self.lock_for_update()
        if value is False:
            self._lock = None
            return self
        self._lock = str(value)
        return self

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
        """Apply reusable query logic and keep building — Laravel's ``tap``."""
        callback(self)
        return self

    def with_attributes(
        self,
        values: Mapping[str, Any],
        as_conditions: bool = True,
    ) -> QueryBuilder:
        """Constrain on attributes *and* seed them on anything this query creates.

        Laravel's ``withAttributes`` is what makes a scoped relationship whole:
        a query that only finds published posts should also produce published
        posts. Pass ``as_conditions=False`` to seed without filtering.
        """
        self._pending_attributes.update(values)
        if as_conditions:
            for key, value in values.items():
                self.where(key, "=", value)
        return self

    def pending_attributes(self) -> dict[str, Any]:
        """The attributes this query seeds onto models it creates."""
        return dict(self._pending_attributes)

    def pipe(self, callback: Callable[[QueryBuilder], Any]) -> Any:
        """Hand the query to something that returns a result of its own.

        Where `tap` always gives the builder back, `pipe` gives back whatever
        the callable returns — a paginator, a count, a coroutine to await.
        """
        return callback(self)

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
        from almasix.orm.eager import aggregate_alias

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
        from almasix.orm.model import RelationDescriptor
        from almasix.orm.relations import BelongsTo

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
        from almasix.orm.model import Model as ModelBase

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
        source = self._from if self._from is not None else self._table_clause(self.table)
        for kind, table_name, onclause in self._joins:
            target = self._table_clause(table_name)
            if kind == "cross":
                source = sa.join(source, target, sa.literal(True))
            elif kind == "right":
                # SQLAlchemy has no right join, and none is needed: the same
                # rows come back from a left join with the sides swapped.
                source = sa.join(target, source, onclause, isouter=True)
            else:
                source = sa.join(source, target, onclause, isouter=(kind == "left"))
        statement = sa.select(*selected).select_from(source)

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
        orders = builder._orders
        if builder._unions:
            # Ordering and paging belong to the combined result, not to the
            # first query in it, which is where Laravel puts them too — and a
            # combined result has no table names left to qualify columns with.
            for all_rows, other in builder._unions:
                combine = statement.union_all if all_rows else statement.union
                statement = combine(other.to_select())
            orders = [_unqualified(order) for order in orders]
        for order in orders:
            statement = statement.order_by(order)
        if builder._limit is not None:
            statement = statement.limit(builder._limit)
        if builder._offset is not None:
            statement = statement.offset(builder._offset)
        if builder._lock is not None:
            statement = statement.with_for_update(read=builder._lock == "share")
        return statement

    def _dialect(self) -> Any:
        """The dialect to compile for, or None before a connection exists."""
        try:
            return self.get_connection().engine.dialect
        except Exception:  # noqa: BLE001 — compiling must work without a connection
            return None

    def _compiled(self, *, literal: bool) -> Any:
        kwargs = {"literal_binds": True} if literal else {}
        return self.to_select().compile(dialect=self._dialect(), compile_kwargs=kwargs)

    def to_sql(self) -> str:
        """The SQL, with the values left as placeholders — Laravel's ``toSql``."""
        return str(self._compiled(literal=False))

    def to_raw_sql(self) -> str:
        """The SQL with every value written in — Laravel's ``toRawSql``."""
        return str(self._compiled(literal=True))

    def get_bindings(self) -> list[Any]:
        """The values the placeholders in :meth:`to_sql` stand for."""
        compiled = self._compiled(literal=False)
        return [compiled.params[key] for key in compiled.positiontup or compiled.params]

    # --- debugging ----------------------------------------------------------

    def dump(self) -> QueryBuilder:
        """Print the SQL and its bindings, then carry on building."""
        from almasix.debug import dump as debug_dump

        debug_dump({"sql": self.to_sql(), "bindings": self.get_bindings()}, _depth=2)
        return self

    def dd(self) -> None:
        """Print the SQL and its bindings, then stop."""
        from almasix.debug import dd as debug_dd

        debug_dd({"sql": self.to_sql(), "bindings": self.get_bindings()})

    def dump_raw_sql(self) -> QueryBuilder:
        """Print the SQL with its values written in, then carry on."""
        from almasix.debug import dump as debug_dump

        debug_dump(self.to_raw_sql(), _depth=2)
        return self

    def dd_raw_sql(self) -> None:
        """Print the SQL with its values written in, then stop."""
        from almasix.debug import dd as debug_dd

        debug_dd(self.to_raw_sql())

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
        from almasix.orm.eager import eager_load, eager_load_aggregate

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

    async def sole(self) -> Any:
        """The one matching row — anything else is a mistake worth raising.

        Two rows mean the query was not as narrow as the caller believed, and
        silently taking the first would hide that.
        """
        results = await self.clone().limit(2).get()
        name = self.model.__name__ if self.model else self.table
        if not len(results):
            raise ModelNotFoundError(name)
        if len(results) > 1:
            raise MultipleRecordsFoundError(name, len(results))
        return results.first()

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

    async def implode(self, column: str, glue: str = "") -> str:
        """Join one column's values into a string — Laravel's ``implode``."""
        values = await self.pluck(column)
        return glue.join("" if value is None else str(value) for value in values)

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

    average = avg

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

    async def _stream_lazy_by_id(self, size: int = 1000, column: str | None = None) -> AsyncIterator[Any]:
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

    async def _stream_cursor(self, size: int = 100) -> AsyncIterator[Any]:
        connection = self.get_connection()
        async for row in connection.stream(self.to_select(), chunk_size=size):
            yield self.model._hydrate(row, casts=self._casts) if self.model else row

    def lazy(self, size: int = 1000) -> AsyncLazyCollection:
        """Walk the whole result set one row at a time, a chunk per query.

        Returns a lazy collection, so ``async for`` reads rows as they arrive
        and `map` / `filter` / `chunk` apply without buffering the result set.
        """
        return AsyncLazyCollection(functools.partial(self._stream_lazy, size))

    def lazy_by_id(self, size: int = 1000, column: str | None = None) -> AsyncLazyCollection:
        """Like :meth:`lazy`, but paged by ascending id."""
        return AsyncLazyCollection(functools.partial(self._stream_lazy_by_id, size, column))

    def cursor(self, size: int = 100) -> AsyncLazyCollection:
        """Stream rows from the database, hydrating one model at a time.

        Unlike :meth:`lazy`, this holds a single result set open instead of
        issuing one query per chunk, so nothing but the current row is in
        memory. Eager loads need the whole set, so they are not applied here.
        """
        return AsyncLazyCollection(functools.partial(self._stream_cursor, size))

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
        payload = _writable_rows(values)
        if not payload:
            return 0
        statement = sa.insert(self._table_clause(self.table))
        for row in payload:
            for key in row:
                self.column(key)
        result = await self.get_connection().execute(statement, payload)
        return int(result.rowcount or 0)

    async def insert_or_ignore(
        self,
        values: Mapping[str, Any] | Sequence[Mapping[str, Any]],
    ) -> int:
        """Insert, letting rows that would collide fall on the floor."""
        payload = _writable_rows(values)
        if not payload:
            return 0
        for row in payload:
            for key in row:
                self.column(key)
        statement = _ignoring_insert(self._table_clause(self.table), payload, self.get_connection().dialect)
        result = await self.get_connection().execute(statement)
        return int(result.rowcount or 0)

    async def insert_using(self, columns: Sequence[str], query: QueryBuilder | Any) -> int:
        """Fill a table from another query — ``INSERT INTO … SELECT …``."""
        target = self._table_clause(self.table)
        for name in columns:
            self.column(name)
        source = query.to_select() if isinstance(query, QueryBuilder) else query
        statement = sa.insert(target).from_select([self.column(name) for name in columns], source)
        result = await self.get_connection().execute(statement)
        return int(result.rowcount or 0)

    async def insert_get_id(self, values: Mapping[str, Any]) -> Any:
        row = _writable_rows(values)[0]
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
        """Update the matching rows; ``"options->key"`` writes inside a JSON column."""
        payload: dict[str, Any] = {}
        patches: dict[str, list[tuple[list[str], Any]]] = {}
        for key, value in values.items():
            if is_json_path(key):
                name, path = split_json_path(key)
                patches.setdefault(name, []).append((path, value))
                continue
            payload[key] = _writable_value(value)
        for name, edits in patches.items():
            payload[name] = _json_set(self.column(name), edits)
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

    async def update_or_insert(
        self,
        attributes: Mapping[str, Any],
        values: Mapping[str, Any] | None = None,
    ) -> bool:
        """Update the row matching ``attributes``, or insert it — ``updateOrInsert``.

        Returns True either way, as Laravel does; ask `exists` beforehand if
        you need to know which of the two happened.
        """
        probe = self.clone()
        for key, value in attributes.items():
            probe.where(key, "=", value)
        if not values:
            if await probe.exists():
                return True
            await self.clone().insert(dict(attributes))
            return True
        if await probe.exists():
            await probe.clone().update(dict(values))
            return True
        await self.clone().insert({**attributes, **values})
        return True

    async def delete(self, key: Any = _MISSING) -> int:
        """Delete the matching rows, or the one row with this primary key."""
        builder = self.clone()
        if key is not _MISSING:
            builder.where(builder._key_column(), "=", key)
        self._apply_global_scopes(builder)
        statement = sa.delete(self._table_clause(self.table))
        clause = builder._compile_wheres()
        if clause is not None:
            statement = statement.where(clause)
        result = await self.get_connection().execute(statement)
        return int(result.rowcount or 0)

    async def truncate(self) -> None:
        """Empty the table and reset its auto-increment, where the engine can."""
        connection = self.get_connection()
        dialect = connection.engine.dialect
        for sql in _truncate_sql(self.table, dialect):
            await connection.execute(sql)
        if dialect.name == "sqlite" and await connection.scalar(_SQLITE_SEQUENCE):
            # The sequence table only exists once something has autoincremented.
            await connection.execute(f"DELETE FROM sqlite_sequence WHERE name = '{self.table}'")

    async def increment(self, column: str, amount: int = 1, **extra: Any) -> int:
        target = self.column(column)
        return await self.update({column: target + amount, **extra})

    async def decrement(self, column: str, amount: int = 1, **extra: Any) -> int:
        target = self.column(column)
        return await self.update({column: target - amount, **extra})

    async def increment_each(self, columns: Mapping[str, Any], **extra: Any) -> int:
        """Raise several columns in one statement — ``incrementEach``."""
        changes = {name: self.column(name) + amount for name, amount in columns.items()}
        return await self.update({**changes, **extra})

    async def decrement_each(self, columns: Mapping[str, Any], **extra: Any) -> int:
        changes = {name: self.column(name) - amount for name, amount in columns.items()}
        return await self.update({**changes, **extra})

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
        payload = _writable_rows(values)
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
        return await self.model.create({**self._pending_attributes, **attributes, **(values or {})})

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
        instance.force_fill({**self._pending_attributes, **attributes, **(values or {})})
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
        return await self.model.create({**self._pending_attributes, **attributes, **(values or {})})


class JoinClause(QueryBuilder):
    """The builder a join callable receives — Laravel's ``JoinClause``.

    It is a query builder bound to the joined table, so `where` and friends
    all work; `on` is the column-to-column comparison a join usually wants.
    """

    def on(
        self,
        first: str | Callable[[JoinClause], Any],
        operator: Any = _MISSING,
        second: Any = _MISSING,
        boolean: str = "and",
    ) -> JoinClause:
        if callable(first):
            clause = self._nested(first)
            if clause is not None:
                self._push_where(boolean, clause)
            return self
        self.where_column(first, operator, second, boolean=boolean)
        return self

    def or_on(self, first: str, operator: Any = _MISSING, second: Any = _MISSING) -> JoinClause:
        return self.on(first, operator, second, boolean="or")

    def _nested(self, callback: Callable[[Any], Any]) -> ClauseElement | None:
        nested = JoinClause(
            model=self.model,
            table=self.table,
            connection=self._connection_name,
            tables=self._tables,
        )
        nested._local_tables = self._local_tables
        callback(nested)
        return nested._compile_wheres()


def _writable_rows(
    values: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """One row or many, ready to be bound."""
    rows = [values] if isinstance(values, Mapping) else values
    return [{key: _writable_value(value) for key, value in dict(row).items()} for row in rows]


def _writable_value(value: Any) -> Any:
    """A list or dict headed for a JSON column becomes the document it describes.

    The builder's table clauses carry no column types, so nothing downstream
    would know to encode it; Laravel encodes here for the same reason.
    """
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


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


def _ignoring_insert(table: TableClause, payload: Sequence[Mapping[str, Any]], dialect: str) -> Any:
    """An insert that skips rows a constraint would reject."""
    name = str(dialect).lower()
    if name == "mysql":
        from sqlalchemy.dialects.mysql import insert as dialect_insert

        return dialect_insert(table).values(list(payload)).prefix_with("IGNORE")
    if name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    elif name in {"postgresql", "postgres"}:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        raise UnsupportedByDialectError("insert-or-ignore", str(dialect))
    return dialect_insert(table).values(list(payload)).on_conflict_do_nothing()


def _truncate_sql(table: str, dialect: Any) -> list[str]:
    """Emptying a table, spelled for the engine in front of us.

    SQLite has no `TRUNCATE`; its delete is paired with a reset of the
    sequence table, which is what makes the ids start over the way they do
    elsewhere. That reset lives in `truncate` because the sequence table is
    only there once something has autoincremented.
    """
    quoted = quote_ident(dialect, table)
    if dialect.name == "sqlite":
        return [f"DELETE FROM {quoted}"]
    if dialect.name in {"postgresql", "mssql"}:
        return [f"TRUNCATE TABLE {quoted}" + (" RESTART IDENTITY CASCADE" if dialect.name == "postgresql" else "")]
    return [f"TRUNCATE TABLE {quoted}"]


def _json_set(column: Any, edits: Sequence[tuple[list[str], Any]]) -> Any:
    """Fold several edits to one JSON column into a single expression."""
    document = column
    for path, value in edits:
        document = JsonSet(document, path, value)
    return document


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


_SELECT_ALIAS = re.compile(r"^(?P<expression>.+?)\s+as\s+(?P<alias>[A-Za-z_][A-Za-z0-9_]*)$", re.IGNORECASE)


def _split_select_alias(sql: str) -> tuple[str, str | None]:
    """Separate ``count(*) as total`` into the expression and the name."""
    match = _SELECT_ALIAS.match(sql.strip())
    if match is None:
        return sql, None
    return match.group("expression"), match.group("alias")


def _unqualified(order: Any) -> Any:
    """Strip the table off an ordering, for use over a union."""
    element = getattr(order, "element", None)
    name = getattr(element, "name", None)
    if name is None:
        return order
    bare = sa.literal_column(str(name))
    return bare.desc() if order.modifier is operators.desc_op else bare.asc()


def _pair(low: Any, high: Any) -> tuple[Any, Any]:
    """Accept ``(1, 100)`` or Laravel's ``[1, 100]`` for a range."""
    if high is _MISSING:
        first, second = low
        return first, second
    return low, high


def _first_sample(values: Any) -> Any:
    """One value from a list, to type a JSON comparison by."""
    if isinstance(values, QueryBuilder):
        return None
    for value in values:
        return value
    return None


def _clock_now() -> Any:
    """The current moment, as the app's clock reports it."""
    from almasix.support.helpers import now

    return now().replace(tzinfo=None)


def _clock_today() -> Any:
    from almasix.support.helpers import today

    return today()


def _as_date_text(value: Any) -> Any:
    """Dates compare against `date()` output, which is text."""
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.strftime("%Y-%m-%d")
    return value


def _as_time_text(value: Any) -> Any:
    """Times compare against `time()` output, which is text."""
    if isinstance(value, datetime.datetime):
        return value.strftime("%H:%M:%S")
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M:%S")
    return value
