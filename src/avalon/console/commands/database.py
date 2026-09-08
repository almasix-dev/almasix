"""The migration and seeding commands — ``migrate*`` and ``db:seed``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from avalon.console.command import Command
from avalon.console.exceptions import CommandFailed
from avalon.orm.migration import Migrator
from avalon.orm.seeder import SeederError, resolve_seeder_class, run_seeder


class SeederOutput:
    """The output hook ``run_seeder`` announces each seeder through.

    ``Seeder._announce`` looks for ``echo`` — Typer's name for it, not one the
    Command surface has — so the seeder gets this adapter and its progress
    lines still land on the command's own output.
    """

    def __init__(self, echo: Callable[[str], None]) -> None:
        self.echo = echo


class DatabaseCommand(Command):
    """Shared body: the migrator, the event loop, and the seeder run."""

    def migrator(self) -> Migrator:
        return Migrator(self.root() / "database" / "migrations")

    def root(self) -> Path:
        """The working directory, as ``grail`` was run.

        Not ``app.base_path``: the application is built while the front door
        imports, so its root is stale in a process that has since moved.
        """
        return Path.cwd()

    def run_async(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Await one migrator call, reporting failure the way Grail always has."""
        try:
            return asyncio.run(coro)
        except Exception as exc:
            self.error(str(exc))
            raise CommandFailed from exc

    def seed_database(self, class_name: str | None = None) -> int:
        """Run ``DatabaseSeeder``, or ``class_name`` when one was named.

        Not ``seed()``: ``Command.run`` injects every option as an attribute,
        and ``--seed`` would land on top of the method.
        """
        root = self.root()
        try:
            target = resolve_seeder_class(class_name, base_path=root) if class_name else None
            run_seeder(
                target,
                base_path=root,
                container=self.app.container,
                command=SeederOutput(self.line),
            )
        except SeederError as exc:
            self.error(str(exc))
            return self.FAILURE
        self.success("Database seeding completed successfully.")
        return self.SUCCESS

    def seed_if_asked(self) -> int:
        """``--seed`` runs the default seeder; ``--seeder=`` implies ``--seed``."""
        seeder = self.option("seeder")
        if not self.option("seed") and not seeder:
            return self.SUCCESS
        return self.seed_database(seeder)


class MigrateCommand(DatabaseCommand):
    signature = (
        "migrate {--seed : Run DatabaseSeeder after migrating} "
        "{--seeder= : Seeder class to run when --seed is set}"
    )
    description = "Run outstanding migrations"

    def handle(self) -> int:
        applied = self.run_async(self.migrator().run())
        if not applied:
            self.line("Nothing to migrate.")
        else:
            for name in applied:
                self.success(f"Migrated: {name}")
        return self.seed_if_asked()


class MigrateRollbackCommand(DatabaseCommand):
    signature = "migrate:rollback {--step=1 : Batches to roll back}"
    description = "Roll back the last migration batch"

    def handle(self) -> int:
        rolled = self.run_async(self.migrator().rollback(int(self.option("step") or 1)))
        if not rolled:
            self.line("Nothing to roll back.")
            return self.SUCCESS
        for name in rolled:
            self.warn(f"Rolled back: {name}")
        return self.SUCCESS


class MigrateFreshCommand(DatabaseCommand):
    signature = (
        "migrate:fresh {--seed : Run DatabaseSeeder after migrating} "
        "{--seeder= : Seeder class to run when --seed is set}"
    )
    description = "Drop all tables and re-run every migration"

    def handle(self) -> int:
        for name in self.run_async(self.migrator().fresh()):
            self.success(f"Migrated: {name}")
        return self.seed_if_asked()


class MigrateStatusCommand(DatabaseCommand):
    signature = "migrate:status"
    description = "Show which migrations have run"

    def handle(self) -> int:
        rows = self.run_async(self.migrator().status())
        if not rows:
            self.line("No migrations.")
            return self.SUCCESS
        for row in rows:
            mark = "Ran" if row["ran"] else "Pending"
            self.line(f"{mark:8} {row['migration']}")
        return self.SUCCESS


class DbSeedCommand(DatabaseCommand):
    signature = "db:seed {--class= : Seeder class to run (default: DatabaseSeeder)}"
    description = "Seed the database using DatabaseSeeder (or --class)"

    def handle(self) -> int:
        return self.seed_database(self.option("class"))
