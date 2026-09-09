"""Database assertions, and the two ways a test can keep its database clean.

Laravel's `assertDatabaseHas` and the `RefreshDatabase` / `DatabaseTransactions`
traits. Everything here is a coroutine, because every query in Almasix is.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from almasix.orm.facade import get_manager


async def assert_database_has(
    table: str | Any,
    data: Mapping[str, Any] | None = None,
    *,
    connection: str | None = None,
) -> None:
    """A row like this exists. `table` may be a model class."""
    name, data = _table_and_data(table, data)
    if await _count(name, data, connection) == 0:
        rows = await _sample(name, connection)
        raise AssertionError(f"No row in [{name}] matches {dict(data)}. The table holds: {rows}.")


async def assert_database_missing(
    table: str | Any,
    data: Mapping[str, Any] | None = None,
    *,
    connection: str | None = None,
) -> None:
    name, data = _table_and_data(table, data)
    found = await _count(name, data, connection)
    if found:
        raise AssertionError(f"{found} row(s) in [{name}] match {dict(data)}, and none should.")


async def assert_database_count(
    table: str | Any,
    count: int,
    *,
    connection: str | None = None,
) -> None:
    name, _ = _table_and_data(table, None)
    found = await _count(name, {}, connection)
    if found != count:
        raise AssertionError(f"Expected {count} row(s) in [{name}]; found {found}.")


async def assert_database_empty(table: str | Any, *, connection: str | None = None) -> None:
    await assert_database_count(table, 0, connection=connection)


async def assert_model_exists(model: Any) -> None:
    """This model is still in the database, by key."""
    table = type(model).get_table()
    key = type(model).primary_key
    if await _count(table, {key: model.get_key()}, _connection_of(model)) == 0:
        raise AssertionError(f"[{type(model).__name__}] {model.get_key()!r} is not in [{table}].")


async def assert_model_missing(model: Any) -> None:
    table = type(model).get_table()
    key = type(model).primary_key
    if await _count(table, {key: model.get_key()}, _connection_of(model)):
        raise AssertionError(f"[{type(model).__name__}] {model.get_key()!r} is still in [{table}].")


async def assert_soft_deleted(
    model: Any,
    data: Mapping[str, Any] | None = None,
    *,
    column: str = "deleted_at",
) -> None:
    """The row is still there, and it is trashed."""
    table = type(model).get_table()
    wanted = {type(model).primary_key: model.get_key(), **dict(data or {})}
    rows = await _rows(table, wanted, _connection_of(model))
    if not rows:
        raise AssertionError(f"No row in [{table}] matches {wanted}.")
    if all(row.get(column) is None for row in rows):
        raise AssertionError(f"The row in [{table}] is not soft deleted; [{column}] is null.")


async def assert_not_soft_deleted(
    model: Any,
    data: Mapping[str, Any] | None = None,
    *,
    column: str = "deleted_at",
) -> None:
    table = type(model).get_table()
    wanted = {type(model).primary_key: model.get_key(), **dict(data or {})}
    rows = await _rows(table, wanted, _connection_of(model))
    if not rows:
        raise AssertionError(f"No row in [{table}] matches {wanted}.")
    trashed = [row for row in rows if row.get(column) is not None]
    if trashed:
        raise AssertionError(f"The row in [{table}] is soft deleted, at {trashed[0][column]}.")


# --- keeping the database clean ----------------------------------------------


@asynccontextmanager
async def database_transactions(connection: str | None = None) -> AsyncIterator[Any]:
    """Run a test inside a transaction, and roll it back on the way out.

    Laravel's `DatabaseTransactions`. Nothing the test wrote survives it, and
    nothing it wrote was ever visible to another connection.
    """
    handle = get_manager().connection(connection)
    rollback = _Rollback()
    try:
        async with handle.transaction():
            yield handle
            raise rollback
    except _Rollback as raised:
        if raised is not rollback:  # pragma: no cover - defensive
            raise


async def refresh_database(
    *,
    connection: str | None = None,
    path: str | Path | None = None,
) -> list[str]:
    """Migrate a fresh database for this test (Laravel's `RefreshDatabase`).

    Drops every table and runs the migrations again, so a test starts from the
    schema on disk rather than from whatever the last test left behind.
    """
    from almasix.orm.migration import Migrator

    directory = Path(path) if path else Path.cwd() / "database" / "migrations"
    return await Migrator(directory, connection).fresh()


# --- internals ----------------------------------------------------------------


class _Rollback(Exception):
    """Leaves the transaction the only way a context manager can: by raising."""


def _table_and_data(
    table: str | Any,
    data: Mapping[str, Any] | None,
) -> tuple[str, Mapping[str, Any]]:
    if isinstance(table, str):
        return table, dict(data or {})
    name = table.get_table() if isinstance(table, type) else type(table).get_table()
    return name, dict(data or {})


def _connection_of(model: Any) -> str | None:
    name = getattr(model, "get_connection_name", None)
    return name() if callable(name) else getattr(type(model), "connection", None)


async def _rows(
    table: str,
    data: Mapping[str, Any],
    connection: str | None,
) -> list[dict[str, Any]]:
    from almasix.orm.builder import QueryBuilder

    query = QueryBuilder(table=table, connection=connection)
    for column, value in data.items():
        query.where(column, value)
    return [dict(row) for row in await query.get()]


async def _count(table: str, data: Mapping[str, Any], connection: str | None) -> int:
    return len(await _rows(table, data, connection))


async def _sample(table: str, connection: str | None, limit: int = 3) -> str:
    """The first few rows, so a failure says what the table actually holds."""
    from almasix.orm.builder import QueryBuilder

    rows = await QueryBuilder(table=table, connection=connection).limit(limit).get()
    if not rows:
        return "nothing"
    return ", ".join(str(dict(row)) for row in rows)
