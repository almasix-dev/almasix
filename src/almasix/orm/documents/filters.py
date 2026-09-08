"""The query shape a document store is asked to satisfy.

A `DocumentBuilder` never speaks Mongo, and a store never speaks Articulate.
Between them sits this: a list of conditions, an order, a window. Each store
translates it into whatever its engine understands.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

#: Operators every store must understand.
OPERATORS = (
    "=",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "in",
    "not in",
    "null",
    "not null",
    "between",
    "not between",
    "like",
    "regex",
    "exists",
    "all",
    "size",
    "raw",
    "group",
)


class UnsupportedQueryError(RuntimeError):
    """A SQL-shaped call that a document store cannot honestly answer."""


@dataclass(frozen=True)
class Condition:
    """One `where` — or, when `operator` is `group`, a parenthesised set."""

    column: str
    operator: str
    value: Any = None
    boolean: str = "and"

    def __post_init__(self) -> None:
        if self.operator not in OPERATORS:
            raise UnsupportedQueryError(
                f"Operator {self.operator!r} means nothing to a document store; "
                f"use one of {', '.join(OPERATORS[:-2])}"
            )


@dataclass
class Order:
    column: str
    direction: str = "asc"

    @property
    def descending(self) -> bool:
        return self.direction.lower() == "desc"


@dataclass
class Query:
    """Everything a store needs to answer one question."""

    collection: str
    wheres: list[Condition] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    limit: int | None = None
    offset: int | None = None
    projection: tuple[str, ...] = ()
    distinct: str | None = None

    def clone(self) -> Query:
        return Query(
            collection=self.collection,
            wheres=list(self.wheres),
            orders=[Order(order.column, order.direction) for order in self.orders],
            limit=self.limit,
            offset=self.offset,
            projection=self.projection,
            distinct=self.distinct,
        )


def dotted(document: Any, path: str) -> Any:
    """Read `profile.city` out of a nested document; `None` when absent."""
    current: Any = document
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            if not part.isdigit() or int(part) >= len(current):
                return None
            current = current[int(part)]
        else:
            return None
    return current


def has_path(document: Any, path: str) -> bool:
    """Whether the path exists at all — `null` and missing are different."""
    current: Any = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True
