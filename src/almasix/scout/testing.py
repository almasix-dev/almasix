"""Search under test — record instead of index, then assert."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from almasix.orm.collection import Collection
from almasix.scout.engines.base import Engine, searchable_payload


@dataclass
class RecordedIndexWrite:
    """One batch of records that would have reached the index."""

    action: str
    index: str
    keys: list[Any] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    #: The options an index-management call carried, if any.
    payload: dict[str, Any] = field(default_factory=dict)


class FakeEngine(Engine):
    """An engine that remembers what it was asked to do.

    Installed by `Scout.fake()`. Searching returns whatever the fake was
    given as hits — models, or nothing — so a controller can be exercised
    without a search service anywhere near the test.
    """

    driver = "fake"

    def __init__(self, name: str = "fake", hits: Sequence[Any] | None = None) -> None:
        super().__init__(name, {})
        self.writes: list[RecordedIndexWrite] = []
        self.searches: list[Any] = []
        self.hits: list[Any] = list(hits or [])
        self.indexes: list[str] = []

    def returns(self, models: Sequence[Any]) -> FakeEngine:
        """What the next searches find."""
        self.hits = list(models)
        return self

    # --- writing ------------------------------------------------------------

    async def update(self, models: Sequence[Any]) -> None:
        records = list(models)
        if not records:
            return
        self.writes.append(
            RecordedIndexWrite(
                action="update",
                index=type(records[0]).searchable_as(),
                keys=[model.get_scout_key() for model in records],
                documents=[searchable_payload(model) for model in records],
            )
        )

    async def delete(self, models: Sequence[Any]) -> None:
        records = list(models)
        if not records:
            return
        self.writes.append(
            RecordedIndexWrite(
                action="delete",
                index=type(records[0]).searchable_as(),
                keys=[model.get_scout_key() for model in records],
            )
        )

    async def flush(self, model: Any) -> None:
        self.writes.append(RecordedIndexWrite(action="flush", index=model.searchable_as()))

    async def create_index(self, name: str, options: Any = None) -> Any:
        self.indexes.append(name)
        self.writes.append(
            RecordedIndexWrite(action="create-index", index=name, payload=dict(options or {}))
        )
        return {"index": name}

    async def delete_index(self, name: str) -> Any:
        if name in self.indexes:
            self.indexes.remove(name)
        self.writes.append(RecordedIndexWrite(action="delete-index", index=name))
        return {"index": name}

    async def delete_all_indexes(self) -> Any:
        self.indexes.clear()
        self.writes.append(RecordedIndexWrite(action="delete-all-indexes", index="*"))
        return {"indexes": []}

    async def sync_settings(self, model: Any) -> bool:
        self.writes.append(RecordedIndexWrite(action="settings", index=model.searchable_as()))
        return True

    # --- reading ------------------------------------------------------------

    async def search(self, builder: Any) -> Any:
        self.searches.append(builder)
        return {"models": list(self.hits), "total": len(self.hits)}

    async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
        self.searches.append(builder)
        start = max(int(page) - 1, 0) * int(per_page)
        return {"models": self.hits[start : start + int(per_page)], "total": len(self.hits)}

    def map_ids(self, results: Any) -> list[Any]:
        return [model.get_scout_key() for model in results["models"]]

    def total_count(self, results: Any) -> int:
        return int(results["total"])

    async def map(self, builder: Any, results: Any, model: Any) -> Collection[Any]:
        del builder, model
        return Collection(list(results["models"]))

    # --- assertions -----------------------------------------------------

    def written(self, action: str | None = None, index: str | None = None) -> list[RecordedIndexWrite]:
        return [
            write
            for write in self.writes
            if (action is None or write.action == action)
            and (index is None or write.index == index)
        ]

    def assert_synced(self, model: Any, keys: Sequence[Any] | None = None) -> None:
        """A model — or these keys — reached the index."""
        index, wanted = _target(model, keys)
        for write in self.written("update", index):
            if wanted is None or set(wanted) <= {str(key) for key in write.keys}:
                return
        raise AssertionError(
            f"Nothing was indexed for [{index}]"
            + (f" with keys {list(wanted)}." if wanted else ".")
        )

    def assert_removed(self, model: Any, keys: Sequence[Any] | None = None) -> None:
        index, wanted = _target(model, keys)
        for write in self.written("delete", index):
            if wanted is None or set(wanted) <= {str(key) for key in write.keys}:
                return
        raise AssertionError(f"Nothing was removed from [{index}].")

    def assert_flushed(self, model: Any) -> None:
        if not self.written("flush", model.searchable_as()):
            raise AssertionError(f"Index [{model.searchable_as()}] was not flushed.")

    def assert_nothing_synced(self) -> None:
        if self.writes:
            actions = ", ".join(f"{write.action} {write.index}" for write in self.writes)
            raise AssertionError(f"Expected no index writes; got: {actions}.")

    def assert_searched(self, query: str) -> None:
        if not any(builder.query == query for builder in self.searches):
            asked = ", ".join(repr(builder.query) for builder in self.searches) or "nothing"
            raise AssertionError(f"No search for {query!r}. Searched: {asked}.")

    def assert_search_count(self, count: int) -> None:
        if len(self.searches) != count:
            raise AssertionError(f"Expected {count} searches; got {len(self.searches)}.")

    def flush_records(self) -> None:
        self.writes.clear()
        self.searches.clear()


def _target(model: Any, keys: Sequence[Any] | None) -> tuple[str, set[str] | None]:
    """Accept a model class or an instance, and turn keys into strings."""
    if isinstance(model, type):
        return model.searchable_as(), {str(key) for key in keys} if keys else None
    wanted = {str(key) for key in keys} if keys else {str(model.get_scout_key())}
    return model.searchable_as(), wanted
