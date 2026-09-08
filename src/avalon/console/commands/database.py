"""The migration and seeding commands — ``migrate*`` and ``db:seed``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from avalon.console.command import Command
from avalon.console.confirmable import Confirmable
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

    def migrator(self, connection: str | None = None, path: str | Path | None = None) -> Migrator:
        directory = Path(path) if path else self.root() / "database" / "migrations"
        if not directory.is_absolute():
            directory = self.root() / directory
        return Migrator(directory, connection)

    def resolve_migrator(self) -> Migrator | None:
        """The migrator ``--database`` and ``--path`` ask for, or ``None``.

        Names the option it could not read before returning ``None``, so the
        caller only has to answer with ``INVALID``. Where Laravel's ``--path``
        takes any number of directories, Avalon's takes one: a ``Migrator``
        reads a single tree.
        """
        connection = self.option("database")
        if connection is True:
            self.error(
                "Invalid value for '--database': provide a connection name, e.g. --database=sqlite."
            )
            return None
        path = self.option("path")
        if path is True:
            self.error(
                "Invalid value for '--path': provide a directory, e.g. --path=database/migrations."
            )
            return None
        return self.migrator(
            str(connection or "").strip() or None,
            str(path or "").strip() or None,
        )

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
        "{--seeder= : Seeder class to run, which implies --seed}"
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


class MigrateInstallCommand(DatabaseCommand):
    """Create the table the migrator records its runs in.

    Laravel's ``migrate:install`` fails on a second run; Avalon's says the
    table is already there and succeeds, because every other migration command
    creates it on demand and running this one twice is not a mistake.
    """

    signature = (
        "migrate:install "
        "{--database= : Connection to install on (default: the configured default)}"
    )
    description = "Create the migration repository table"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        if self.run_async(migrator.install()):
            self.success("Migration table created successfully.")
        else:
            self.line("Migration table already exists.")
        return self.SUCCESS


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


class MigrateResetCommand(Confirmable, DatabaseCommand):
    """Roll every migration back, newest first.

    ``--pretend`` is not offered: Avalon's migrator runs schema changes rather
    than compiling them to SQL, so there is nothing honest to print.
    """

    signature = (
        "migrate:reset "
        "{--database= : Connection to roll back (default: the configured default)} "
        "{--path= : Directory to read migrations from (default: database/migrations)} "
        "{--force : Roll back without asking, and allow it in production}"
    )
    description = "Roll back every migration that has run"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        if not self.confirm_to_proceed("This rolls back every migration that has run."):
            return self.FAILURE

        rolled = self.run_async(migrator.reset())
        if not rolled:
            self.line("Nothing to roll back.")
            return self.SUCCESS
        for name in rolled:
            self.warn(f"Rolled back: {name}")
        self.success(f"Rolled back {len(rolled)} migration(s).")
        return self.SUCCESS


class MigrateRefreshCommand(Confirmable, DatabaseCommand):
    """Roll the migrations back and run them again."""

    signature = (
        "migrate:refresh "
        "{--step=0 : Batches to roll back and re-run instead of every one} "
        "{--seed : Run DatabaseSeeder after migrating} "
        "{--seeder= : Seeder class to run, which implies --seed} "
        "{--database= : Connection to refresh (default: the configured default)} "
        "{--path= : Directory to read migrations from (default: database/migrations)} "
        "{--force : Refresh without asking, and allow it in production}"
    )
    description = "Roll back every migration and run them again"

    def handle(self) -> int:
        steps = self.steps()
        if steps is None:
            return self.INVALID
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID

        scope = f"the last {steps} batch(es) of migrations" if steps else "every migration"
        if not self.confirm_to_proceed(f"This rolls back and re-runs {scope}."):
            return self.FAILURE

        rolled, applied = self.run_async(migrator.refresh(steps))
        for name in rolled:
            self.warn(f"Rolled back: {name}")
        if not applied:
            self.line("Nothing to migrate.")
        else:
            for name in applied:
                self.success(f"Migrated: {name}")
        return self.seed_if_asked()

    def steps(self) -> int | None:
        """``--step`` as a batch count, or ``None`` once it has been refused."""
        given = self.option("step")
        try:
            steps = 0 if given is None else int(str(given))
        except ValueError:
            self.error(f"Invalid value for '--step': {given!r} is not a valid integer.")
            return None
        if steps < 0:
            self.error(f"Invalid value for '--step': {given!r} is not a number of batches.")
            return None
        return steps


class MigrateFreshCommand(DatabaseCommand):
    signature = (
        "migrate:fresh {--seed : Run DatabaseSeeder after migrating} "
        "{--seeder= : Seeder class to run, which implies --seed}"
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
