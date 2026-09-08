"""Schema builder — Laravel `Schema::create` / `Schema::table` / `Blueprint`."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from almasix.orm.dialects import drop_table_sql, quote_ident, rename_column_sql
from almasix.orm.facade import get_manager
from almasix.orm.inflector import pluralize


class SchemaError(RuntimeError):
    """Raised when a schema operation is unsupported on the active dialect."""


class ForeignKeyDefinition:
    """Fluent foreign-key builder (Laravel ``foreign`` / ``constrained`` chain)."""

    def __init__(
        self,
        blueprint: Blueprint,
        columns: list[str],
        *,
        column: Column | None = None,
        ref_table: str | None = None,
        ref_column: str = "id",
        name: str | None = None,
    ) -> None:
        self._blueprint = blueprint
        self.columns = columns
        self._column = column
        self.ref_table = ref_table
        self.ref_column = ref_column
        self.name = name
        self.on_delete: str | None = None
        self.on_update: str | None = None
        blueprint._foreign_keys.append(self)

    def references(self, column: str) -> ForeignKeyDefinition:
        self.ref_column = column
        self._sync_column()
        return self

    def on(self, table: str) -> ForeignKeyDefinition:
        self.ref_table = table
        self._sync_column()
        return self

    def cascade_on_delete(self) -> ForeignKeyDefinition:
        return self.on_delete_action("CASCADE")

    def restrict_on_delete(self) -> ForeignKeyDefinition:
        return self.on_delete_action("RESTRICT")

    def null_on_delete(self) -> ForeignKeyDefinition:
        return self.on_delete_action("SET NULL")

    def no_action_on_delete(self) -> ForeignKeyDefinition:
        return self.on_delete_action("NO ACTION")

    def cascade_on_update(self) -> ForeignKeyDefinition:
        return self.on_update_action("CASCADE")

    def restrict_on_update(self) -> ForeignKeyDefinition:
        return self.on_update_action("RESTRICT")

    def null_on_update(self) -> ForeignKeyDefinition:
        return self.on_update_action("SET NULL")

    def no_action_on_update(self) -> ForeignKeyDefinition:
        return self.on_update_action("NO ACTION")

    def on_delete_action(self, action: str) -> ForeignKeyDefinition:
        self.on_delete = action
        self._sync_column()
        return self

    def on_update_action(self, action: str) -> ForeignKeyDefinition:
        self.on_update = action
        self._sync_column()
        return self

    def _sync_column(self) -> None:
        if self._column is None or not self.ref_table:
            return
        self._column.options["references"] = f"{self.ref_table}.{self.ref_column}"
        if self.on_delete:
            self._column.options["on_delete"] = self.on_delete
        if self.on_update:
            self._column.options["on_update"] = self.on_update

    def constraint_name(self) -> str:
        if self.name:
            return self.name
        return f"{self._blueprint.table}_{'_'.join(self.columns)}_foreign"


class Column:
    """One column definition inside a `Blueprint`."""

    def __init__(
        self,
        name: str,
        type_: Any,
        blueprint: Blueprint | None = None,
        **options: Any,
    ) -> None:
        self.name = name
        self.type = type_
        self.options = options
        self._blueprint = blueprint

    def nullable(self, value: bool = True) -> Column:
        self.options["nullable"] = value
        return self

    def default(self, value: Any) -> Column:
        self.options["default"] = value
        return self

    def unique(self, value: bool = True) -> Column:
        self.options["unique"] = value
        return self

    def index(self, value: bool = True) -> Column:
        self.options["index"] = value
        return self

    def primary(self, value: bool = True) -> Column:
        self.options["primary_key"] = value
        return self

    def after(self, column: str) -> Column:
        """Place column after ``column`` (MySQL / MariaDB)."""
        self.options["after"] = column
        self.options.pop("before", None)
        return self

    def before(self, column: str) -> Column:
        """Place column before ``column`` (MariaDB)."""
        self.options["before"] = column
        self.options.pop("after", None)
        return self

    def constrained(
        self,
        table: str | None = None,
        column: str = "id",
        index_name: str | None = None,
    ) -> ForeignKeyDefinition:
        """Attach a foreign key using naming conventions (Laravel ``constrained``)."""
        if self._blueprint is None:
            raise SchemaError("constrained() requires a Blueprint-owned column")
        ref_table = table or _guess_foreign_table(self.name)
        fk = ForeignKeyDefinition(
            self._blueprint,
            [self.name],
            column=self,
            ref_table=ref_table,
            ref_column=column,
            name=index_name,
        )
        fk._sync_column()
        return fk

    def to_sqlalchemy(self) -> sa.Column:
        options = dict(self.options)
        options.setdefault("nullable", not options.get("primary_key", False))
        references = options.pop("references", None)
        on_delete = options.pop("on_delete", None)
        on_update = options.pop("on_update", None)
        options.pop("after", None)
        options.pop("before", None)
        options.pop("index", None)
        args: list[Any] = [self.name, self.type]
        if references:
            fk_kwargs: dict[str, Any] = {}
            if on_delete:
                fk_kwargs["ondelete"] = on_delete
            if on_update:
                fk_kwargs["onupdate"] = on_update
            args.append(sa.ForeignKey(references, **fk_kwargs))
        return sa.Column(*args, **options)


class Blueprint:
    """Fluent table definition."""

    def __init__(self, table: str) -> None:
        self.table = table
        self.columns: list[Column] = []
        self._indexes: list[tuple[str, list[str], bool]] = []
        self._drop_columns: list[str] = []
        self._renames: list[tuple[str, str]] = []
        self._foreign_keys: list[ForeignKeyDefinition] = []

    def _add(self, name: str, type_: Any, **options: Any) -> Column:
        column = Column(name, type_, blueprint=self, **options)
        self.columns.append(column)
        return column

    # --- column types -------------------------------------------------------

    def id(self, name: str = "id") -> Column:
        return self._add(name, sa.Integer, primary_key=True, autoincrement=True)

    def big_increments(self, name: str = "id") -> Column:
        return self._add(name, sa.BigInteger, primary_key=True, autoincrement=True)

    def uuid(self, name: str = "uuid") -> Column:
        return self._add(name, sa.String(36))

    def string(self, name: str, length: int = 255) -> Column:
        return self._add(name, sa.String(length))

    def text(self, name: str) -> Column:
        return self._add(name, sa.Text)

    def integer(self, name: str) -> Column:
        return self._add(name, sa.Integer)

    def big_integer(self, name: str) -> Column:
        return self._add(name, sa.BigInteger)

    def float(self, name: str) -> Column:
        return self._add(name, sa.Float)

    def decimal(self, name: str, precision: int = 8, scale: int = 2) -> Column:
        return self._add(name, sa.Numeric(precision, scale))

    def boolean(self, name: str) -> Column:
        return self._add(name, sa.Boolean)

    def json(self, name: str) -> Column:
        return self._add(name, sa.JSON)

    def date(self, name: str) -> Column:
        return self._add(name, sa.Date)

    def date_time(self, name: str) -> Column:
        return self._add(name, sa.DateTime)

    def timestamp(self, name: str) -> Column:
        return self._add(name, sa.DateTime)

    def timestamps(self) -> None:
        self._add("created_at", sa.DateTime, nullable=True)
        self._add("updated_at", sa.DateTime, nullable=True)

    def soft_deletes(self, name: str = "deleted_at") -> Column:
        return self._add(name, sa.DateTime, nullable=True)

    def foreign_id(self, name: str, references: str | None = None) -> Column:
        """FK column helper (Laravel ``foreignId``). Almasix uses INTEGER."""
        column = self._add(name, sa.Integer, nullable=True)
        if references:
            column.options["references"] = references
        return column

    def morphs(self, name: str) -> None:
        self._add(f"{name}_id", sa.Integer, nullable=True)
        self._add(f"{name}_type", sa.String(255), nullable=True)

    def drop_column(self, *columns: str) -> None:
        """Queue column drops for ``Schema.table`` (Laravel ``dropColumn``)."""
        self._drop_columns.extend(columns)

    def rename_column(self, from_name: str, to_name: str) -> None:
        """Queue a column rename (Laravel ``renameColumn``)."""
        self._renames.append((from_name, to_name))

    def unique(self, columns: str | list[str], name: str | None = None) -> None:
        """Add a unique index (Laravel ``$table->unique(...)``)."""
        cols = [columns] if isinstance(columns, str) else list(columns)
        self.unique_index(cols, name)

    def unique_index(self, columns: list[str], name: str | None = None) -> None:
        self._indexes.append((name or f"uq_{self.table}_{'_'.join(columns)}", columns, True))

    def index(self, columns: str | list[str], name: str | None = None) -> None:
        cols = [columns] if isinstance(columns, str) else list(columns)
        self._indexes.append((name or f"ix_{self.table}_{'_'.join(cols)}", cols, False))

    def foreign(self, *columns: str) -> ForeignKeyDefinition:
        """Add a foreign key on existing column(s) (Laravel ``$table->foreign``)."""
        return ForeignKeyDefinition(self, list(columns))

    # --- compilation --------------------------------------------------------

    def to_table(self, metadata: sa.MetaData) -> sa.Table:
        table = sa.Table(
            self.table,
            metadata,
            *[column.to_sqlalchemy() for column in self.columns],
        )
        for name, columns, unique in self._indexes:
            sa.Index(name, *[table.c[column] for column in columns], unique=unique)
        return table


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
            sa_table = blueprint.to_table(metadata)
            metadata.create_all(sync_conn, tables=[sa_table])

        async with engine.begin() as conn:
            await _enable_foreign_keys(conn, engine.dialect.name)
            await conn.run_sync(reflect_and_create)

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
    async def has_index(table: str, name: str, connection: str | None = None) -> bool:
        engine = _schema_connection(connection).engine

        def inspect(sync_conn: Any) -> bool:
            return any(index["name"] == name for index in sa.inspect(sync_conn).get_indexes(table))

        async with engine.connect() as conn:
            return await conn.run_sync(inspect)

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
    async def table_names(connection: str | None = None) -> list[str]:
        engine = _schema_connection(connection).engine

        def names(sync_conn: Any) -> list[str]:
            return list(sa.inspect(sync_conn).get_table_names())

        async with engine.connect() as conn:
            return await conn.run_sync(names)


def _guess_foreign_table(column: str) -> str:
    """``user_id`` → ``users`` (Laravel constrained convention)."""
    base = column[:-3] if column.endswith("_id") else column
    return pluralize(base)


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

    inline_fk_columns = {
        column.name for column in blueprint.columns if column.options.get("references")
    }

    for column in blueprint.columns:
        # Compile the bare column, then append REFERENCES manually — SQLAlchemy's
        # CreateColumn omits FK clauses on ALTER TABLE ADD COLUMN for SQLite.
        options = dict(column.options)
        references = options.pop("references", None)
        on_delete = options.pop("on_delete", None)
        on_update = options.pop("on_update", None)
        after = options.pop("after", None)
        before = options.pop("before", None)
        options.pop("index", None)
        bare = Column(column.name, column.type, **options)
        sa_col = bare.to_sqlalchemy()
        # mssql CreateColumn requires a Table-bound column.
        if dialect_name in {"mssql", "oracle"}:
            tmp = sa.Table("__almasix_alter__", sa.MetaData())
            tmp.append_column(sa_col)
        col_sql = str(sa.schema.CreateColumn(sa_col).compile(dialect=dialect))
        if references:
            ref_table, _, ref_column = references.partition(".")
            col_sql += (
                f" REFERENCES {quote_ident(dialect, ref_table)} "
                f"({quote_ident(dialect, ref_column or 'id')})"
            )
            if on_delete:  # pragma: no branch
                col_sql += f" ON DELETE {on_delete}"
            if on_update:
                col_sql += f" ON UPDATE {on_update}"
        statement = f"ALTER TABLE {qt} ADD COLUMN {col_sql}"
        if dialect_name == "mysql":
            if after:
                statement += f" AFTER {quote_ident(dialect, after)}"
            elif before:
                statement += f" BEFORE {quote_ident(dialect, before)}"
        statements.append(statement)

    for name in blueprint._drop_columns:
        statements.append(f"ALTER TABLE {qt} DROP COLUMN {quote_ident(dialect, name)}")

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
            f"CREATE {unique_sql}INDEX {quote_ident(dialect, index_name)} "
            f"ON {qt} ({cols})"
        )

    for column in blueprint.columns:
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
