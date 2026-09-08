"""What every document store must be able to do."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.orm.documents.filters import Query


class DocumentStore(ABC):
    """A collection-shaped database, behind one small interface.

    Everything Articulate's document layer needs, and nothing engine-specific:
    a store receives a `Query` and returns plain dicts.
    """

    #: The driver name in `config/database.py`.
    driver = "document"

    def __init__(self, name: str, config: Mapping[str, Any] | None = None) -> None:
        self.name = name
        self.config = dict(config or {})

    # --- reads --------------------------------------------------------------

    @abstractmethod
    async def find(self, query: Query) -> list[dict[str, Any]]:
        """The documents matching the query, in its order and window."""

    @abstractmethod
    async def count(self, query: Query) -> int:
        """How many documents match, ignoring limit and offset."""

    @abstractmethod
    async def aggregate(self, query: Query, function: str, column: str | None = None) -> Any:
        """`sum` / `avg` / `min` / `max` over a field."""

    @abstractmethod
    async def group_count(self, query: Query, column: str) -> dict[Any, int]:
        """Counts per distinct value of `column` — what `with_count` needs."""

    # --- writes -------------------------------------------------------------

    @abstractmethod
    async def insert(self, collection: str, documents: Sequence[Mapping[str, Any]]) -> list[Any]:
        """Insert documents; returns the key of each, generated or given."""

    @abstractmethod
    async def update(self, query: Query, values: Mapping[str, Any]) -> int:
        """Set fields on every matching document; returns how many changed."""

    @abstractmethod
    async def increment(self, query: Query, amounts: Mapping[str, Any], values: Mapping[str, Any]) -> int:
        """Add to numeric fields in place, and set anything in `values`."""

    @abstractmethod
    async def delete(self, query: Query) -> int:
        """Remove every matching document; returns how many went."""

    # --- collections and indexes -------------------------------------------

    @abstractmethod
    async def create_index(
        self,
        collection: str,
        keys: Sequence[tuple[str, int]],
        *,
        unique: bool = False,
        name: str | None = None,
    ) -> str:
        """Declare an index; returns its name."""

    @abstractmethod
    async def indexes(self, collection: str) -> list[dict[str, Any]]:
        """The indexes that exist on a collection."""

    @abstractmethod
    async def drop_collection(self, collection: str) -> None:
        """Remove a collection and everything in it."""

    @abstractmethod
    async def collections(self) -> list[str]:
        """Every collection this store holds."""

    async def disconnect(self) -> None:
        """Release whatever the store is holding open."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.name!r}>"
