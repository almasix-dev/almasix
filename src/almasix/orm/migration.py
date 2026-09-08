"""Laravel-shaped migrations over the Schema builder."""

from __future__ import annotations

import importlib.util
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

import sqlalchemy as sa

from almasix.orm.connection import pretending
from almasix.orm.dialects import quote_ident
from almasix.orm.facade import DB, get_manager
from almasix.orm.inflector import studly
from almasix.orm.schema import Schema

_FILE_RE = re.compile(r"^(\d{4}_\d{2}_\d{2}_\d{6})_(.+)\.py$")

# Laravel ``TableGuesser`` — derive table + create/update from the migration slug.
_CREATE_PATTERNS = (
    re.compile(r"^create_(\w+)_table$"),
    re.compile(r"^create_(\w+)$"),
)
_CHANGE_PATTERNS = (
    re.compile(r".+_(?:to|from|in)_(\w+)_table$"),
    re.compile(r".+_(?:to|from|in)_(\w+)$"),
)

#: Engines that can roll a failed migration back. MySQL and MariaDB commit
#: every DDL statement as it runs, so wrapping one there would only pretend.
#: SQLite belongs here by rights, but its Python driver runs `CREATE TABLE`
#: outside the transactions it opens, so only the data a migration writes
#: comes back.
_TRANSACTIONAL_DDL = frozenset({"sqlite", "postgresql", "mssql"})


class Migration:
    """One schema change. Subclass and implement `up` / `down`."""

    #: The connection this migration runs on, when it is not the default one.
    connection: str | None = None

    #: Whether to wrap the migration in a transaction, where the engine can.
    within_transaction: bool = True

    async def up(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    async def down(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def should_run(self) -> bool:
        """Whether this migration applies at all — Laravel's ``shouldRun``."""
        return True


class MigrationError(RuntimeError):
    """Raised when a migration file cannot be loaded or applied."""


@dataclass
class MigrationStarted:
    """A migration is about to run."""

    migration: str
    direction: str


@dataclass
class MigrationEnded:
    """A migration has finished, with how long it took in milliseconds."""

    migration: str
    direction: str
    elapsed: float


@dataclass
class NoPendingMigrations:
    """A run found nothing to do."""

    direction: str = "up"


class MigrationResult(str):
    """The name of a migration that ran, and what running it took.

    A migrator has always answered with names, and callers compare against
    them; this is that name, carrying the timing and the pretended queries
    for anyone who asks.
    """

    __slots__ = ("elapsed", "queries", "skipped")

    def __new__(
        cls,
        migration: str,
        elapsed: float = 0.0,
        queries: list[Any] | None = None,
        skipped: bool = False,
    ) -> Self:
        result = super().__new__(cls, migration)
        result.elapsed = elapsed
        result.queries = queries or []
        result.skipped = skipped
        return result

    @property
    def migration(self) -> str:
        return str(self)


def _load(path: Path) -> type[Migration]:
    spec = importlib.util.spec_from_file_location(f"almasix_migration_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise MigrationError(f"Cannot load migration {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for value in vars(module).values():
        if isinstance(value, type) and issubclass(value, Migration) and value is not Migration:
            return value
    raise MigrationError(f"{path.name} does not define a Migration subclass")


class Migrator:
    """Applies ordered Python migrations and records them in `migrations`."""

    table = "migrations"

    def __init__(
        self,
        path: str | Path | Sequence[str | Path],
        connection: str | None = None,
    ) -> None:
        paths = [path] if isinstance(path, (str, Path)) else list(path)
        self.paths = [Path(one) for one in paths]
        self.path = self.paths[0] if self.paths else Path("database/migrations")
        self.connection = connection

    def files(self) -> list[Path]:
        """Every migration in every path, ordered by the stamp in its name."""
        found: dict[str, Path] = {}
        for directory in self.paths:
            if not directory.is_dir():
                continue
            for path in directory.glob("*.py"):
                if _FILE_RE.match(path.name):
                    found.setdefault(path.name, path)
        return [found[name] for name in sorted(found)]

    # --- the repository -----------------------------------------------------

    def _quoted_table(self) -> str:
        """The repository's name, quoted the way this engine quotes names."""
        dialect = get_manager().connection(self.connection).engine.dialect
        return quote_ident(dialect, self.table)

    async def _ensure_table(self) -> None:
        if await Schema.has_table(self.table, connection=self.connection):
            return

        def define(blueprint: Any) -> None:
            blueprint.id()
            blueprint.string("migration")
            blueprint.integer("batch")

        await Schema.create(self.table, define, connection=self.connection)

    async def ran(self) -> list[str]:
        await self._ensure_table()
        rows = await DB.select(
            f"SELECT migration FROM {self._quoted_table()} ORDER BY id",
            connection=self.connection,
        )
        return [str(row["migration"]) for row in rows]

    async def current_batch(self) -> int:
        await self._ensure_table()
        row = await DB.select_one(
            f"SELECT MAX(batch) AS batch FROM {self._quoted_table()}",
            connection=self.connection,
        )
        if not row or row.get("batch") is None:
            return 0
        return int(row["batch"])

    async def batches(self) -> dict[str, int]:
        """Which batch each migration ran in — what ``migrate:status`` shows."""
        await self._ensure_table()
        rows = await DB.select(
            f"SELECT migration, batch FROM {self._quoted_table()} ORDER BY id",
            connection=self.connection,
        )
        return {str(row["migration"]): int(row["batch"]) for row in rows}

    async def any_ran(self) -> bool:
        """Whether anything has been recorded, without creating the repository.

        A squashed schema carries the repository table with it, so asking the
        question must not be what creates it.
        """
        if not await Schema.has_table(self.table, connection=self.connection):
            return False
        rows = await DB.select(
            f"SELECT migration FROM {self._quoted_table()}",
            connection=self.connection,
        )
        return bool(rows)

    async def pending(self) -> list[Path]:
        applied = set(await self.ran())
        return [path for path in self.files() if path.stem not in applied]

    async def _log(self, name: str, batch: int) -> None:
        await DB.statement(
            f"INSERT INTO {self._quoted_table()} (migration, batch) VALUES (:migration, :batch)",
            {"migration": name, "batch": batch},
            connection=self.connection,
        )

    async def _forget(self, name: str) -> None:
        await DB.statement(
            f"DELETE FROM {self._quoted_table()} WHERE migration = :migration",
            {"migration": name},
            connection=self.connection,
        )

    # --- running ------------------------------------------------------------

    async def run(
        self,
        steps: int | None = None,
        *,
        step: bool = False,
        pretend: bool = False,
    ) -> list[MigrationResult]:
        """Apply the pending migrations.

        ``steps`` caps how many run; ``step`` gives each its own batch, so a
        later ``migrate:rollback`` undoes them one at a time.
        """
        waiting = await self.pending()
        if steps is not None:
            waiting = waiting[: max(int(steps), 0)]
        if not waiting:
            _dispatch(NoPendingMigrations("up"))
            return []
        batch = await self.current_batch() + 1
        applied: list[MigrationResult] = []
        for path in waiting:
            result = await self._migrate(path, "up", pretend=pretend)
            if result.skipped:
                continue
            if not pretend:
                await self._log(path.stem, batch)
            applied.append(result)
            if step:
                batch += 1
        return applied

    async def rollback(
        self,
        steps: int | None = None,
        *,
        step: int = 0,
        batch: int = 0,
        pretend: bool = False,
    ) -> list[MigrationResult]:
        """Undo migrations, newest first.

        With nothing asked for, the last batch goes; ``step`` counts
        migrations, as Laravel's does, and ``batch`` names one batch exactly.
        ``steps`` is the older Almasix spelling and counts batches.
        """
        await self._ensure_table()
        names = await self._for_rollback(steps=steps, step=step, batch=batch)
        if not names:
            _dispatch(NoPendingMigrations("down"))
            return []
        lookup = {path.stem: path for path in self.files()}
        rolled: list[MigrationResult] = []
        for name in names:
            path = lookup.get(name)
            if path is None:
                raise MigrationError(f"Migration file missing for {name}")
            result = await self._migrate(path, "down", pretend=pretend)
            if result.skipped:
                continue
            if not pretend:
                await self._forget(name)
            rolled.append(result)
        return rolled

    async def _for_rollback(self, *, steps: int | None, step: int, batch: int) -> list[str]:
        """The migration names one rollback should undo, newest first."""
        table = self._quoted_table()
        if step > 0:
            rows = await DB.select(
                f"SELECT migration FROM {table} ORDER BY id DESC",
                connection=self.connection,
            )
            return [str(row["migration"]) for row in rows][:step]
        if batch > 0:
            rows = await DB.select(
                f"SELECT migration FROM {table} WHERE batch = :batch ORDER BY id DESC",
                {"batch": batch},
                connection=self.connection,
            )
            return [str(row["migration"]) for row in rows]
        last = await self.current_batch()
        if last == 0:
            return []
        target = max(last - max(int(steps or 1), 1) + 1, 1)
        rows = await DB.select(
            f"SELECT migration FROM {table} WHERE batch >= :batch ORDER BY id DESC",
            {"batch": target},
            connection=self.connection,
        )
        return [str(row["migration"]) for row in rows]

    async def _migrate(self, path: Path, direction: str, *, pretend: bool) -> MigrationResult:
        """Run one migration's ``up`` or ``down``, wrapped as it asks to be."""
        instance = _load(path)()
        if not instance.should_run():
            return MigrationResult(path.stem, skipped=True)

        method = getattr(instance, direction)
        connection = get_manager().connection(instance.connection or self.connection)

        if pretend:
            with pretending() as recorded:
                await method()
            return MigrationResult(path.stem, queries=list(recorded))

        _dispatch(MigrationStarted(path.stem, direction))
        started = time.perf_counter()
        if instance.within_transaction and connection.engine.dialect.name in _TRANSACTIONAL_DDL:
            async with connection.transaction():
                await method()
        else:
            await method()
        elapsed = (time.perf_counter() - started) * 1000
        _dispatch(MigrationEnded(path.stem, direction, elapsed))
        return MigrationResult(path.stem, elapsed=elapsed)

    async def install(self) -> bool:
        """Create the repository table, reporting whether this call created it."""
        if await Schema.has_table(self.table, connection=self.connection):
            return False
        await self._ensure_table()
        return True

    async def reset(self, *, pretend: bool = False) -> list[MigrationResult]:
        """Roll back every migration that has run, newest first."""
        batch = await self.current_batch()
        if batch == 0:
            _dispatch(NoPendingMigrations("down"))
            return []
        return await self.rollback(batch, pretend=pretend)

    async def refresh(
        self,
        steps: int = 0,
        *,
        step: int = 0,
        pretend: bool = False,
    ) -> tuple[list[MigrationResult], list[MigrationResult]]:
        """Roll back and run again, returning ``(rolled back, applied)``.

        ``steps`` rolls back that many batches instead of all of them, and
        ``step`` that many migrations, so the ones below them stay applied.
        """
        if step:
            rolled = await self.rollback(step=step, pretend=pretend)
        elif steps:
            rolled = await self.rollback(steps, pretend=pretend)
        else:
            rolled = await self.reset(pretend=pretend)
        return rolled, await self.run(pretend=pretend)

    async def fresh(self, *, pretend: bool = False, step: bool = False) -> list[MigrationResult]:
        """Drop everything and start again, foreign keys notwithstanding."""
        await Schema.drop_all_tables(connection=self.connection)
        return await self.run(step=step, pretend=pretend)

    async def status(self) -> list[dict[str, Any]]:
        batches = await self.batches()
        return [
            {
                "migration": path.stem,
                "ran": path.stem in batches,
                "batch": batches.get(path.stem),
            }
            for path in self.files()
        ]

    # --- squashing ----------------------------------------------------------

    async def dump_schema(self, destination: Path) -> Path:
        """Write the current schema, and the migrations behind it, to one file.

        Laravel shells out to `mysqldump`; Almasix reads the schema back
        through the inspector, so the dump is the same on every engine and
        needs no client binary installed.
        """
        dialect = get_manager().connection(self.connection).engine.dialect
        lines = [
            "-- Almasix schema dump",
            f"-- Written {datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC",
            "",
        ]
        for name in await Schema.table_names(connection=self.connection):
            lines.extend(await _dump_table(name, dialect, self.connection))
        for migration in await self.ran():
            lines.append(
                f"INSERT INTO {quote_ident(dialect, self.table)} (migration, batch) "
                f"VALUES ('{migration}', 1);"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return destination

    async def load_schema(self, source: Path) -> int:
        """Replay a dumped schema, returning how many statements it held."""
        if not source.is_file():
            raise MigrationError(f"No schema dump at {source}")
        body = "\n".join(
            line
            for line in source.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("--")
        )
        statements = [
            statement.strip().rstrip(";")
            for statement in body.split(";\n")
            if statement.strip().rstrip(";").strip()
        ]
        for statement in statements:
            await DB.statement(statement, connection=self.connection)
        return len(statements)


async def _dump_table(name: str, dialect: Any, connection: str | None) -> list[str]:
    """One table's ``CREATE TABLE`` and indexes, as text."""
    manager = get_manager()
    engine = manager.connection(manager.direct_name(connection)).engine

    def read(sync_conn: Any) -> list[str]:
        metadata = sa.MetaData()
        table = sa.Table(name, metadata, autoload_with=sync_conn)
        written = [str(sa.schema.CreateTable(table).compile(dialect=dialect)).strip() + ";"]
        written.extend(
            str(sa.schema.CreateIndex(index).compile(dialect=dialect)).strip() + ";"
            for index in sorted(table.indexes, key=lambda index: index.name or "")
        )
        return written

    async with engine.connect() as conn:
        return await conn.run_sync(read)


def _dispatch(event: Any) -> None:
    """Tell anyone listening, without making the migrator depend on there being one."""
    from almasix.events.helpers import dispatch

    try:
        dispatch(event)
    except Exception:  # noqa: BLE001 — a listener must never break a migration
        return


def guess_migration(name: str) -> tuple[str | None, bool]:
    """Infer ``(table, create)`` from a snake_case migration name (Laravel TableGuesser).

    Alter patterns (``*_to_*_table``, ``*_from_*``, ``*_in_*``) win over create when
    both could match — so ``create_add_slug_to_posts_table`` is treated as an update
    to ``posts``, not ``Schema.create("add_slug_to_posts")``.
    """
    for pattern in _CHANGE_PATTERNS:
        match = pattern.match(name)
        if match:
            return match.group(1), False
    for pattern in _CREATE_PATTERNS:
        match = pattern.match(name)
        if match:
            return match.group(1), True
    return None, False


def make_migration(
    name: str,
    directory: Path,
    *,
    table: str | None = None,
    create: bool = False,
    base_path: Path | None = None,
) -> Path:
    """Write a timestamped migration stub and return its path.

    When ``table`` is omitted, the name is parsed like Laravel:

    - ``create_users_table`` / ``create_users`` → create stub for ``users``
    - ``add_foo_to_posts_table`` / ``*_from_*`` / ``*_in_*`` → update stub
    - otherwise → blank stub

    The generated class is always StudlyCase of the full slug
    (``CreateUsersTable``, ``AddDescriptionColumnToPostsTable``).
    ``--create`` / ``--table`` (passed as ``create`` / ``table``) override inference.
    """
    # Imported here, not at module scope: the console is a layer above the ORM,
    # and importing down from up makes the two mutually importing.
    from almasix.console.stub import render

    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise MigrationError("A migration name is required.")
    stamp = datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stamp}_{slug}.py"

    if table is None:
        table, create = guess_migration(slug)

    class_name = studly(slug)
    if table and create:
        stub = "migration.create.stub"
    elif table:
        stub = "migration.update.stub"
    else:
        stub = "migration.stub"
    body = render(stub, {"class": class_name, "table": table or ""}, base_path=base_path)
    path.write_text(body, encoding="utf-8")
    return path


# Callable kept for type checkers looking at Schema.create callbacks.
MigrationCallback = Callable[..., Any]
