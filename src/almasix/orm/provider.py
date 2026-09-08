"""Database service provider."""

from __future__ import annotations

from typing import Any

from almasix.orm.connection import DatabaseManager
from almasix.orm.facade import set_manager
from almasix.providers.provider import ServiceProvider


def default_config(database: Any = None) -> dict[str, Any]:
    """Fallback config so an app without `config/database.py` still boots."""
    return {
        "default": "sqlite",
        "connections": {
            "sqlite": {"driver": "sqlite", "database": str(database) if database else ":memory:"}
        },
    }


class DatabaseServiceProvider(ServiceProvider):
    """Binds the `DatabaseManager` from `config/database.py`."""

    def register(self) -> None:
        app = self.app

        def factory(_container: Any) -> DatabaseManager:
            config = app.config.get("database", None)
            if not config:
                config = default_config(app.path("database") / "database.sqlite")
            else:
                config = dict(config)
                connections = dict(config.get("connections") or {})
                sqlite = dict(connections.get("sqlite") or {})
                database = sqlite.get("database")
                if (
                    database
                    and database != ":memory:"
                    and not str(database).startswith("/")
                    and "://" not in str(database)
                ):
                    sqlite["database"] = str(app.path(str(database)))
                    connections["sqlite"] = sqlite
                    config["connections"] = connections
            return DatabaseManager(config)

        app.container.singleton(DatabaseManager, factory)
        app.container.alias(DatabaseManager, "db")

    def boot(self) -> None:
        set_manager(self.app.make(DatabaseManager))
