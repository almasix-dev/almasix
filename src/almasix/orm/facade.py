"""`DB` façade — raw access and transactions without touching SQLAlchemy."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text as _text
from sqlalchemy.sql import ClauseElement

from almasix.orm.connection import Connection, DatabaseManager

_manager: DatabaseManager | None = None


def set_manager(manager: DatabaseManager | None) -> None:
    global _manager
    _manager = manager


def get_manager() -> DatabaseManager:
    if _manager is None:
        raise RuntimeError(
            "Database is not configured. Bootstrap the Application or call "
            "almasix.orm.set_manager() first."
        )
    return _manager


def raw(sql: str) -> ClauseElement:
    """Escape hatch for a raw SQL fragment."""
    return _text(sql)


class DB:
    """Static façade mirroring Laravel's `DB`."""

    @staticmethod
    def connection(name: str | None = None) -> Connection:
        return get_manager().connection(name)

    @staticmethod
    async def select(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        connection: str | None = None,
    ) -> list[dict[str, Any]]:
        return await DB.connection(connection).select(statement, parameters)

    @staticmethod
    async def select_one(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        connection: str | None = None,
    ) -> dict[str, Any] | None:
        return await DB.connection(connection).select_one(statement, parameters)

    @staticmethod
    async def statement(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
        connection: str | None = None,
    ) -> int:
        result = await DB.connection(connection).execute(statement, parameters)
        return int(result.rowcount or 0)

    @staticmethod
    def table(name: str, connection: str | None = None) -> Any:
        """Query builder against a bare table (no model)."""
        from almasix.orm.builder import QueryBuilder

        return QueryBuilder.for_table(name, connection=connection)

    @staticmethod
    @asynccontextmanager
    async def transaction(connection: str | None = None) -> AsyncIterator[Any]:
        async with DB.connection(connection).transaction() as handle:
            yield handle

    @staticmethod
    def raw(sql: str) -> ClauseElement:
        return raw(sql)

    @staticmethod
    async def disconnect(name: str | None = None) -> None:
        await get_manager().disconnect(name)
