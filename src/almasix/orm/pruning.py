"""Model pruning — Laravel's `Prunable` and `MassPrunable`.

Declare which rows are stale and let ``smith model:prune`` delete them::

    class Flight(Prunable, Model):
        def prunable(self):
            return self.query().where("created_at", "<", month_ago())

``Prunable`` loads each model so ``pruning()`` can clean up related files or
rows first. ``MassPrunable`` skips loading and deletes in bulk, which is much
faster but fires no per-model hook.
"""

from __future__ import annotations

from typing import Any

DEFAULT_CHUNK = 1000


class Prunable:
    """Deletes prunable models one by one, calling `pruning()` on each."""

    def prunable(self) -> Any:
        """Return a query matching the rows that should be pruned."""
        raise NotImplementedError(
            f"{type(self).__name__} is Prunable but does not implement prunable()."
        )

    async def pruning(self) -> None:
        """Called before this model is pruned — clean up related state here."""

    @classmethod
    def prunable_query(cls) -> Any:
        """The prunable query, built from a throwaway instance."""
        return cls().prunable()  # type: ignore[abstract]

    @classmethod
    async def prune(cls, chunk_size: int = DEFAULT_CHUNK) -> int:
        """Prune stale rows, returning how many were deleted."""
        pruned = 0
        while True:
            models = await cls.prunable_query().limit(chunk_size).get()
            if not len(models):
                return pruned
            for model in models:
                await model.pruning()
                if hasattr(model, "force_delete"):
                    await model.force_delete()
                else:  # pragma: no cover - every Model has force_delete
                    await model.delete()
                pruned += 1
            if len(models) < chunk_size:
                return pruned


class MassPrunable(Prunable):
    """Deletes prunable rows in bulk, without loading models."""

    @classmethod
    async def prune(cls, chunk_size: int = DEFAULT_CHUNK) -> int:
        pruned = 0
        primary_key = cls.primary_key  # type: ignore[attr-defined]
        while True:
            keys = await cls.prunable_query().limit(chunk_size).pluck(primary_key)
            if not keys:
                return pruned
            deleted = await (
                cls.new_query()  # type: ignore[attr-defined]
                .without_global_scopes()
                .where_in(primary_key, list(keys))
                .delete()
            )
            pruned += deleted if isinstance(deleted, int) else len(keys)
            if len(keys) < chunk_size:
                return pruned
