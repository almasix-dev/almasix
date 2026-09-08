"""Engine manager — resolves drivers from `config/scout.py`."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from almasix.scout.engines.base import Engine
from almasix.scout.engines.collection import CollectionEngine
from almasix.scout.engines.database import DatabaseEngine
from almasix.scout.engines.meilisearch import MeilisearchEngine
from almasix.scout.engines.null import NullEngine
from almasix.scout.exceptions import UnsupportedEngineException

#: Engines Almasix ships with. `database` is the default, as it is in Laravel:
#: it needs no service and it is right for most applications.
BUILT_IN: dict[str, type[Engine]] = {
    "collection": CollectionEngine,
    "database": DatabaseEngine,
    "meilisearch": MeilisearchEngine,
    "null": NullEngine,
}

DEFAULT_DRIVER = "database"


class EngineManager:
    """Resolves named search engines, and holds what search is configured to do."""

    def __init__(self, app: Any | None = None, config: Mapping[str, Any] | None = None) -> None:
        self.app = app
        self.config = dict(config or {})
        self._engines: dict[str, Engine] = {}
        self._custom: dict[str, Callable[..., Engine]] = {}

    # --- drivers ------------------------------------------------------------

    def get_default_driver(self) -> str:
        return str(self.config.get("driver") or DEFAULT_DRIVER)

    def set_default_driver(self, name: str) -> None:
        self.config["driver"] = name

    def extend(self, driver: str, callback: Callable[..., Engine]) -> EngineManager:
        """Register a custom engine (Laravel's `EngineManager::extend`)."""
        self._custom[driver] = callback
        self._engines.pop(driver, None)
        return self

    def engine(self, name: str | None = None) -> Engine:
        key = name or self.get_default_driver()
        if key not in self._engines:
            self._engines[key] = self._resolve(key)
        return self._engines[key]

    def forget_engine(self, name: str | None = None) -> None:
        if name is None:
            self._engines.clear()
        else:
            self._engines.pop(name, None)

    def set_engine(self, name: str, engine: Engine) -> EngineManager:
        """Put an engine in place by hand — what `Scout.fake()` does."""
        self._engines[name] = engine
        return self

    def _resolve(self, name: str) -> Engine:
        settings = dict(self.config.get(name) or {})
        if name in self._custom:
            return self._custom[name](self.app, settings, name)
        engine = BUILT_IN.get(name)
        if engine is None:
            raise UnsupportedEngineException(
                f"Search engine {name!r} is not supported. "
                f"Available: {', '.join(sorted(BUILT_IN))}. "
                "Register your own with Scout.extend()."
            )
        return engine(name, settings)

    # --- what search does ---------------------------------------------------

    @property
    def prefix(self) -> str:
        """Prepended to every index name — one Meilisearch, several apps."""
        return str(self.config.get("prefix") or "")

    @property
    def queues(self) -> bool:
        """Whether indexing goes through the queue."""
        queue = self.config.get("queue")
        return bool(queue) if not isinstance(queue, Mapping) else True

    @property
    def queue_options(self) -> dict[str, Any]:
        queue = self.config.get("queue")
        return dict(queue) if isinstance(queue, Mapping) else {}

    @property
    def after_commit(self) -> bool:
        """Whether indexing waits for the surrounding transaction to commit."""
        return bool(self.config.get("after_commit"))

    @property
    def soft_delete(self) -> bool:
        """Whether trashed records stay in the index, flagged."""
        return bool(self.config.get("soft_delete"))

    def chunk_size(self, kind: str = "searchable") -> int:
        """How many records go into one index request (`scout.chunk`)."""
        chunk = self.config.get("chunk") or {}
        return int(chunk.get(kind) or 500)
