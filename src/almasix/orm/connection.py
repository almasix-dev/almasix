"""Database connections — async engines over SQLAlchemy Core."""

from __future__ import annotations

import dataclasses
import time
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import ClauseElement

from almasix.orm.dialects import build_async_url, ensure_async_driver

# Active transaction connection, request/task scoped so concurrent requests
# never share a connection.
_active: ContextVar[dict[str, AsyncConnection] | None] = ContextVar(
    "almasix_db_transactions", default=None
)

# Transactions the caller opened by hand and will close by hand, innermost
# last. Nesting adds a SAVEPOINT, as the block form does.
_manual: ContextVar[dict[str, list[Any]] | None] = ContextVar("almasix_db_manual", default=None)

# Work deferred until the outermost transaction commits — Laravel's
# `DB::afterCommit`. Scoped like `_active` so one request cannot run another's.
_deferred: ContextVar[dict[str, list[Callable[[], Any]]] | None] = ContextVar(
    "almasix_db_after_commit", default=None
)

# Connections written to in this context, for the `sticky` option.
_written: ContextVar[frozenset[str]] = ContextVar("almasix_db_written", default=frozenset())

# Queries this context has run, and how long they took in total.
_elapsed: ContextVar[float] = ContextVar("almasix_db_elapsed", default=0.0)

# When set, queries are collected instead of run — Laravel's `DB::pretend`.
_pretending: ContextVar[list[QueryExecuted] | None] = ContextVar(
    "almasix_db_pretending", default=None
)


class ConnectionError_(RuntimeError):
    """Raised when a connection name is not configured."""


@dataclasses.dataclass(frozen=True)
class QueryExecuted:
    """One statement, as a listener sees it — Laravel's ``QueryExecuted``."""

    sql: str
    bindings: list[Any]
    time: float
    connection_name: str

    def to_raw_sql(self) -> str:
        """The SQL with its bindings written in, for reading rather than running."""
        rendered = self.sql
        for binding in self.bindings:
            rendered = rendered.replace("?", _quote_binding(binding), 1)
        return rendered


def _quote_binding(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _normalize_url(config: Mapping[str, Any]) -> str:
    """Build an async SQLAlchemy URL from a Laravel-shaped connection dict."""
    try:
        return build_async_url(dict(config))
    except ValueError as exc:
        raise ConnectionError_(str(exc)) from exc


def _ensure_async_driver(url: str) -> str:
    """Upgrade a sync URL to its async driver so app config stays familiar."""
    return ensure_async_driver(url)


def _engine_options(url: str) -> dict[str, Any]:
    options: dict[str, Any] = {"future": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        # :memory: otherwise gives every acquire() a brand-new empty database.
        if ":memory:" in url or url in {"sqlite+aiosqlite://", "sqlite+aiosqlite:///"}:
            options["poolclass"] = StaticPool
    else:
        options["pool_pre_ping"] = True
    return options


def _merge(base: Mapping[str, Any], override: Any) -> dict[str, Any]:
    """A read/write/direct block, layered over the connection it belongs to."""
    merged = {key: value for key, value in base.items() if key not in {"read", "write", "direct"}}
    if isinstance(override, Mapping):
        merged.update({key: value for key, value in override.items() if value not in (None, "")})
    return merged


class Connection:
    """One named database connection.

    A connection may front two engines: Laravel lets `read` and `write` blocks
    point at different hosts, and then reads go to one and writes to the
    other. With `sticky` on, a context that has written reads from the write
    engine for the rest of its life, so it can see its own rows.
    """

    def __init__(self, name: str, config: Mapping[str, Any]) -> None:
        self.name = name
        self.config = dict(config)
        self.sticky = bool(self.config.get("sticky", False))
        write_config = _merge(self.config, self.config.get("write"))
        read_config = _merge(self.config, self.config.get("read"))
        self.url = _normalize_url(write_config)
        self._prepare_sqlite_path(write_config)
        self._engine: AsyncEngine = self._build(self.url)
        if "read" in self.config or "write" in self.config:
            self.read_url = _normalize_url(read_config)
            self._prepare_sqlite_path(read_config)
            self._read_engine: AsyncEngine = self._build(self.read_url)
        else:
            self.read_url = self.url
            self._read_engine = self._engine

    def _prepare_sqlite_path(self, config: Mapping[str, Any]) -> None:
        raw = str(config.get("database") or "")
        if not self.url.startswith("sqlite") or not raw or raw == ":memory:":
            return
        from pathlib import Path as FilePath

        FilePath(raw).parent.mkdir(parents=True, exist_ok=True)

    def _build(self, url: str) -> AsyncEngine:
        engine = create_async_engine(url, **_engine_options(url))
        if url.startswith("sqlite"):
            from sqlalchemy import event

            @event.listens_for(engine.sync_engine, "connect")
            def _sqlite_foreign_keys(
                dbapi_connection: Any, _record: Any
            ) -> None:  # pragma: no cover
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        return engine

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def read_engine(self) -> AsyncEngine:
        """The engine reads go to — the write engine unless `read` is configured."""
        if self.sticky and self.name in _written.get():
            return self._engine
        return self._read_engine

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    def current(self) -> AsyncConnection | None:
        """Connection bound to the active transaction, if any."""
        bag = _active.get()
        return bag.get(self.name) if bag else None

    def _mark_written(self) -> None:
        _written.set(_written.get() | {self.name})

    @asynccontextmanager
    async def acquire(self, *, write: bool = True) -> AsyncIterator[AsyncConnection]:
        """Reuse the transaction connection, else open a short-lived one."""
        existing = self.current()
        if existing is not None:
            yield existing
            return
        engine = self._engine if write else self.read_engine
        async with engine.begin() as connection:
            yield connection

    # --- running statements -------------------------------------------------

    async def execute(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
        *,
        write: bool = True,
    ) -> CursorResult[Any]:
        compiled = text(statement) if isinstance(statement, str) else statement
        recorded = _pretending.get()
        if recorded is not None:
            recorded.append(self._describe(compiled, parameters, 0.0))
            return PretendResult()
        if write:
            self._mark_written()
        started = time.perf_counter()
        async with self.acquire(write=write) as connection:
            if parameters is None:
                result = await connection.execute(compiled)
            else:
                result = await connection.execute(compiled, parameters)
        self._record(compiled, parameters, (time.perf_counter() - started) * 1000)
        return result

    def _describe(
        self,
        statement: Any,
        parameters: Any,
        elapsed: float,
    ) -> QueryExecuted:
        """What a listener is told about a statement."""
        try:
            compiled = statement.compile(dialect=self._engine.dialect)
            sql = str(compiled)
            bindings = [compiled.params[key] for key in compiled.positiontup or compiled.params]
        except Exception:
            sql = str(statement)
            bindings = []
        if isinstance(parameters, Mapping):
            bindings = list(parameters.values())
        elif isinstance(parameters, Sequence):
            # An insert of several rows arrives as one statement per row's
            # worth of bindings; a listener wants to see all of them.
            bindings = [value for row in parameters for value in dict(row).values()]
        return QueryExecuted(sql=sql, bindings=bindings, time=elapsed, connection_name=self.name)

    def _record(self, statement: Any, parameters: Any, elapsed: float) -> None:
        """Tell the manager's listeners, and add to this context's total."""
        from almasix.orm.facade import get_manager

        try:
            manager = get_manager()
        except RuntimeError:  # pragma: no cover - a connection built by hand
            return
        _elapsed.set(_elapsed.get() + elapsed)
        manager.notify(lambda: self._describe(statement, parameters, elapsed), self)

    async def select(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        result = await self.execute(statement, parameters, write=False)
        return [dict(row) for row in result.mappings().all()]

    async def select_one(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        rows = await self.select(statement, parameters)
        return rows[0] if rows else None

    async def scalar(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
    ) -> Any:
        """The first column of the first row, for queries that return one value."""
        row = await self.select_one(statement, parameters)
        return next(iter(row.values()), None) if row else None

    async def unprepared(self, sql: str) -> bool:
        """Run SQL with no bindings at all, for statements drivers refuse to prepare."""
        from sqlalchemy import exc as sa_exc

        recorded = _pretending.get()
        if recorded is not None:
            recorded.append(
                QueryExecuted(sql=sql, bindings=[], time=0.0, connection_name=self.name)
            )
            return True
        self._mark_written()
        try:
            async with self.acquire() as connection:
                await connection.exec_driver_sql(sql)
        except sa_exc.DBAPIError:  # pragma: no cover - driver-specific
            return False
        return True

    async def stream(
        self,
        statement: ClauseElement | str,
        parameters: Mapping[str, Any] | None = None,
        *,
        chunk_size: int = 100,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield rows as the driver produces them, without buffering the set."""
        compiled = text(statement) if isinstance(statement, str) else statement
        async with self.acquire(write=False) as connection:
            result = await connection.stream(
                compiled, parameters, execution_options={"yield_per": chunk_size}
            )
            async for row in result.mappings():
                yield dict(row)

    # --- transactions -------------------------------------------------------

    def in_transaction(self) -> bool:
        """Whether this connection is inside a transaction right now."""
        return self.current() is not None

    def transaction_level(self) -> int:
        """How deep the open transactions are stacked."""
        frames = _manual.get()
        manual = len(frames.get(self.name, [])) if frames else 0
        return manual or (1 if self.in_transaction() else 0)

    def after_commit(self, callback: Callable[[], Any]) -> None:
        """Run `callback` once the outermost transaction commits.

        Outside a transaction there is nothing to wait for, so it runs now.
        A rollback throws the callback away with everything else — which is
        the point: nobody should hear about a row that never existed.
        """
        if not self.in_transaction():
            callback()
            return
        bag = _deferred.get()
        if bag is None:  # pragma: no cover - set whenever a transaction starts
            callback()
            return
        bag.setdefault(self.name, []).append(callback)

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
            deferred_bag = _deferred.get()
            deferred_token = None
            if deferred_bag is None:
                deferred_bag = {}
                deferred_token = _deferred.set(deferred_bag)
            transaction = await connection.begin()
            try:
                yield connection
            except BaseException:
                await transaction.rollback()
                deferred_bag.pop(self.name, None)
                raise
            else:
                await transaction.commit()
                self._run_deferred(deferred_bag)
            finally:
                _active.reset(token)
                if deferred_token is not None:
                    _deferred.reset(deferred_token)

    async def begin_transaction(self) -> None:
        """Open a transaction you will `commit` or `rollback` yourself.

        Each frame remembers whether it opened the connection: one begun
        inside a block transaction is a SAVEPOINT within it, and closing it
        must leave the block's connection where the block will find it.
        """
        frames = dict(_manual.get() or {})
        stack = list(frames.get(self.name, []))
        existing = self.current()
        if existing is not None:
            stack.append((await existing.begin_nested(), None))
        else:
            connection = await self._engine.connect()
            bag = dict(_active.get() or {})
            bag[self.name] = connection
            _active.set(bag)
            if _deferred.get() is None:
                _deferred.set({})
            stack.append((await connection.begin(), connection))
        frames[self.name] = stack
        _manual.set(frames)

    async def commit(self) -> None:
        """Commit the innermost hand-opened transaction."""
        transaction, connection = self._pop_manual("commit")
        await transaction.commit()
        if connection is not None:
            await self._close_manual(connection, run_deferred=True)

    async def rollback(self) -> None:
        """Roll back the innermost hand-opened transaction."""
        transaction, connection = self._pop_manual("rollback")
        await transaction.rollback()
        if connection is not None:
            await self._close_manual(connection, run_deferred=False)

    def _pop_manual(self, verb: str) -> tuple[Any, AsyncConnection | None]:
        frames = dict(_manual.get() or {})
        stack = list(frames.get(self.name, []))
        if not stack:
            raise RuntimeError(f"There is no transaction on {self.name!r} to {verb}.")
        frame = stack.pop()
        frames[self.name] = stack
        _manual.set(frames)
        return frame

    async def _close_manual(self, connection: AsyncConnection, *, run_deferred: bool) -> None:
        bag = dict(_active.get() or {})
        bag.pop(self.name, None)
        _active.set(bag)
        deferred_bag = _deferred.get() or {}
        if run_deferred:
            self._run_deferred(deferred_bag)
        else:
            deferred_bag.pop(self.name, None)
        await connection.close()

    def _run_deferred(self, bag: dict[str, list[Callable[[], Any]]]) -> None:
        """Run the callbacks this connection deferred, in the order given."""
        for callback in bag.pop(self.name, []):
            callback()

    async def disconnect(self) -> None:
        await self._engine.dispose()
        if self._read_engine is not self._engine:
            await self._read_engine.dispose()


class PretendResult:
    """What a pretended statement hands back — nothing, convincingly."""

    rowcount = 0
    lastrowid = None

    def mappings(self) -> PretendResult:
        return self

    def all(self) -> list[Any]:
        return []

    def scalar(self) -> Any:
        return None


@contextmanager
def pretending() -> Iterator[list[QueryExecuted]]:
    """Collect the queries a block would run, without running any of them."""
    recorded: list[QueryExecuted] = []
    token = _pretending.set(recorded)
    try:
        yield recorded
    finally:
        _pretending.reset(token)


def total_query_duration() -> float:
    """Milliseconds this context has spent querying."""
    return _elapsed.get()


def reset_total_query_duration() -> None:
    """Start the query-time budget over — a new request, say."""
    _elapsed.set(0.0)


#: Drivers whose connections hold collections, not tables.
DOCUMENT_DRIVERS = ("mongodb", "mongo", "memory")

#: The suffix that asks for a pooled connection's direct twin.
DIRECT_SUFFIX = "::direct"


class DatabaseManager:
    """Resolves named connections from `config/database.py`.

    A connection is either a SQL database or a document store, decided by its
    driver. `connection()` hands back the first kind and `store()` the second;
    asking for the wrong one says so rather than failing obscurely.
    """

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        config = dict(config or {})
        self.default: str = str(config.get("default", "sqlite"))
        self._definitions: dict[str, Any] = dict(config.get("connections", {}) or {})
        self._connections: dict[str, Connection] = {}
        self._stores: dict[str, Any] = {}
        self._listeners: list[Callable[[QueryExecuted], Any]] = []
        self._slow: list[tuple[float, Callable[[Connection, QueryExecuted], Any]]] = []

    def _definition(self, key: str) -> dict[str, Any]:
        base, direct = _split_direct(key)
        if base not in self._definitions:
            raise ConnectionError_(f"Database connection {base!r} is not configured.")
        definition = dict(self._definitions[base])
        if direct:
            return _merge(definition, definition.get("direct"))
        return definition

    def driver(self, name: str | None = None) -> str:
        """The driver behind a connection name."""
        return str(self._definition(name or self.default).get("driver", ""))

    def is_document(self, name: str | None = None) -> bool:
        """Whether this connection stores documents rather than rows."""
        return self.driver(name) in DOCUMENT_DRIVERS

    def direct_name(self, name: str | None = None) -> str:
        """The connection schema work should use — direct, when one is pooled.

        Transaction poolers cannot hold the session state migrations and
        schema inspection need, so Laravel routes that work to the `direct`
        block instead. A connection that is not pooled is its own direct twin.
        """
        key = name or self.default
        if key.endswith(DIRECT_SUFFIX):
            return key
        definition = self._definitions.get(key, {})
        if definition.get("pooled") and definition.get("direct"):
            return f"{key}{DIRECT_SUFFIX}"
        return key

    def connection(self, name: str | None = None) -> Connection:
        key = name or self.default
        if key not in self._connections:
            definition = self._definition(key)
            if str(definition.get("driver", "")) in DOCUMENT_DRIVERS:
                raise ConnectionError_(
                    f"Connection {key!r} is a document store "
                    f"({definition.get('driver')!r}) — reach it with store(), not connection()."
                )
            self._connections[key] = Connection(key, definition)
        return self._connections[key]

    def store(self, name: str | None = None) -> Any:
        """The document store behind a connection name."""
        from almasix.orm.documents.stores import MemoryStore, MongoStore

        key = name or self.default
        if key not in self._stores:
            definition = self._definition(key)
            driver = str(definition.get("driver", ""))
            if driver == "memory":
                self._stores[key] = MemoryStore(key, definition)
            elif driver in ("mongodb", "mongo"):
                self._stores[key] = MongoStore(key, definition)
            else:
                raise ConnectionError_(
                    f"Connection {key!r} is a {driver!r} database, not a document store."
                )
        return self._stores[key]

    def set_store(self, name: str, store: Any) -> None:
        """Bind a store instance directly — how tests hand in a fake client."""
        self._stores[name] = store

    def add_connection(self, name: str, config: Mapping[str, Any]) -> None:
        self._definitions[name] = dict(config)
        self._connections.pop(name, None)
        self._stores.pop(name, None)

    def connection_names(self) -> list[str]:
        return sorted(self._definitions)

    def document_connection_names(self) -> list[str]:
        return sorted(name for name in self._definitions if self.is_document(name))

    # --- listening ----------------------------------------------------------

    def listen(self, callback: Callable[[QueryExecuted], Any]) -> None:
        """Call `callback` with every statement this application runs."""
        self._listeners.append(callback)

    def when_querying_for_longer_than(
        self,
        milliseconds: float,
        callback: Callable[[Connection, QueryExecuted], Any],
    ) -> None:
        """Call `callback` once a context has spent this long querying.

        The budget is per context — a request, a job, a command — because
        that is the unit a slow page is measured in.
        """
        self._slow.append((float(milliseconds), callback))

    def notify(self, describe: Callable[[], QueryExecuted], connection: Connection) -> None:
        """Tell the listeners about a statement, building the event only if asked."""
        if not self._listeners and not self._slow:
            return
        event = describe()
        for listener in self._listeners:
            listener(event)
        total = _elapsed.get()
        for threshold, callback in self._slow:
            if total >= threshold:
                callback(connection, event)

    def flush_listeners(self) -> None:
        """Forget every listener — how a test leaves the next one alone."""
        self._listeners.clear()
        self._slow.clear()

    async def disconnect(self, name: str | None = None) -> None:
        if name is None:
            for connection in list(self._connections.values()):
                await connection.disconnect()
            self._connections.clear()
            for store in list(self._stores.values()):
                await store.disconnect()
            self._stores.clear()
            return
        connection = self._connections.pop(name, None)
        if connection is not None:
            await connection.disconnect()
        store = self._stores.pop(name, None)
        if store is not None:
            await store.disconnect()


def _split_direct(name: str) -> tuple[str, bool]:
    if name.endswith(DIRECT_SUFFIX):
        return name[: -len(DIRECT_SUFFIX)], True
    return name, False
