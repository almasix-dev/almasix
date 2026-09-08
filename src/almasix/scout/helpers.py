"""The manager accessor and the default search configuration."""

from __future__ import annotations

from typing import Any

from almasix.scout.manager import EngineManager

_manager: EngineManager | None = None


def set_engine_manager(manager: EngineManager | None) -> None:
    global _manager
    _manager = manager
    from almasix.scout.facade import Scout

    Scout.set_manager(manager)


def get_engine_manager() -> EngineManager:
    """The application's manager, or a bare one so libraries still work.

    Searching outside a booted application is legitimate — a unit test, a
    script — and it should behave rather than raise. Without configuration
    the engine is `database`, which needs nothing installed.
    """
    global _manager
    if _manager is None:
        _manager = EngineManager(config=default_scout_config())
    return _manager


def default_scout_config() -> dict[str, Any]:
    """The shape of `config/scout.py`."""
    from almasix.config import env

    return {
        "driver": env("SCOUT_DRIVER", "database"),
        "prefix": env("SCOUT_PREFIX", ""),
        "queue": bool(env("SCOUT_QUEUE", False)),
        "after_commit": False,
        "chunk": {"searchable": 500, "unsearchable": 500},
        "soft_delete": False,
        "identify": bool(env("SCOUT_IDENTIFY", False)),
        "meilisearch": {
            "host": env("MEILISEARCH_HOST", "http://localhost:7700"),
            "key": env("MEILISEARCH_KEY"),
            "index-settings": {},
        },
    }
