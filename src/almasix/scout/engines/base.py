"""What every search engine has to answer.

An engine indexes records, searches them, and turns what it found back into
models. Everything above it — the `Searchable` mixin, the builder, the
commands — is written against these methods and nothing else, which is why a
custom engine registered with `Scout.extend()` is a first-class citizen.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.orm.collection import Collection


class Engine(ABC):
    """The contract a search engine satisfies."""

    #: The name this engine is configured under (`scout.driver`).
    driver = "engine"

    def __init__(self, name: str = "", config: Mapping[str, Any] | None = None) -> None:
        self.name = name or self.driver
        self.config = dict(config or {})

    # --- writing ------------------------------------------------------------

    @abstractmethod
    async def update(self, models: Sequence[Any]) -> None:
        """Add or replace these models in their index."""

    @abstractmethod
    async def delete(self, models: Sequence[Any]) -> None:
        """Remove these models from their index."""

    @abstractmethod
    async def flush(self, model: Any) -> None:
        """Remove every record of a model class from its index."""

    async def create_index(self, name: str, options: Mapping[str, Any] | None = None) -> Any:
        """Create an index by name; engines without indexes may ignore this."""
        del name, options
        return None

    async def delete_index(self, name: str) -> Any:
        del name
        return None

    async def delete_all_indexes(self) -> Any:
        """Delete every index this engine knows about."""
        return None

    async def sync_settings(self, model: Any) -> bool:
        """Push the configured index settings for a model; `False` if none apply."""
        del model
        return False

    # --- reading ------------------------------------------------------------

    @abstractmethod
    async def search(self, builder: Any) -> Any:
        """Run the search and return the engine's own result shape."""

    @abstractmethod
    async def paginate(self, builder: Any, per_page: int, page: int) -> Any:
        """Run the search for one page of results."""

    @abstractmethod
    def map_ids(self, results: Any) -> list[Any]:
        """The keys in a result set, in the order the engine ranked them."""

    @abstractmethod
    def total_count(self, results: Any) -> int:
        """How many records matched, ignoring paging."""

    async def map(self, builder: Any, results: Any, model: Any) -> Collection[Any]:
        """Turn a result set into models, keeping the engine's order."""
        del model
        return await hydrate(builder, self.map_ids(results))

    async def keys(self, builder: Any) -> list[Any]:
        return self.map_ids(await self.search(builder))

    async def get(self, builder: Any) -> Collection[Any]:
        return await self.map(builder, await self.search(builder), builder.model)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.name!r})"


async def hydrate(builder: Any, keys: Sequence[Any]) -> Collection[Any]:
    """Fetch the models behind a list of keys, in the engine's order.

    A search engine ranks; a database does not. The rows come back however
    the database felt like returning them and are put back in the engine's
    order here, because that order is the whole point of searching.
    """
    if not keys:
        return Collection([])

    models = await builder.model_query(keys).get()
    by_key = {str(model.get_scout_key()): model for model in models}
    return Collection([by_key[str(key)] for key in keys if str(key) in by_key])


def searchable_payload(model: Any) -> dict[str, Any]:
    """What goes into the index for one model, key included."""
    payload = dict(model.to_searchable_array())
    payload.update(model.scout_metadata())
    payload.setdefault(model.get_scout_key_name(), model.get_scout_key())
    return payload
