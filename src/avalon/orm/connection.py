"""Database connections — async engines over SQLAlchemy Core."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import ClauseElement

from avalon.orm.dialects import build_async_url, ensure_async_driver

# Active transaction connection, request/task scoped so concurrent requests
# never share a connection.
_active: ContextVar[dict[str, AsyncConnection] | None] = ContextVar(
    "avalon_db_transactions", default=None
)


class ConnectionError_(RuntimeError):
    """Raised when a connection name is not configured."""


def _normalize_url(config: Mapping[str, Any]) -> str:
    """Build an async SQLAlchemy URL from a Laravel-shaped connection dict."""
    try:
        return build_async_url(dict(config))
    except ValueError as exc:
        raise ConnectionError_(str(exc)) from exc


def _ensure_async_driver(url: str) -> str:
    """Upgrade a sync URL to its async driver so app config stays familiar."""
    return ensure_async_driver(url)


class Connection:
    """One named database connection."""

    def __init__(self, name: str, config: Mapping[str, Any]) -> None:
        self.name = name
        self.config = dict(config)
        self.url = _normalize_url(config)
        if self.url.startswith("sqlite") and ":memory:" not in self.url:
            # sqlite+aiosqlite:///relative/or/absolute/path
            raw = str(config.get("database") or "")
            if raw and raw != ":memory:":
                from pathlib import Path as FilePath

                FilePath(raw).parent.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {"future": True}
        if self.url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
            # :memory: otherwise gives every acquire() a brand-new empty database.
            if ":memory:" in self.url or self.url in {"sqlite+aiosqlite://", "sqlite+aiosqlite:///"}:
                options["poolclass"] = StaticPool
        else:
            options["pool_pre_ping"] = True
        self._engine: AsyncEngine = create_async_engine(self.url, **options)
        if self.url.startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(self._engine.sync_engine, "connect")
            def _sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:  # pragma: no cover
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    def current(self) -> AsyncConnection | None:
        """Connection bound to the active transaction, if any."""
        bag = _active.get()
        return bag.get(self.name) if bag else None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[AsyncConnection]:
        """Reuse the transaction connection, else open a short-lived one."""
        existing = self.current()
        if existing is not None:
            yield existing
            return
        async with self._engine.begin() as connection:
            yield connection

    async def execute(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    ) -> CursorResult[Any]:
        compiled = text(statement) if isinstance(statement, str) else statement
        async with self.acquire() as connection:
            if parameters is None:
                return await connection.execute(compiled)
            return await connection.execute(compiled, parameters)

    async def select(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = await self.execute(statement, parameters)
        return [dict(row) for row in result.mappings().all()]

    async def select_one(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = await self.select(statement, parameters)
        return rows[0] if rows else None

    async def stream(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        *,
        chunk_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield rows as the driver produces them, without buffering the set."""
        compiled = text(statement) if isinstance(statement, str) else statement
        async with self.acquire() as connection:
            result = await connection.stream(
                compiled, parameters, execution_options={"yield_per": chunk_size}
            )
            async for row in result.mappings():
                yield dict(row)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        """Run in a transaction; nested calls use SAVEPOINTs."""
        bag = _active.get()
        existing = bag.get(self.name) if bag else None

        if existing is not None:
            async with existing.begin_nested():
                yield existing
            return

        async with self._engine.connect() as connection:
            new_bag = dict(bag or {})
            new_bag[self.name] = connection
            token = _active.set(new_bag)
            transaction = await connection.begin()
            try:
                yield connection
            except BaseException:
                await transaction.rollback()
                raise
            else:
                await transaction.commit()
            finally:
                _active.reset(token)

    async def disconnect(self) -> None:
        await self._engine.dispose()


class DatabaseManager:
    """Resolves named connections from `config/database.py`."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        config = dict(config or {})
        self.default: str = str(config.get("default", "sqlite"))
        self._definitions: dict[str, Any] = dict(config.get("connections", {}) or {})
        self._connections: dict[str, Connection] = {}

    def connection(self, name: str | None = None) -> Connection:
        key = name or self.default
        if key not in self._connections:
            if key not in self._definitions:
                raise ConnectionError_(f"Database connection {key!r} is not configured.")
            self._connections[key] = Connection(key, self._definitions[key])
        return self._connections[key]

    def add_connection(self, name: str, config: Mapping[str, Any]) -> None:
        self._definitions[name] = dict(config)
        self._connections.pop(name, None)

    def connection_names(self) -> list[str]:
        return sorted(self._definitions)

    async def disconnect(self, name: str | None = None) -> None:
        if name is None:
            for connection in list(self._connections.values()):
                await connection.disconnect()
            self._connections.clear()
            return
        connection = self._connections.pop(name, None)
        if connection is not None:
            await connection.disconnect()
