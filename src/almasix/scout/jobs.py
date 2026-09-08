"""The queued half of indexing.

A job carries a model class and a list of keys rather than the models
themselves: queue payloads here are plain JSON, so any driver can hold them,
and re-reading the rows when the job runs means the index gets what the
database says now instead of what it said when the request ended.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any

from almasix.queue.job import Job, ShouldQueue


class ScoutJob(Job, ShouldQueue):
    """Shared body: a model class, some keys, and the engine they belong to."""

    queue = "default"

    def __init__(self, model: str, keys: Sequence[Any]) -> None:
        self.model = model
        self.keys = list(keys)

    @classmethod
    def for_models(cls, models: Sequence[Any]) -> ScoutJob:
        first = type(models[0])
        return cls(
            f"{first.__module__}.{first.__qualname__}",
            [model.get_scout_key() for model in models],
        )

    def model_class(self) -> Any:
        module, _, name = str(self.model).rpartition(".")
        return getattr(importlib.import_module(module), name)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.model} {self.keys!r})"


class MakeSearchable(ScoutJob):
    """Index the rows behind these keys."""

    async def handle(self) -> None:
        model = self.model_class()
        models = await model.query_scout_models_by_ids(None, self.keys).get()
        records = [record for record in models if record.should_be_searchable()]
        if records:
            await model.searchable_using().update(records)


class RemoveFromSearch(ScoutJob):
    """Take the records behind these keys out of the index.

    The rows are usually gone by the time this runs, so the job rebuilds just
    enough model to name the index and the key.
    """

    async def handle(self) -> None:
        model = self.model_class()
        await model.searchable_using().delete([_stub(model, key) for key in self.keys])


def _stub(model: Any, key: Any) -> Any:
    """A model that exists only to say which record to delete."""
    instance = model()
    instance.force_fill({model.get_scout_key_name(): key})
    return instance
