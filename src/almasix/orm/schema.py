"""Schema builder — Laravel `Schema::create` / `Schema::table` / `Blueprint`.

The blueprint itself lives in :mod:`almasix.orm.blueprint`; this module is the
façade that runs one against a connection, and the compiler that turns the
alter path into the ALTER statements each engine understands.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import sqlalchemy as sa

from almasix.orm.blueprint import (
    Blueprint,
    Column,
    ForeignKeyDefinition,
    SchemaError,
    _default_literal,
    guess_foreign_table,
)
from almasix.orm.dialects import drop_table_sql, quote_ident, rename_column_sql
from almasix.orm.facade import get_manager

#: Laravel keeps this private name; Almasix's tests reach for it too.
_guess_foreign_table = guess_foreign_table


def _schema_connection(connection: str | None = None) -> Any:
    """The connection schema work runs on.

    A pooled PostgreSQL connection cannot hold the session state DDL needs,
    so when one declares a `direct` twin, schema work goes there instead —
    the same routing Laravel applies to migrations and the `db:*` commands.
    """
    manager = get_manager()
    return manager.connection(manager.direct_name(connection))


class Schema:
    """Static schema façade."""

    @staticmethod
    async def create(table: str, callback: Any, connection: str | None = None) -> None:
        blueprint = Blueprint(table)
        callback(blueprint)
        metadata = sa.MetaData()
        engine = _schema_connection(connection).engine

        def reflect_and_create(sync_conn: Any) -> None:
            # Load existing tables so ForeignKey("users.id") can resolve during CREATE.
            metadata.reflect(bind=sync_conn)
            sa_table = blueprint.to_table(metadata, engine.dialect)
            metadata.create_all(sync_conn, tables=[sa_table])

        async with engine.begin() as conn:
            await _enable_foreign_keys(conn, engine.dialect.name)
            await conn.run_sync(reflect_and_create)

    @staticmethod
    async def create_if_not_exists(
        table: str, callback: Any, connection: str | None = None
    ) -> None:
        """Create the table only when it is not already there."""
        if await Schema.has_table(table, connection):
            return
        await Schema.create(table, callback, connection)

    @staticmethod
    async def table(table: str, callback: Any, connection: str | None = None) -> None:
        """Alter an existing table (Laravel ``Schema::table``)."""
        blueprint = Blueprint(table)
        callback(blueprint)
        engine = _schema_connection(connection).engine
        dialect_name = engine.dialect.name
        statements = compile_table_statements(blueprint, engine.dialect)
        if not statements:
            return
        async with engine.begin() as conn:
            await _enable_foreign_keys(conn, dialect_name)
            for statement in statements:
                await conn.execute(sa.text(statement))

    @staticmethod
    async def rename(from_table: str, to_table: str, connection: str | None = None) -> None:
        """Rename a table (Laravel ``Schema::rename``)."""
        engine = _schema_connection(connection).engine
        await _schema_connection(connection).execute(
            rename_table_sql(from_table, to_table, engine.dialect)
        )

    @staticmethod
    async def drop(table: str, connection: str | None = None) -> None:
        engine = _schema_connection(connection).engine
        await _schema_connection(connection).execute(
            drop_table_sql(table, engine.dialect, if_exists=False)
        )

    @staticmethod
    async def drop_if_exists(table: str, connection: str | None = None) -> None:
        engine = _schema_connection(connection).engine
        await _schema_connection(connection).execute(
            drop_table_sql(table, engine.dialect, if_exists=True)
        )

    @staticmethod
    async def drop_all_tables(connection: str | None = None) -> None:
        """Empty the schema, foreign keys and all.

        Constraints are switched off for the duration rather than the tables
        sorted, because a cycle between two tables has no safe order.
        """
        engine = _schema_connection(connection).engine
        tables = await Schema.table_names(connection)
        if not tables:
            return
        async with Schema.without_foreign_key_constraints(connection):
            for table in tables:
                await _schema_connection(connection).execute(
                    drop_table_sql(table, engine.dialect, if_exists=True)
                )

    @staticmethod
    async def has_table(table: str, connection: str | None = None) -> bool:
        engine = _schema_connection(connection).engine

        def inspect(sync_conn: Any) -> bool:
            return sa.inspect(sync_conn).has_table(table)

        async with engine.connect() as conn:
            return await conn.run_sync(inspect)

    @staticmethod
    async def has_column(table: str, column: str, connection: str | None = None) -> bool:
        engine = _schema_connection(connection).engine

        def inspect(sync_conn: Any) -> bool:
            return column in {col["name"] for col in sa.inspect(sync_conn).get_columns(table)}

        async with engine.connect() as conn:
            return await conn.run_sync(inspect)

    @staticmethod
    async def has_columns(
        table: str, columns: list[str], connection: str | None = None
    ) -> bool:
        present = {column["name"] for column in await Schema.columns(table, connection)}
        return set(columns).issubset(present)

    @staticmethod
    async def has_index(
        table: str,
        index: str | list[str],
        connection: str | None = None,
        *,
        unique: bool | None = None,
    ) -> bool:
        """Whether an index exists, named or described by its columns."""
        indexes = await Schema.get_indexes(table, connection)
        for found in indexes:
            if unique is not None and bool(found["unique"]) is not unique:
                continue
            if isinstance(index, str):
                if found["name"] == index:
                    return True
            elif list(found["columns"]) == list(index):
                return True
        return False

    @staticmethod
    async def columns(table: str, connection: str | None = None) -> list[dict[str, Any]]:
        """Reflected column metadata (Laravel ``Schema::getColumns``).

        A table that does not exist has no columns, rather than raising: the
        question "what does this table hold?" is answerable with "nothing yet".
        """

        def read(sync_conn: Any) -> list[dict[str, Any]]:
            inspector = sa.inspect(sync_conn)
            if not inspector.has_table(table):
                return []
            return [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": bool(column["nullable"]),
                    "default": column.get("default"),
                }
                for column in inspector.get_columns(table)
            ]

        engine = _schema_connection(connection).engine
        async with engine.connect() as conn:
            return await conn.run_sync(read)

    @staticmethod
    async def column_type(table: str, column: str, connection: str | None = None) -> str:
        """The type of one column (Laravel ``Schema::getColumnType``)."""
        for found in await Schema.columns(table, connection):
            if found["name"] == column:
                return str(found["type"])
        raise SchemaError(f"Table {table} has no column {column}.")

    @staticmethod
    async def get_indexes(table: str, connection: str | None = None) -> list[dict[str, Any]]:
        """Every index on a table, primary key included."""

        def read(sync_conn: Any) -> list[dict[str, Any]]:
            inspector = sa.inspect(sync_conn)
            if not inspector.has_table(table):
                return []
            found = [
                {
                    "name": index["name"],
                    "columns": list(index["column_names"]),
                    "unique": bool(index["unique"]),
                    "primary": False,
                }
                for index in inspector.get_indexes(table)
            ]
            primary = inspector.get_pk_constraint(table)
            if primary.get("constrained_columns"):
                found.append(
                    {
                        "name": primary.get("name") or f"{table}_primary",
                        "columns": list(primary["constrained_columns"]),
                        "unique": True,
                        "primary": True,
                    }
                )
            return found

        engine = _schema_connection(connection).engine
        async with engine.connect() as conn:
            return await conn.run_sync(read)

    @staticmethod
    async def get_foreign_keys(table: str, connection: str | None = None) -> list[dict[str, Any]]:
        """Every foreign key on a table, with the actions it carries."""

        def read(sync_conn: Any) -> list[dict[str, Any]]:
            inspector = sa.inspect(sync_conn)
            if not inspector.has_table(table):
                return []
            return [
                {
                    "name": key.get("name"),
                    "columns": list(key["constrained_columns"]),
                    "foreign_table": key["referred_table"],
                    "foreign_columns": list(key["referred_columns"]),
                    "on_delete": (key.get("options") or {}).get("ondelete"),
                    "on_update": (key.get("options") or {}).get("onupdate"),
                }
                for key in inspector.get_foreign_keys(table)
            ]

        engine = _schema_connection(connection).engine
        async with engine.connect() as conn:
            return await conn.run_sync(read)

    @staticmethod
    async def get_views(connection: str | None = None) -> list[dict[str, Any]]:
        def read(sync_conn: Any) -> list[dict[str, Any]]:
            inspector = sa.inspect(sync_conn)
            return [
                {"name": name, "definition": inspector.get_view_definition(name) or ""}
                for name in inspector.get_view_names()
            ]

        engine = _schema_connection(connection).engine
        async with engine.connect() as conn:
            return await conn.run_sync(read)

    @staticmethod
    async def table_names(connection: str | None = None) -> list[str]:
        engine = _schema_connection(connection).engine

        def names(sync_conn: Any) -> list[str]:
            return list(sa.inspect(sync_conn).get_table_names())

        async with engine.connect() as conn:
            return await conn.run_sync(names)

    @staticmethod
    async def when_table_has_column(
        table: str, column: str, callback: Any, connection: str | None = None
    ) -> None:
        """Run the blueprint only if the column is there — Laravel's conditional."""
        if await Schema.has_column(table, column, connection):
            await Schema.table(table, callback, connection)

    @staticmethod
    async def when_table_doesnt_have_column(
        table: str, column: str, callback: Any, connection: str | None = None
    ) -> None:
        if not await Schema.has_column(table, column, connection):
            await Schema.table(table, callback, connection)

    @staticmethod
    async def disable_foreign_key_constraints(connection: str | None = None) -> None:
        statement = _foreign_key_switch(_schema_connection(connection).engine.dialect, False)
        if statement:
            await _schema_connection(connection).execute(statement)

    @staticmethod
    async def enable_foreign_key_constraints(connection: str | None = None) -> None:
        statement = _foreign_key_switch(_schema_connection(connection).engine.dialect, True)
        if statement:
            await _schema_connection(connection).execute(statement)

    @staticmethod
    @asynccontextmanager
    async def without_foreign_key_constraints(connection: str | None = None) -> Any:
        """Run a block with foreign keys switched off, then switch them back on."""
        await Schema.disable_foreign_key_constraints(connection)
        try:
            yield
        finally:
            await Schema.enable_foreign_key_constraints(connection)


def _foreign_key_switch(dialect: Any, enabled: bool) -> str | None:
    """The statement that turns constraint checking off and on again."""
    name = dialect.name
    if name == "sqlite":
        return f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}"
    if name == "mysql":
        return f"SET FOREIGN_KEY_CHECKS={1 if enabled else 0}"
    if name == "postgresql":
        return f"SET session_replication_role = {'origin' if enabled else 'replica'}"
    return None


def rename_table_sql(from_table: str, to_table: str, dialect: Any) -> str:
    """``ALTER TABLE … RENAME``, in each engine's spelling."""
    old = quote_ident(dialect, from_table)
    if dialect.name == "mssql":
        return f"EXEC sp_rename '{from_table}', '{to_table}'"
    new = quote_ident(dialect, to_table)
    if dialect.name == "mysql":
        return f"RENAME TABLE {old} TO {new}"
    return f"ALTER TABLE {old} RENAME TO {new}"


async def _enable_foreign_keys(conn: Any, dialect_name: str) -> None:
    if dialect_name == "sqlite":  # pragma: no branch
        await conn.execute(sa.text("PRAGMA foreign_keys=ON"))


def compile_table_statements(blueprint: Blueprint, dialect: Any) -> list[str]:
    """Compile ``Schema.table`` DDL (also used by tests)."""
    table = blueprint.table
    dialect_name = dialect.name
    qt = quote_ident(dialect, table)
    statements: list[str] = []

    for old, new in blueprint._renames:
        statements.append(rename_column_sql(table, old, new, dialect))

    for old, new in blueprint._rename_indexes:
        statements.append(_rename_index_sql(table, old, new, dialect))

    statements.extend(_drop_constraint_statements(blueprint, dialect, qt))

    inline_fk_columns = {
        column.name
        for column in blueprint.columns
        if column.options.get("references") and not column.changing
    }

    for column in blueprint.columns:
        if column.changing:
            statements.extend(_change_statements(column, dialect, qt))
            continue
        statements.append(_add_column_sql(column, dialect, qt))

    for name in blueprint._drop_columns:
        statements.append(f"ALTER TABLE {qt} DROP COLUMN {quote_ident(dialect, name)}")

    if blueprint._primary is not None:
        columns, name = blueprint._primary
        cols = ", ".join(quote_ident(dialect, column) for column in columns)
        constraint = f"CONSTRAINT {quote_ident(dialect, name)} " if name else ""
        statements.append(f"ALTER TABLE {qt} ADD {constraint}PRIMARY KEY ({cols})")

    for fk in blueprint._foreign_keys:
        if not fk.ref_table:
            raise SchemaError(
                f"Foreign key on {fk.columns} is missing references()/on() or constrained()"
            )
        if inline_fk_columns.issuperset(fk.columns):
            continue
        if dialect_name == "sqlite":
            raise SchemaError(
                "SQLite cannot add a foreign key to an existing column via ALTER TABLE. "
                "Use foreign_id(...).constrained() when adding the column, "
                "or MySQL / MariaDB / PostgreSQL / SQL Server / Oracle."
            )
        cols = ", ".join(quote_ident(dialect, column) for column in fk.columns)
        clause = (
            f"ALTER TABLE {qt} ADD CONSTRAINT {quote_ident(dialect, fk.constraint_name())} "
            f"FOREIGN KEY ({cols}) REFERENCES {quote_ident(dialect, fk.ref_table)} "
            f"({quote_ident(dialect, fk.ref_column)})"
        )
        if fk.on_delete:  # pragma: no branch
            clause += f" ON DELETE {fk.on_delete}"
        if fk.on_update:
            clause += f" ON UPDATE {fk.on_update}"
        statements.append(clause)

    for index_name, columns, unique in blueprint._indexes:
        cols = ", ".join(quote_ident(dialect, column) for column in columns)
        unique_sql = "UNIQUE " if unique else ""
        statements.append(
            f"CREATE {unique_sql}INDEX {quote_ident(dialect, index_name)} ON {qt} ({cols})"
        )

    for column in blueprint.columns:
        if column.changing:
            continue
        if column.options.get("unique") and not column.options.get("primary_key"):
            # UNIQUE may already be inline on ADD COLUMN for SQLite/Postgres.
            if dialect_name not in {"sqlite", "postgresql"}:
                name = f"uq_{table}_{column.name}"
                statements.append(
                    f"CREATE UNIQUE INDEX {quote_ident(dialect, name)} "
                    f"ON {qt} ({quote_ident(dialect, column.name)})"
                )
        if column.options.get("index"):
            name = f"ix_{table}_{column.name}"
            statements.append(
                f"CREATE INDEX {quote_ident(dialect, name)} "
                f"ON {qt} ({quote_ident(dialect, column.name)})"
            )

    return statements


def _add_column_sql(column: Column, dialect: Any, qt: str) -> str:
    """One ``ALTER TABLE … ADD COLUMN``, foreign key and placement included."""
    # Compile the bare column, then append REFERENCES manually — SQLAlchemy's
    # CreateColumn omits FK clauses on ALTER TABLE ADD COLUMN for SQLite.
    col_sql = _column_definition(column, dialect)
    references = column.options.get("references")
    if references:
        ref_table, _, ref_column = references.partition(".")
        col_sql += (
            f" REFERENCES {quote_ident(dialect, ref_table)} "
            f"({quote_ident(dialect, ref_column or 'id')})"
        )
        if column.options.get("on_delete"):  # pragma: no branch
            col_sql += f" ON DELETE {column.options['on_delete']}"
        if column.options.get("on_update"):
            col_sql += f" ON UPDATE {column.options['on_update']}"
    statement = f"ALTER TABLE {qt} ADD COLUMN {col_sql}"
    if dialect.name == "mysql":
        if column.options.get("first"):
            statement += " FIRST"
        elif column.options.get("after"):
            statement += f" AFTER {quote_ident(dialect, column.options['after'])}"
        elif column.options.get("before"):
            statement += f" BEFORE {quote_ident(dialect, column.options['before'])}"
    return statement


def _column_definition(column: Column, dialect: Any) -> str:
    """``name TYPE NOT NULL DEFAULT …`` — the part every engine agrees on."""
    options = {key: value for key, value in column.options.items() if key not in _ALTER_IGNORED}
    bare = Column(column.name, column.type, **options)
    sa_col = bare.to_sqlalchemy(dialect)
    if dialect.name in {"mssql", "oracle"}:  # CreateColumn needs a Table-bound column.
        sa.Table("__almasix_alter__", sa.MetaData()).append_column(sa_col)
    definition = str(sa.schema.CreateColumn(sa_col).compile(dialect=dialect))
    if dialect.name == "mysql":
        if column.options.get("charset"):
            definition += f" CHARACTER SET {column.options['charset']}"
        if column.options.get("collation"):
            definition += f" COLLATE {column.options['collation']}"
        if column.options.get("invisible"):
            definition += " INVISIBLE"
        if column.options.get("comment"):
            comment = str(column.options["comment"]).replace("'", "''")
            definition += f" COMMENT '{comment}'"
    return definition


#: Modifiers the ALTER path writes itself rather than handing to SQLAlchemy.
_ALTER_IGNORED = frozenset({"references", "on_delete", "on_update", "index", "comment"})


def _change_statements(column: Column, dialect: Any, qt: str) -> list[str]:
    """Restate an existing column — Laravel's ``change()``.

    Every attribute is re-stated, so a modifier left out of the call is
    dropped rather than kept; that is Laravel's rule, and the engines that
    take a whole column definition enforce it for us.
    """
    name = dialect.name
    quoted = quote_ident(dialect, column.name)
    if name == "sqlite":
        raise SchemaError(
            "SQLite cannot change a column in place. Add the new column, copy the "
            "values across, and drop the old one — or run the migration on "
            "MySQL / MariaDB / PostgreSQL / SQL Server."
        )
    if name == "mysql":
        return [f"ALTER TABLE {qt} MODIFY {_column_definition(column, dialect)}"]
    if name == "oracle":
        return [f"ALTER TABLE {qt} MODIFY ({_column_definition(column, dialect)})"]

    type_sql = column.sa_type(dialect).compile(dialect=dialect)
    if name == "mssql":
        nullable = "NULL" if column.options.get("nullable", True) else "NOT NULL"
        return [f"ALTER TABLE {qt} ALTER COLUMN {quoted} {type_sql} {nullable}"]

    # PostgreSQL says one thing at a time.
    statements = [
        (f"ALTER TABLE {qt} ALTER COLUMN {quoted} TYPE {type_sql} USING {quoted}::{type_sql}")
    ]
    if column.options.get("nullable", True):
        statements.append(f"ALTER TABLE {qt} ALTER COLUMN {quoted} DROP NOT NULL")
    else:
        statements.append(f"ALTER TABLE {qt} ALTER COLUMN {quoted} SET NOT NULL")
    default = column.options.get("default")
    if column.options.get("use_current"):
        statements.append(
            f"ALTER TABLE {qt} ALTER COLUMN {quoted} SET DEFAULT CURRENT_TIMESTAMP"
        )
    elif default is not None:
        literal = _default_literal(default, dialect)
        statements.append(f"ALTER TABLE {qt} ALTER COLUMN {quoted} SET DEFAULT {literal}")
    else:
        statements.append(f"ALTER TABLE {qt} ALTER COLUMN {quoted} DROP DEFAULT")
    return statements


def _drop_constraint_statements(blueprint: Blueprint, dialect: Any, qt: str) -> list[str]:
    """Index, foreign-key, and primary-key drops, in each engine's spelling."""
    name = dialect.name
    statements: list[str] = []

    for index_name, _kind in blueprint._drop_indexes:
        quoted = quote_ident(dialect, index_name)
        if name in {"mysql", "mssql"}:
            statements.append(f"ALTER TABLE {qt} DROP INDEX {quoted}")
        else:
            statements.append(f"DROP INDEX {quoted}")

    for key_name in blueprint._drop_foreign_keys:
        quoted = quote_ident(dialect, key_name)
        if name == "sqlite":
            raise SchemaError(
                "SQLite cannot drop a foreign key. Rebuild the table instead, "
                "or run the migration on another engine."
            )
        keyword = "FOREIGN KEY" if name == "mysql" else "CONSTRAINT"
        statements.append(f"ALTER TABLE {qt} DROP {keyword} {quoted}")

    if blueprint._drop_primary:
        if name == "mysql":
            statements.append(f"ALTER TABLE {qt} DROP PRIMARY KEY")
        elif name == "sqlite":
            raise SchemaError(
                "SQLite cannot drop a primary key. Rebuild the table instead."
            )
        else:
            constraint = quote_ident(dialect, f"{blueprint.table}_pkey")
            statements.append(f"ALTER TABLE {qt} DROP CONSTRAINT {constraint}")

    return statements


def _rename_index_sql(table: str, old: str, new: str, dialect: Any) -> str:
    name = dialect.name
    if name == "mysql":
        return (
            f"ALTER TABLE {quote_ident(dialect, table)} RENAME INDEX "
            f"{quote_ident(dialect, old)} TO {quote_ident(dialect, new)}"
        )
    if name == "mssql":
        return f"EXEC sp_rename '{table}.{old}', '{new}', 'INDEX'"
    if name == "sqlite":
        raise SchemaError(
            "SQLite cannot rename an index. Drop it and create it under the new name."
        )
    return f"ALTER INDEX {quote_ident(dialect, old)} RENAME TO {quote_ident(dialect, new)}"


__all__ = [
    "Blueprint",
    "Column",
    "ForeignKeyDefinition",
    "Schema",
    "SchemaError",
    "compile_table_statements",
    "rename_table_sql",
]
