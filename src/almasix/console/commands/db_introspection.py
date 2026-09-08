"""The read-only database commands — ``db:show``, ``db:table``, ``db:monitor``.

All three report what the active dialect can actually answer. SQLAlchemy's
inspector covers tables, views, columns, indexes, and foreign keys on every
driver Almasix supports, so those rows are always real. Custom types and the
server's session count are not portable: they degrade to a stated reason
instead of a number nobody should trust.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from almasix.console.command import Command
from almasix.console.display import to_json
from almasix.orm.connection import Connection, ConnectionError_
from almasix.orm.dialects import quote_ident
from almasix.orm.facade import get_manager

T = TypeVar("T")

#: How each server reports the sessions it currently holds open.
_SESSION_COUNT_SQL: dict[str, str] = {
    "mysql": "SHOW STATUS LIKE 'Threads_connected'",
    "mariadb": "SHOW STATUS LIKE 'Threads_connected'",
    "postgresql": "SELECT count(*) FROM pg_stat_activity",
    "mssql": "SELECT count(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1",
}

#: Why a driver has no session count to read, keyed by dialect.
_NO_SESSION_COUNT: dict[str, str] = {
    "sqlite": "SQLite is a file, not a server",
    "oracle": "Oracle keeps this in v$session, which needs privileges Almasix cannot assume",
}

#: The rows ``db:show`` prints above the table list, in order.
_OVERVIEW_LABELS: tuple[tuple[str, str], ...] = (
    ("name", "Name"),
    ("driver", "Driver"),
    ("host", "Host"),
    ("port", "Port"),
    ("database", "Database"),
    ("username", "Username"),
)


class DatabaseIntrospectionCommand(Command):
    """Shared body: naming a connection, and reading its schema off the loop."""

    def selected_connection(self) -> Connection | int:
        """The connection ``--database`` names, or the exit code refusing it."""
        given = self.option("database")
        if given is True:
            self.error(
                "Invalid value for '--database': provide a connection name, e.g. --database=sqlite."
            )
            return self.INVALID
        return self.named_connection(str(given or "").strip() or None)

    def named_connection(self, name: str | None) -> Connection | int:
        """One configured connection, or the exit code explaining its absence.

        Reading a schema goes to the direct connection when the named one is
        pooled, because a transaction pooler cannot answer these questions.
        """
        manager = get_manager()
        try:
            return manager.connection(manager.direct_name(name))
        except ConnectionError_ as exc:
            self.error(str(exc))
            return self.FAILURE

    async def read(
        self,
        handle: AsyncConnection,
        reader: Callable[[sa.Inspector], T],
    ) -> T:
        """Run one synchronous inspection over an open async connection."""
        return await handle.run_sync(lambda sync: reader(sa.inspect(sync)))

    async def table_names(self, connection: Connection) -> list[str]:
        async with connection.engine.connect() as handle:
            return await self.read(handle, _table_names)


class DbShowCommand(DatabaseIntrospectionCommand):
    """Laravel's ``db:show`` — the connection, and the tables it holds.

    Row counts sit behind ``--counts`` for the reason Laravel puts them there:
    each one is a ``count(*)``, a full scan of the table. The estimates MySQL
    and PostgreSQL keep in their catalogs are not read instead, because SQLite
    has no equivalent and a column that means "exact" on one driver and
    "roughly" on another is worse than one flag.

    Laravel's size columns are absent. Table size has a different answer in
    every dialect, and SQLite only has one when the interpreter was built with
    the ``dbstat`` virtual table, so there is no row that means the same thing
    on all five drivers.
    """

    signature = (
        "db:show {--database= : Connection to describe (default: the configured default)} "
        "{--counts : Count the rows in every table — a full scan each} "
        "{--views : Also list the connection's views} "
        "{--types : Also list custom types (PostgreSQL only)} "
        "{--json : Output as JSON}"
    )
    description = "Show information about a database connection and its tables"

    def handle(self) -> int:
        connection = self.selected_connection()
        if isinstance(connection, int):
            return connection

        try:
            overview = asyncio.run(self.overview(connection))
        except Exception as exc:  # noqa: BLE001 - the database is the user's to fix
            self.error(str(exc))
            return self.FAILURE

        if self.option("json"):
            self.line(to_json(overview))
            return self.SUCCESS
        self.render(overview)
        return self.SUCCESS

    async def overview(self, connection: Connection) -> dict[str, Any]:
        """Everything the connection can say about itself, in one round trip."""
        url = connection.engine.url
        overview: dict[str, Any] = {"name": connection.name, "driver": connection.dialect}
        for key, value in (
            ("host", url.host),
            ("port", url.port),
            ("database", url.database),
            ("username", url.username),
        ):
            if value is not None:
                overview[key] = value
        overview["connections"] = get_manager().connection_names()

        notes: list[str] = []
        async with connection.engine.connect() as handle:
            names = await self.read(handle, _table_names)
            overview["tables"] = await self.tables(handle, connection, names)
            if self.option("views"):
                overview["views"] = await self.read(handle, _view_names)
            if self.option("types"):
                custom = await self.read(handle, _custom_types)
                if custom is None:
                    notes.append(
                        f"--types cannot be honoured on {connection.dialect}: only PostgreSQL "
                        "reports custom types. No type was listed."
                    )
                else:
                    overview["types"] = custom
        if notes:
            overview["notes"] = notes
        return overview

    async def tables(
        self,
        handle: AsyncConnection,
        connection: Connection,
        names: list[str],
    ) -> list[dict[str, Any]]:
        """One entry per table, carrying a row count only when asked for one."""
        if not self.option("counts"):
            return [{"table": name} for name in names]
        dialect = connection.engine.dialect
        entries: list[dict[str, Any]] = []
        for name in names:
            result = await handle.execute(
                sa.text(f"SELECT count(*) FROM {quote_ident(dialect, name)}")
            )
            entries.append({"table": name, "rows": int(result.scalar() or 0)})
        return entries

    def render(self, overview: dict[str, Any]) -> None:
        rows = [(label, str(overview[key])) for key, label in _OVERVIEW_LABELS if key in overview]
        rows.append(("Connections", ", ".join(overview["connections"])))
        rows.append(("Tables", str(len(overview["tables"]))))
        self.comment("Connection")
        _labelled(self.line, rows)

        self.new_line()
        self.comment("Tables")
        if not overview["tables"]:
            self.line("  (no tables)")
        elif self.option("counts"):
            self.table(
                ("Table", "Rows"),
                [(entry["table"], entry["rows"]) for entry in overview["tables"]],
            )
        else:
            self.table(("Table",), [(entry["table"],) for entry in overview["tables"]])

        for key, title in (("views", "Views"), ("types", "Types")):
            if key not in overview:
                continue
            self.new_line()
            self.comment(title)
            for name in overview[key] or ["(none)"]:
                self.line(f"  {name}")

        for note in overview.get("notes", ()):
            self.warn(note)


class DbTableCommand(DatabaseIntrospectionCommand):
    """Laravel's ``db:table`` — one table's columns, indexes, and foreign keys.

    Named without a table, it asks which one, as Laravel does. A
    non-interactive terminal takes the first table rather than hanging, which
    is how :meth:`Command.choice` answers everywhere in Smith.
    """

    signature = (
        "db:table {table? : The table to inspect (asks when omitted)} "
        "{--database= : Connection holding the table (default: the configured default)} "
        "{--json : Output as JSON}"
    )
    description = "Show information about the given database table"

    def handle(self) -> int:
        connection = self.selected_connection()
        if isinstance(connection, int):
            return connection

        try:
            names = asyncio.run(self.table_names(connection))
        except Exception as exc:  # noqa: BLE001 - the database is the user's to fix
            self.error(str(exc))
            return self.FAILURE

        if not names:
            self.error(f"The [{connection.name}] database has no tables to inspect.")
            return self.FAILURE

        name = str(self.argument("table") or "").strip()
        if not name:
            name = str(self.choice("Which table would you like to inspect?", list(names)))
        if name not in names:
            self.error(f"Table [{name}] doesn't exist. Available tables: {', '.join(names)}.")
            return self.FAILURE

        detail = asyncio.run(self.detail(connection, name))
        if self.option("json"):
            self.line(to_json(detail))
            return self.SUCCESS
        self.render(detail)
        return self.SUCCESS

    async def detail(self, connection: Connection, name: str) -> dict[str, Any]:
        """The table's columns, keys, and indexes, in one round trip."""
        async with connection.engine.connect() as handle:

            async def about(reader: Callable[[sa.Inspector, str], Any]) -> Any:
                return await self.read(handle, lambda inspector: reader(inspector, name))

            return {
                "table": name,
                "connection": connection.name,
                "columns": await about(_columns),
                "primary_key": await about(_primary_key),
                "indexes": await about(_indexes),
                "foreign_keys": await about(_foreign_keys),
            }

    def render(self, detail: dict[str, Any]) -> None:
        rows = [
            ("Table", detail["table"]),
            ("Connection", detail["connection"]),
            ("Columns", str(len(detail["columns"]))),
        ]
        if detail["primary_key"]:
            rows.append(("Primary Key", ", ".join(detail["primary_key"])))
        self.comment("Table")
        _labelled(self.line, rows)

        self.new_line()
        self.comment("Columns")
        self.table(
            ("Column", "Type", "Nullable", "Default"),
            [
                (
                    column["column"],
                    column["type"],
                    "yes" if column["nullable"] else "no",
                    "" if column["default"] is None else column["default"],
                )
                for column in detail["columns"]
            ],
        )

        self.new_line()
        self.comment("Indexes")
        if not detail["indexes"]:
            self.line("  (no indexes)")
        else:
            self.table(
                ("Index", "Columns", "Unique"),
                [
                    (
                        index["index"],
                        ", ".join(index["columns"]),
                        "yes" if index["unique"] else "no",
                    )
                    for index in detail["indexes"]
                ],
            )

        self.new_line()
        self.comment("Foreign Keys")
        if not detail["foreign_keys"]:
            self.line("  (no foreign keys)")
        else:
            self.table(
                ("Columns", "References", "On Delete", "On Update"),
                [
                    (
                        ", ".join(key["columns"]),
                        key["references"],
                        key["on_delete"] or "",
                        key["on_update"] or "",
                    )
                    for key in detail["foreign_keys"]
                ],
            )


class DbMonitorCommand(DatabaseIntrospectionCommand):
    """Laravel's ``db:monitor`` — how many sessions a database has open.

    Only a server can answer this, and only out of its own catalog: MySQL and
    MariaDB through ``SHOW STATUS LIKE 'Threads_connected'``, PostgreSQL
    through ``pg_stat_activity``, SQL Server through ``sys.dm_exec_sessions``.
    SQLite has no server at all, and Oracle keeps the answer behind privileges
    a framework cannot assume it has, so for those two this reports the pool
    this process holds and says plainly that no server count exists — where
    Laravel raises, which would make the command useless on SQLite.

    A breach exits ``FAILURE`` rather than dispatching Laravel's
    ``DatabaseBusy`` event: Almasix has no such event to listen for, and the
    exit code is what a cron entry or health check can already read.
    """

    signature = (
        "db:monitor {--databases= : Comma-separated connections to check "
        "(default: the configured default)} "
        "{--max= : Fail when a connection reports more sessions than this}"
    )
    description = "Monitor the number of connections on the specified database"

    def handle(self) -> int:
        try:
            maximum = _threshold(self.option("max"))
            names = _database_names(self.option("databases"))
        except ValueError as exc:
            self.error(str(exc))
            return self.INVALID

        rows: list[tuple[str, str]] = []
        notes: list[str] = []
        breached: list[str] = []
        for name in names:
            connection = self.named_connection(name)
            if isinstance(connection, int):
                return connection
            try:
                sessions = self.sessions(connection)
            except Exception as exc:  # noqa: BLE001 - the database is the user's to fix
                self.error(f"[{connection.name}] could not be asked: {exc}")
                return self.FAILURE
            if sessions is None:
                rows.append((connection.name, "-"))
                notes.append(_pool_note(connection))
                continue
            rows.append((connection.name, str(sessions)))
            if maximum is not None and sessions > maximum:
                breached.append(
                    f"[{connection.name}] has {sessions} open session(s), "
                    f"above the maximum of {maximum}."
                )

        self.table(("Database", "Sessions"), rows)
        for note in notes:
            self.warn(note)
        for breach in breached:
            self.error(breach)
        return self.FAILURE if breached else self.SUCCESS

    def sessions(self, connection: Connection) -> int | None:
        """The server's open session count, or ``None`` when it keeps none."""
        query = _SESSION_COUNT_SQL.get(connection.dialect)
        if query is None:
            return None
        row = asyncio.run(connection.select_one(query))
        return _session_count(row) if row else 0


def _table_names(inspector: sa.Inspector) -> list[str]:
    return list(inspector.get_table_names())


def _view_names(inspector: sa.Inspector) -> list[str]:
    return list(inspector.get_view_names())


def _custom_types(inspector: sa.Inspector) -> list[str] | None:
    """Custom type names, or ``None`` where the inspector has no notion of one.

    ``get_enums`` belongs to PostgreSQL's inspector alone.
    """
    reader = getattr(inspector, "get_enums", None)
    if reader is None:
        return None
    return [str(enum["name"]) for enum in reader()]


def _columns(inspector: sa.Inspector, table: str) -> list[dict[str, Any]]:
    return [
        {
            "column": str(column["name"]),
            "type": str(column["type"]),
            "nullable": bool(column["nullable"]),
            "default": None if column.get("default") is None else str(column["default"]),
        }
        for column in inspector.get_columns(table)
    ]


def _primary_key(inspector: sa.Inspector, table: str) -> list[str]:
    constraint = inspector.get_pk_constraint(table)
    return [str(column) for column in constraint.get("constrained_columns") or []]


def _indexes(inspector: sa.Inspector, table: str) -> list[dict[str, Any]]:
    return [
        {
            "index": str(index["name"]),
            "columns": [str(column) for column in index["column_names"]],
            "unique": bool(index["unique"]),
        }
        for index in inspector.get_indexes(table)
    ]


def _foreign_keys(inspector: sa.Inspector, table: str) -> list[dict[str, Any]]:
    keys: list[dict[str, Any]] = []
    for key in inspector.get_foreign_keys(table):
        options = key.get("options") or {}
        referred = ", ".join(str(column) for column in key["referred_columns"])
        keys.append(
            {
                "columns": [str(column) for column in key["constrained_columns"]],
                "references": f"{key['referred_table']}({referred})",
                "on_delete": options.get("ondelete"),
                "on_update": options.get("onupdate"),
            }
        )
    return keys


def _labelled(write: Callable[[str], None], rows: list[tuple[str, str]]) -> None:
    """Print label/value pairs in the aligned two-column shape ``about`` uses."""
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        write(f"  {label:<{width}}  {value}")


def _threshold(given: Any) -> int | None:
    """``--max`` as a positive count, or ``None`` when it was not given."""
    if given is True:
        raise ValueError("Invalid value for '--max': provide a number, e.g. --max=100.")
    text = str(given or "").strip()
    if not text:
        return None
    try:
        maximum = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid value for '--max': {text!r} is not a number.") from exc
    if maximum < 1:
        raise ValueError(f"Invalid value for '--max': {maximum} is not a session count.")
    return maximum


def _database_names(given: Any) -> list[str | None]:
    """``--databases`` split on commas; ``[None]`` means the default connection."""
    if given is True:
        raise ValueError(
            "Invalid value for '--databases': provide connection names, "
            "e.g. --databases=mysql,pgsql."
        )
    names: list[str | None] = [part.strip() for part in str(given or "").split(",") if part.strip()]
    return names or [None]


def _session_count(row: Mapping[str, Any]) -> int:
    """The number in a session-count row, whatever the server named its column.

    MySQL answers ``SHOW STATUS`` with a ``Variable_name``/``Value`` pair; the
    others answer with a single aggregate column.
    """
    return int(list(row.values())[-1])


def _pool_note(connection: Connection) -> str:
    """Why this driver has no session count, and what Almasix can see instead."""
    reason = _NO_SESSION_COUNT.get(
        connection.dialect, f"Almasix knows no session count for {connection.dialect}"
    )
    return (
        f"[{connection.name}] reports no open sessions: {reason}. "
        f"This process holds {connection.engine.pool.status()}."
    )
