"""`searchable()` on a query and on a collection.

Laravel adds these with macros in Scout's service provider so that
`Order::where('price', '>', 100)->searchable()` works. Almasix has no macro
system on the query builder, so the two methods are installed here — once, at
import — and refuse politely on a model that is not searchable.
"""

from __future__ import annotations

from typing import Any

_INSTALLED = False


async def _query_searchable(self: Any, chunk: int | None = None) -> int:
    """Index every row this query matches, a chunk at a time."""
    from almasix.scout.helpers import get_engine_manager
    from almasix.scout.searchable import make_searchable

    _require_searchable(self.model)
    size = int(chunk or get_engine_manager().chunk_size("searchable"))
    indexed = 0

    async def index(models: Any) -> None:
        nonlocal indexed
        wanted = [model for model in models if model.should_be_searchable()]
        await make_searchable(wanted)
        indexed += len(wanted)

    await self.chunk(size, index)
    return indexed


async def _query_unsearchable(self: Any, chunk: int | None = None) -> int:
    """Remove every row this query matches from the index."""
    from almasix.scout.helpers import get_engine_manager
    from almasix.scout.searchable import remove_from_search

    _require_searchable(self.model)
    size = int(chunk or get_engine_manager().chunk_size("unsearchable"))
    removed = 0

    async def remove(models: Any) -> None:
        nonlocal removed
        await remove_from_search(list(models))
        removed += len(models)

    await self.chunk(size, remove)
    return removed


async def _collection_searchable(self: Any) -> None:
    """Index the models already in hand — no `should_be_searchable()` check.

    Asking for a collection to be indexed is explicit, and Laravel treats it
    the same way: it overrides what the model says about itself.
    """
    from almasix.scout.searchable import make_searchable

    models = list(self)
    if models:
        _require_searchable(type(models[0]))
        await make_searchable(models)


async def _collection_unsearchable(self: Any) -> None:
    from almasix.scout.searchable import remove_from_search

    models = list(self)
    if models:
        _require_searchable(type(models[0]))
        await remove_from_search(models)


def _require_searchable(model: Any) -> None:
    if model is None or not hasattr(model, "searchable_as"):
        name = getattr(model, "__name__", model)
        raise TypeError(
            f"{name} is not searchable. Mix in almasix.scout.Searchable before Model."
        )


def install() -> None:
    """Add `searchable()` / `unsearchable()` to queries and collections."""
    global _INSTALLED
    if _INSTALLED:
        return

    from almasix.orm.builder import QueryBuilder
    from almasix.orm.collection import Collection

    QueryBuilder.searchable = _query_searchable  # type: ignore[attr-defined]
    QueryBuilder.unsearchable = _query_unsearchable  # type: ignore[attr-defined]
    Collection.searchable = _collection_searchable  # type: ignore[attr-defined]
    Collection.unsearchable = _collection_unsearchable  # type: ignore[attr-defined]
    _INSTALLED = True
