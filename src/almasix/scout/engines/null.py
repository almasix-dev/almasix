"""The engine that searches nothing.

Useful in an environment where the search service is not reachable and you
would rather have empty results than a stack trace — a CI run, a seeding
script, a local machine without Meilisearch.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from almasix.orm.collection import Collection
from almasix.scout.engines.base import Engine


class NullEngine(Engine):
    """Accepts everything, indexes nothing, finds nothing."""

    driver = "null"

    async def update(self, models: Sequence[Any]) -> None:
        return None

    async def delete(self, models: Sequence[Any]) -> None:
        return None

    async def flush(self, model: Any) -> None:
        return None

    async def search(self, builder: Any) -> Any:
        del builder
        return {"hits": [], "total": 0}

    async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
        del builder, per_page, page
        return {"hits": [], "total": 0}

    def map_ids(self, results: Any) -> list[Any]:
        del results
        return []

    async def map(self, builder: Any, results: Any, model: Any) -> Collection[Any]:
        del builder, results, model
        return Collection([])

    def total_count(self, results: Any) -> int:
        del results
        return 0
