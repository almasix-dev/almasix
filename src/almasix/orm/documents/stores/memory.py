"""An in-process document store — the sqlite of the document world.

Real work goes to Mongo. This one exists so tests, examples, and a laptop
without a server still exercise the whole document path.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from almasix.orm.documents.filters import (
    Condition,
    Query,
    UnsupportedQueryError,
    dotted,
    has_path,
)
from almasix.orm.documents.stores.base import DocumentStore


def new_key() -> str:
    """A 24-character hex key, the shape of a Mongo ObjectId."""
    return secrets.token_hex(12)


def _compare(left: Any, right: Any, operator: str) -> bool:
    """Order comparisons that refuse to crash on mixed or missing values."""
    if left is None or right is None:
        return False
    try:
        if operator == "<":
            return bool(left < right)
        if operator == "<=":
            return bool(left <= right)
        if operator == ">":
            return bool(left > right)
        return bool(left >= right)
    except TypeError:  # pragma: no cover - defensive, documents are untyped
        return False


def _like(value: Any, pattern: str) -> bool:
    """SQL `LIKE`, translated: `%` is anything, `_` is one character."""
    if value is None:
        return False
    expression = re.escape(str(pattern)).replace("%", ".*").replace("_", ".")
    return re.fullmatch(expression, str(value), flags=re.IGNORECASE) is not None


def matches(document: Mapping[str, Any], conditions: Sequence[Condition]) -> bool:
    """Evaluate a where list against one document, honoring and/or."""
    if not conditions:
        return True
    result = _matches_one(document, conditions[0])
    for condition in conditions[1:]:
        outcome = _matches_one(document, condition)
        result = (result or outcome) if condition.boolean == "or" else (result and outcome)
    return result


def _matches_one(document: Mapping[str, Any], condition: Condition) -> bool:
    operator = condition.operator
    if operator == "group":
        return matches(document, condition.value)
    if operator == "raw":
        if callable(condition.value):
            return bool(condition.value(document))
        raise UnsupportedQueryError(
            "where_raw() with a native filter belongs to a real engine — "
            "pass a callable when the memory store has to evaluate it"
        )

    value = dotted(document, condition.column)
    expected = condition.value

    if operator == "=":
        return value == expected
    if operator == "!=":
        return value != expected
    if operator in ("<", "<=", ">", ">="):
        return _compare(value, expected, operator)
    if operator == "in":
        return value in list(expected)
    if operator == "not in":
        return value not in list(expected)
    if operator == "null":
        return value is None
    if operator == "not null":
        return value is not None
    if operator == "between":
        low, high = expected
        return _compare(value, low, ">=") and _compare(value, high, "<=")
    if operator == "not between":
        low, high = expected
        return not (_compare(value, low, ">=") and _compare(value, high, "<="))
    if operator == "like":
        return _like(value, expected)
    if operator == "regex":
        return value is not None and re.search(str(expected), str(value)) is not None
    if operator == "exists":
        return has_path(document, condition.column) is bool(expected)
    if operator == "all":
        return isinstance(value, list) and all(item in value for item in expected)
    return isinstance(value, (list, tuple)) and len(value) == int(expected)  # "size"


class _Sortable:
    """Sort key that puts `None` first and never compares across types."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def __lt__(self, other: _Sortable) -> bool:
        if self.value is None:
            return other.value is not None
        if other.value is None:
            return False
        try:
            return bool(self.value < other.value)
        except TypeError:  # pragma: no cover - defensive, documents are untyped
            return str(self.value) < str(other.value)


class MemoryStore(DocumentStore):
    """Documents in a dict, with the same semantics the Mongo driver gives."""

    driver = "memory"

    def __init__(self, name: str = "memory", config: Mapping[str, Any] | None = None) -> None:
        super().__init__(name, config)
        self._collections: dict[str, list[dict[str, Any]]] = {}
        self._indexes: dict[str, list[dict[str, Any]]] = {}
        self.key_name = str(self.config.get("key", "_id"))

    # --- reads --------------------------------------------------------------

    def _documents(self, collection: str) -> list[dict[str, Any]]:
        return self._collections.setdefault(collection, [])

    def _matching(self, query: Query) -> list[dict[str, Any]]:
        return [row for row in self._documents(query.collection) if matches(row, query.wheres)]

    async def find(self, query: Query) -> list[dict[str, Any]]:
        rows = self._matching(query)
        for order in reversed(query.orders):
            rows.sort(key=lambda row, o=order: _Sortable(dotted(row, o.column)), reverse=order.descending)
        if query.distinct:
            seen: set[Any] = set()
            unique: list[dict[str, Any]] = []
            for row in rows:
                value = dotted(row, query.distinct)
                if value not in seen:
                    seen.add(value)
                    unique.append(row)
            rows = unique
        if query.offset:
            rows = rows[query.offset :]
        if query.limit is not None:
            rows = rows[: query.limit]
        if query.projection:
            keys = {*query.projection, self.key_name}
            rows = [{key: value for key, value in row.items() if key in keys} for row in rows]
        return deepcopy(rows)

    async def count(self, query: Query) -> int:
        window = query.clone()
        window.projection = ()
        rows = self._matching(window)
        if query.offset:
            rows = rows[query.offset :]
        if query.limit is not None:
            rows = rows[: query.limit]
        return len(rows)

    async def aggregate(self, query: Query, function: str, column: str | None = None) -> Any:
        rows = self._matching(query)
        if function == "count":
            return len(rows)
        values = [dotted(row, column or "") for row in rows]
        numbers = [value for value in values if value is not None]
        if not numbers:
            return None
        if function == "sum":
            return sum(numbers)
        if function == "avg":
            return sum(numbers) / len(numbers)
        if function == "min":
            return min(numbers, key=_Sortable)
        return max(numbers, key=_Sortable)

    async def group_count(self, query: Query, column: str) -> dict[Any, int]:
        counts: dict[Any, int] = {}
        for row in self._matching(query):
            key = dotted(row, column)
            counts[key] = counts.get(key, 0) + 1
        return counts

    # --- writes -------------------------------------------------------------

    async def insert(self, collection: str, documents: Sequence[Mapping[str, Any]]) -> list[Any]:
        keys: list[Any] = []
        for document in documents:
            row = deepcopy(dict(document))
            if row.get(self.key_name) is None:
                row[self.key_name] = new_key()
            self._enforce_unique(collection, row)
            self._documents(collection).append(row)
            keys.append(row[self.key_name])
        return keys

    async def update(self, query: Query, values: Mapping[str, Any]) -> int:
        changed = 0
        for row in self._matching(query):
            row.update(deepcopy(dict(values)))
            changed += 1
        return changed

    async def increment(
        self,
        query: Query,
        amounts: Mapping[str, Any],
        values: Mapping[str, Any],
    ) -> int:
        changed = 0
        for row in self._matching(query):
            for column, amount in amounts.items():
                row[column] = (row.get(column) or 0) + amount
            row.update(deepcopy(dict(values)))
            changed += 1
        return changed

    async def delete(self, query: Query) -> int:
        keep = [row for row in self._documents(query.collection) if not matches(row, query.wheres)]
        removed = len(self._documents(query.collection)) - len(keep)
        self._collections[query.collection] = keep
        return removed

    # --- collections and indexes -------------------------------------------

    def _enforce_unique(self, collection: str, row: Mapping[str, Any]) -> None:
        for index in self._indexes.get(collection, []):
            if not index["unique"]:
                continue
            fields = [field for field, _ in index["keys"]]
            candidate = [dotted(row, field) for field in fields]
            for existing in self._documents(collection):
                if [dotted(existing, field) for field in fields] == candidate:
                    raise ValueError(
                        f"Duplicate value for unique index {index['name']!r} on {collection}"
                    )

    async def create_index(
        self,
        collection: str,
        keys: Sequence[tuple[str, int]],
        *,
        unique: bool = False,
        name: str | None = None,
    ) -> str:
        pairs = [(field, int(direction)) for field, direction in keys]
        index_name = name or "_".join(f"{field}_{direction}" for field, direction in pairs)
        existing = self._indexes.setdefault(collection, [])
        for index in existing:
            if index["name"] == index_name:
                return index_name
        existing.append({"name": index_name, "keys": pairs, "unique": unique})
        return index_name

    async def indexes(self, collection: str) -> list[dict[str, Any]]:
        return [dict(index) for index in self._indexes.get(collection, [])]

    async def drop_collection(self, collection: str) -> None:
        self._collections.pop(collection, None)
        self._indexes.pop(collection, None)

    async def collections(self) -> list[str]:
        return sorted(self._collections)

    async def flush(self) -> None:
        """Forget everything — the memory store's `migrate:fresh`."""
        self._collections.clear()
        self._indexes.clear()
