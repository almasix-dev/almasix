"""Courier package service provider — the M29 living example."""

from __future__ import annotations

from pathlib import Path

from almasix.providers import ServiceProvider

_HERE = Path(__file__).resolve().parent


class CourierServiceProvider(ServiceProvider):
    """Registers courier config, routes, views, lang, and publishable assets."""

    def register(self) -> None:
        self.merge_config_from(_HERE / "config" / "courier.py", "courier")

    def boot(self) -> None:
        self.publishes(
            {_HERE / "config" / "courier.py": self.app.path("config", "courier.py")},
            "courier-config",
        )
        self.load_routes_from(_HERE / "routes" / "web.py")
        self.load_views_from(_HERE / "resources" / "views", "courier")
        self.load_translations_from(_HERE / "lang", "courier")
        self.load_migrations_from(_HERE / "database" / "migrations")
        self.publishes_migrations(
            {
                _HERE
                / "database"
                / "migrations"
                / "0001_01_01_000000_create_courier_messages_table.py": (
                    "database/migrations/create_courier_messages_table.py"
                ),
            },
            "courier-migrations",
        )
        from courier.console.courier_status import CourierStatusCommand

        self.commands([CourierStatusCommand])
