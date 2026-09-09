"""Searching a table by reading it.

The collection engine pulls the rows the filters allow and looks for the
phrase in each record's searchable array, in Python. Nothing is indexed and
nothing needs installing, which makes it the right engine for a prototype, a
few hundred rows, or a test — and the wrong one for anything larger, where
the `database` engine does the same job in SQL.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from almasix.scout.builder import SOFT_DELETED
from almasix.scout.engines.base import Engine, searchable_payload


class CollectionEngine(Engine):
    """Filters the model's own rows in memory — no index, no service."""

    driver = "collection"

    async def update(self, models: Sequence[Any]) -> None:
        """Nothing to do: the rows are the index."""
        return

    async def delete(self, models: Sequence[Any]) -> None:
        return None

    async def flush(self, model: Any) -> None:
        return None

    async def search(self, builder: Any) -> Any:
        found = await self._matching(builder)
        return {"models": found[: builder.limit] if builder.limit else found, "total": len(found)}

    async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
        found = await self._matching(builder)
        start = max(int(page) - 1, 0) * int(per_page)
        return {"models": found[start : start + int(per_page)], "total": len(found)}

    def map_ids(self, results: Any) -> list[Any]:
        return [model.get_scout_key() for model in results["models"]]

    def total_count(self, results: Any) -> int:
        return int(results["total"])

    # --- the search itself --------------------------------------------------

    async def _matching(self, builder: Any) -> list[Any]:
        """Every row that survives the filters, the phrase, and the ordering."""
        rows = await self._rows(builder)
        phrase = builder.query.lower()

        found = [
            model for model in rows if model.should_be_searchable() and _contains(model, phrase)
        ]
        found = [model for model in found if _passes_soft_delete(builder, model)]
        return _ordered(builder, found)

    async def _rows(self, builder: Any) -> list[Any]:
        """The candidate rows, with the filters an SQL query can answer applied."""
        model = builder.model
        query = model.scout_base_query()

        for field, value in builder.wheres.items():
            if field != SOFT_DELETED:
                query = query.where(field, "=", value)
        for field, values in builder.where_ins.items():
            query = query.where_in(field, values)
        for field, values in builder.where_not_ins.items():
            query = query.where_not_in(field, values)

        return list(await query.order_by(model.primary_key, "desc").get())


def _contains(model: Any, phrase: str) -> bool:
    """Whether the phrase appears anywhere in the record's searchable data."""
    if not phrase:
        return True
    for value in searchable_payload(model).values():
        if value is None:
            continue
        text = (
            value if isinstance(value, (str, int, float, bool)) else json.dumps(value, default=str)
        )
        if phrase in str(text).lower():
            return True
    return False


def _passes_soft_delete(builder: Any, model: Any) -> bool:
    """Honour `with_trashed()` / `only_trashed()` for a soft deletable model."""
    wanted = builder.wheres.get(SOFT_DELETED)
    if wanted is None:
        return True
    trashed = bool(model.trashed()) if hasattr(model, "trashed") else False
    return trashed is bool(int(wanted))


def _ordered(builder: Any, models: list[Any]) -> list[Any]:
    """Apply `order_by`, last clause first, so the first one wins ties."""
    for order in reversed(builder.orders):
        models = sorted(
            models,
            key=lambda model, column=order["column"]: _sortable(model.get_attribute(column)),
            reverse=order["direction"] == "desc",
        )
    return models


def _sortable(value: Any) -> tuple[int, Any]:
    """Sort `None` first, and never compare a date with a string."""
    if value is None:
        return (0, "")
    return (1, value if isinstance(value, (int, float)) else str(value))
