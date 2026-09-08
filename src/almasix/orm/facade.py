"""`DB` façade — raw access and transactions without touching SQLAlchemy."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import text as _text
from sqlalchemy.sql import ClauseElement

from almasix.orm.connection import (
    Connection,
    DatabaseManager,
    QueryExecuted,
    pretending,
    reset_total_query_duration,
    total_query_duration,
)

_manager: DatabaseManager | None = None

#: Driver messages that mean "try again", not "give up" — Laravel keeps the
#: same list, because no driver agrees with another on how to say it.
_DEADLOCK_MESSAGES = (
    "deadlock found",
    "deadlock detected",
    "lock wait timeout exceeded",
    "has been chosen as the deadlock victim",
    "database is locked",
    "database table is locked",
    "a table in the database is locked",
    "the database file is locked",
    "could not serialize access",
    "wsrep detected deadlock",
)


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


def _is_deadlock(error: BaseException) -> bool:
    message = str(error).lower()
    return any(fragment in message for fragment in _DEADLOCK_MESSAGES)


class _Transaction:
    """What `DB.transaction` gives back — a block, or an awaitable run.

    ``async with DB.transaction():`` wraps a block of statements, and
    ``await DB.transaction(work, attempts=5)`` runs a callable and retries it
    when the engine reports a deadlock. Laravel spells both `DB::transaction`,
    so this does too.
    """

    def __init__(
        self,
        connection: Connection,
        callback: Callable[..., Any] | None,
        attempts: int,
    ) -> None:
        self._connection = connection
        self._callback = callback
        self._attempts = max(int(attempts), 1)
        self._block: Any = None

    async def __aenter__(self) -> Any:
        self._block = self._connection.transaction()
        return await self._block.__aenter__()

    async def __aexit__(self, *exception: object) -> Any:
        return await self._block.__aexit__(*exception)

    def __await__(self) -> Any:
        if self._callback is None:
            raise TypeError("await DB.transaction(callback) needs a callback to run.")
        return self._run().__await__()

    async def _run(self) -> Any:
        assert self._callback is not None
        for attempt in range(1, self._attempts + 1):
            try:
                async with self._connection.transaction() as handle:
                    outcome = self._callback(handle) if _takes_handle(self._callback) else self._callback()
                    if inspect.isawaitable(outcome):
                        outcome = await outcome
                    return outcome
            except Exception as error:
                if attempt >= self._attempts or not _is_deadlock(error):
                    raise
                await asyncio.sleep(0)
        return None  # pragma: no cover - the loop either returns or raises


def _takes_handle(callback: Callable[..., Any]) -> bool:
    """Whether the callback wants the connection handle passed to it."""
    try:
        return bool(inspect.signature(callback).parameters)
    except (TypeError, ValueError):  # pragma: no cover - builtins
        return False


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
    async def scalar(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        connection: str | None = None,
    ) -> Any:
        """One value out of a query that returns exactly one."""
        return await DB.connection(connection).scalar(statement, parameters)

    @staticmethod
    async def statement(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
        connection: str | None = None,
    ) -> int:
        result = await DB.connection(connection).execute(statement, parameters)
        return int(result.rowcount or 0)

    @staticmethod
    async def insert(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
        connection: str | None = None,
    ) -> bool:
        """Run an insert; True once it has run, as Laravel's `DB::insert` returns."""
        await DB.connection(connection).execute(statement, parameters)
        return True

    @staticmethod
    async def update(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        connection: str | None = None,
    ) -> int:
        """Run an update; the number of rows it changed."""
        result = await DB.connection(connection).execute(statement, parameters)
        return int(result.rowcount or 0)

    @staticmethod
    async def delete(
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        connection: str | None = None,
    ) -> int:
        """Run a delete; the number of rows it removed."""
        result = await DB.connection(connection).execute(statement, parameters)
        return int(result.rowcount or 0)

    @staticmethod
    async def unprepared(sql: str, connection: str | None = None) -> bool:
        """Run SQL exactly as written, with no bindings prepared."""
        return await DB.connection(connection).unprepared(sql)

    @staticmethod
    def table(name: str, connection: str | None = None) -> Any:
        """Query builder against a bare table (no model)."""
        from almasix.orm.builder import QueryBuilder

        return QueryBuilder.for_table(name, connection=connection)

    @staticmethod
    def transaction(
        callback: Callable[..., Any] | None = None,
        attempts: int = 1,
        connection: str | None = None,
    ) -> _Transaction:
        """A transaction as a block, or as a callable that retries on deadlock."""
        return _Transaction(DB.connection(connection), callback, attempts)

    @staticmethod
    async def begin_transaction(connection: str | None = None) -> None:
        await DB.connection(connection).begin_transaction()

    @staticmethod
    async def commit(connection: str | None = None) -> None:
        await DB.connection(connection).commit()

    @staticmethod
    async def rollback(connection: str | None = None) -> None:
        await DB.connection(connection).rollback()

    @staticmethod
    def transaction_level(connection: str | None = None) -> int:
        return DB.connection(connection).transaction_level()

    @staticmethod
    def after_commit(callback: Callable[[], Any], connection: str | None = None) -> None:
        """Run `callback` when the open transaction commits — or now, if none is."""
        DB.connection(connection).after_commit(callback)

    @staticmethod
    async def pretend(
        callback: Callable[..., Any],
        connection: str | None = None,
    ) -> list[QueryExecuted]:
        """Collect the queries a callable would run, without running any of them."""
        with pretending() as recorded:
            outcome = callback(DB.connection(connection)) if _takes_handle(callback) else callback()
            if inspect.isawaitable(outcome):
                await outcome
        return recorded

    @staticmethod
    def listen(callback: Callable[[QueryExecuted], Any]) -> None:
        """Watch every statement the application runs."""
        get_manager().listen(callback)

    @staticmethod
    def when_querying_for_longer_than(
        milliseconds: float,
        callback: Callable[[Connection, QueryExecuted], Any],
    ) -> None:
        """Hear about it when one request spends too long in the database."""
        get_manager().when_querying_for_longer_than(milliseconds, callback)

    @staticmethod
    def total_query_duration() -> float:
        return total_query_duration()

    @staticmethod
    def reset_total_query_duration() -> None:
        reset_total_query_duration()

    @staticmethod
    def raw(sql: str) -> ClauseElement:
        return raw(sql)

    @staticmethod
    async def disconnect(name: str | None = None) -> None:
        await get_manager().disconnect(name)
