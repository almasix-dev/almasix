"""The migration and seeding commands — ``migrate*`` and ``db:seed``."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import Any

from almasix.console.command import Command
from almasix.console.confirmable import Confirmable
from almasix.console.exceptions import CommandFailed
from almasix.orm.migration import MigrationResult, Migrator
from almasix.orm.seeder import SeederError, resolve_seeder_class, run_seeder


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

    def migrator(
        self,
        connection: str | None = None,
        path: str | Path | Sequence[str | Path] | None = None,
    ) -> Migrator:
        given = [path] if isinstance(path, (str, Path)) else list(path or [])
        directories = [Path(one) for one in given] or [Path("database/migrations")]
        rooted = [one if one.is_absolute() else self.root() / one for one in directories]
        return Migrator(rooted, connection)

    def resolve_migrator(self) -> Migrator | None:
        """The migrator ``--database`` and ``--path`` ask for, or ``None``.

        Names the option it could not read before returning ``None``, so the
        caller only has to answer with ``INVALID``. ``--path`` takes several
        directories, comma-separated, as Laravel's repeated flag does.
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
        directories = [part.strip() for part in str(path or "").split(",") if part.strip()]
        return self.migrator(str(connection or "").strip() or None, directories)

    def report(self, results: Sequence[MigrationResult], verb: str, style: str) -> None:
        """Say what ran and how long it took, the way Laravel's migrator does."""
        announce = self.success if style == "success" else self.warn
        for result in results:
            if result.queries:
                self.line(f"{verb}: {result}")
                for query in result.queries:
                    self.line(f"  {query.sql}")
                continue
            announce(f"{verb}: {result} ({result.elapsed:.2f}ms)")

    def pretending(self) -> bool:
        return bool(self.option("pretend"))

    def root(self) -> Path:
        """The working directory, as ``smith`` was run.

        Not ``app.base_path``: the application is built while the front door
        imports, so its root is stale in a process that has since moved.
        """
        return Path.cwd()

    def run_async(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Await one migrator call, reporting failure the way Smith always has."""
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


class MigrateCommand(Confirmable, DatabaseCommand):
    """Run whatever has not run yet.

    ``--pretend`` prints the SQL each migration would run instead of running
    it, which is honest here because schema changes go through the connection
    like any other statement.
    """

    signature = (
        "migrate {--seed : Run DatabaseSeeder after migrating} "
        "{--seeder= : Seeder class to run, which implies --seed} "
        "{--database= : Connection to migrate (default: the configured default)} "
        "{--path= : Directories to read migrations from, comma-separated} "
        "{--step : Give each migration its own batch, so it can be rolled back alone} "
        "{--pretend : Print the SQL that would run, and run none of it} "
        "{--schema-path= : Schema dump to load before migrating} "
        "{--graceful : Report a failure as success, for deploys that must not stop} "
        "{--force : Migrate without asking, and allow it in production}"
    )
    description = "Run outstanding migrations"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        if not self.confirm_in_production():
            return self.FAILURE

        try:
            self.load_schema_if_asked(migrator)
            applied = self.run_async(
                migrator.run(step=bool(self.option("step")), pretend=self.pretending())
            )
        except CommandFailed:
            if self.option("graceful"):
                return self.SUCCESS
            raise

        if not applied:
            self.line("Nothing to migrate.")
        else:
            self.report(applied, "Migrated", "success")
        if self.pretending():
            return self.SUCCESS
        return self.seed_if_asked()

    def load_schema_if_asked(self, migrator: Migrator) -> None:
        """Replay a squashed schema first, when one was named and none has run."""
        given = self.option("schema_path")
        if not given or given is True:
            return
        source = Path(str(given))
        if not source.is_absolute():
            source = self.root() / source
        if self.run_async(migrator.any_ran()):
            return
        count = self.run_async(migrator.load_schema(source))
        self.success(f"Loaded {count} statement(s) from {source.name}.")


class MigrateInstallCommand(DatabaseCommand):
    """Create the table the migrator records its runs in.

    Laravel's ``migrate:install`` fails on a second run; Almasix's says the
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


class MigrateRollbackCommand(Confirmable, DatabaseCommand):
    """Undo the last batch, or exactly what ``--step`` / ``--batch`` name.

    ``--step`` counts migrations, as Laravel's does. It counted batches in
    Almasix until M43; ``migrate:rollback`` with nothing at all still undoes
    the last batch, which is what most callers meant by it.
    """

    signature = (
        "migrate:rollback {--step=0 : Migrations to roll back, newest first} "
        "{--batch=0 : Roll back one batch exactly, by its number} "
        "{--database= : Connection to roll back (default: the configured default)} "
        "{--path= : Directories to read migrations from, comma-separated} "
        "{--pretend : Print the SQL that would run, and run none of it} "
        "{--force : Roll back without asking, and allow it in production}"
    )
    description = "Roll back the last migration batch"

    def handle(self) -> int:
        step = self.count("step")
        batch = self.count("batch")
        if step is None or batch is None:
            return self.INVALID
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        if not self.confirm_in_production():
            return self.FAILURE

        rolled = self.run_async(
            migrator.rollback(step=step, batch=batch, pretend=self.pretending())
        )
        if not rolled:
            self.line("Nothing to roll back.")
            return self.SUCCESS
        self.report(rolled, "Rolled back", "warn")
        return self.SUCCESS

    def count(self, name: str) -> int | None:
        """One counting option, or ``None`` once it has been refused."""
        given = self.option(name)
        try:
            value = 0 if given is None or given is True else int(str(given))
        except ValueError:
            self.error(f"Invalid value for '--{name}': {given!r} is not a valid integer.")
            return None
        if value < 0:
            self.error(f"Invalid value for '--{name}': {given!r} is not a count.")
            return None
        return value


class MigrateResetCommand(Confirmable, DatabaseCommand):
    """Roll every migration back, newest first."""

    signature = (
        "migrate:reset "
        "{--database= : Connection to roll back (default: the configured default)} "
        "{--path= : Directories to read migrations from, comma-separated} "
        "{--pretend : Print the SQL that would run, and run none of it} "
        "{--force : Roll back without asking, and allow it in production}"
    )
    description = "Roll back every migration that has run"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        if not self.pretending() and not self.confirm_to_proceed(
            "This rolls back every migration that has run."
        ):
            return self.FAILURE

        rolled = self.run_async(migrator.reset(pretend=self.pretending()))
        if not rolled:
            self.line("Nothing to roll back.")
            return self.SUCCESS
        self.report(rolled, "Rolled back", "warn")
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
        self.report(rolled, "Rolled back", "warn")
        if not applied:
            self.line("Nothing to migrate.")
        else:
            self.report(applied, "Migrated", "success")
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


class MigrateFreshCommand(Confirmable, DatabaseCommand):
    signature = (
        "migrate:fresh {--seed : Run DatabaseSeeder after migrating} "
        "{--seeder= : Seeder class to run, which implies --seed} "
        "{--database= : Connection to rebuild (default: the configured default)} "
        "{--path= : Directories to read migrations from, comma-separated} "
        "{--step : Give each migration its own batch} "
        "{--force : Rebuild without asking, and allow it in production}"
    )
    description = "Drop all tables and re-run every migration"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        if not self.confirm_in_production():
            return self.FAILURE

        applied = self.run_async(migrator.fresh(step=bool(self.option("step"))))
        self.report(applied, "Migrated", "success")
        return self.seed_if_asked()


class MigrateStatusCommand(DatabaseCommand):
    """Show what has run, in which batch, and what is still waiting."""

    signature = (
        "migrate:status "
        "{--database= : Connection to read (default: the configured default)} "
        "{--path= : Directories to read migrations from, comma-separated} "
        "{--pending : Show only the migrations that have not run}"
    )
    description = "Show which migrations have run"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        rows = self.run_async(migrator.status())
        if self.option("pending"):
            rows = [row for row in rows if not row["ran"]]
            if not rows:
                self.success("No pending migrations.")
                return self.SUCCESS
        if not rows:
            self.line("No migrations.")
            return self.SUCCESS
        for row in rows:
            mark = f"Ran [{row['batch']}]" if row["ran"] else "Pending"
            self.line(f"{mark:10} {row['migration']}")
        return self.SUCCESS


class SchemaDumpCommand(DatabaseCommand):
    """Write the current schema to one file, so a fresh database can skip ahead.

    Laravel calls out to `mysqldump`; Almasix reads the schema back through
    the inspector instead, so the dump is the same shape on every engine and
    needs no client binary installed.
    """

    signature = (
        "schema:dump "
        "{--database= : Connection to dump (default: the configured default)} "
        "{--path= : Directories the migrations live in, comma-separated} "
        "{--prune : Delete the migration files the dump now stands in for}"
    )
    description = "Dump the current database schema to database/schema"

    def handle(self) -> int:
        migrator = self.resolve_migrator()
        if migrator is None:
            return self.INVALID
        name = str(self.option("database") or "").strip() or "database"
        destination = self.root() / "database" / "schema" / f"{name}-schema.sql"
        written = self.run_async(migrator.dump_schema(destination))
        self.success(f"Database schema dumped to {written}.")

        if self.option("prune"):
            removed = 0
            for path in migrator.files():
                path.unlink()
                removed += 1
            self.success(f"Pruned {removed} migration file(s).")
        return self.SUCCESS


class DbSeedCommand(DatabaseCommand):
    signature = "db:seed {--class= : Seeder class to run (default: DatabaseSeeder)}"
    description = "Seed the database using DatabaseSeeder (or --class)"

    def handle(self) -> int:
        return self.seed_database(self.option("class"))
