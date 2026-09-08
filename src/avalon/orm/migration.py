"""Laravel-shaped migrations over the Schema builder."""

from __future__ import annotations

import importlib.util
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from avalon.console.stub import render
from avalon.orm.facade import DB
from avalon.orm.inflector import studly
from avalon.orm.schema import Schema

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


class Migration:
    """One schema change. Subclass and implement `up` / `down`."""

    async def up(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    async def down(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError


class MigrationError(RuntimeError):
    """Raised when a migration file cannot be loaded or applied."""


def _load(path: Path) -> type[Migration]:
    spec = importlib.util.spec_from_file_location(f"avalon_migration_{path.stem}", path)
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

    def __init__(self, path: str | Path, connection: str | None = None) -> None:
        self.path = Path(path)
        self.connection = connection

    def files(self) -> list[Path]:
        if not self.path.is_dir():
            return []
        found = [path for path in self.path.glob("*.py") if _FILE_RE.match(path.name)]
        return sorted(found, key=lambda path: path.name)

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
            f'SELECT migration FROM "{self.table}" ORDER BY id',
            connection=self.connection,
        )
        return [str(row["migration"]) for row in rows]

    async def current_batch(self) -> int:
        await self._ensure_table()
        row = await DB.select_one(
            f'SELECT MAX(batch) AS batch FROM "{self.table}"',
            connection=self.connection,
        )
        if not row or row.get("batch") is None:
            return 0
        return int(row["batch"])

    async def pending(self) -> list[Path]:
        applied = set(await self.ran())
        return [path for path in self.files() if path.stem not in applied]

    async def run(self, steps: int | None = None) -> list[str]:
        waiting = await self.pending()
        if steps is not None:
            waiting = waiting[: max(int(steps), 0)]
        if not waiting:
            return []
        batch = await self.current_batch() + 1
        applied: list[str] = []
        for path in waiting:
            instance = _load(path)()
            await instance.up()
            await DB.statement(
                f'INSERT INTO "{self.table}" (migration, batch) VALUES (:migration, :batch)',
                {"migration": path.stem, "batch": batch},
                connection=self.connection,
            )
            applied.append(path.stem)
        return applied

    async def rollback(self, steps: int = 1) -> list[str]:
        await self._ensure_table()
        batch = await self.current_batch()
        if batch == 0:
            return []
        target = max(batch - max(int(steps), 1) + 1, 1)
        rows = await DB.select(
            f'SELECT migration FROM "{self.table}" WHERE batch >= :batch ORDER BY id DESC',
            {"batch": target},
            connection=self.connection,
        )
        rolled: list[str] = []
        lookup = {path.stem: path for path in self.files()}
        for row in rows:
            name = str(row["migration"])
            path = lookup.get(name)
            if path is None:
                raise MigrationError(f"Migration file missing for {name}")
            instance = _load(path)()
            await instance.down()
            await DB.statement(
                f'DELETE FROM "{self.table}" WHERE migration = :migration',
                {"migration": name},
                connection=self.connection,
            )
            rolled.append(name)
        return rolled

    async def fresh(self) -> list[str]:
        names = await Schema.table_names(connection=self.connection)
        for name in names:
            await Schema.drop_if_exists(name, connection=self.connection)
        return await self.run()

    async def status(self) -> list[dict[str, Any]]:
        applied = set(await self.ran())
        rows = []
        for path in self.files():
            rows.append({"migration": path.stem, "ran": path.stem in applied})
        return rows


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
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise MigrationError("A migration name is required.")
    stamp = datetime.now(timezone.utc).strftime("%Y_%m_%d_%H%M%S")
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
