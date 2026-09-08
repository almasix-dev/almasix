"""The table blueprint — Laravel's ``Blueprint``, column by column.

Almasix describes a table in SQLAlchemy types and lets SQLAlchemy compile the
DDL, so most of Laravel's column catalogue is a mapping rather than a grammar.
Where an engine spells a type its own way — MySQL's `MEDIUMINT`, PostgreSQL's
`JSONB`, pgvector's `VECTOR` — the mapping carries a dialect variant, so the
same blueprint means the same thing everywhere it can and says so where it
cannot.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql

from almasix.orm.grammar import Geography, Geometry, UnsupportedByDialectError, Vector
from almasix.orm.inflector import pluralize


class SchemaError(RuntimeError):
    """Raised when a schema operation is unsupported on the active dialect."""


def _variant(base: Any, **per_dialect: Any) -> Any:
    """A type that keeps its meaning on engines that spell it differently."""
    for name, alternative in per_dialect.items():
        base = base.with_variant(alternative, name)
    return base


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


#: Modifiers that describe the column rather than being passed to SQLAlchemy.
_OWN_OPTIONS = frozenset(
    {
        "references",
        "on_delete",
        "on_update",
        "after",
        "before",
        "first",
        "index",
        "unsigned",
        "charset",
        "collation",
        "invisible",
        "use_current",
        "use_current_on_update",
        "change",
        "auto_increment",
        "start_from",
        "spatial",
        "full_text",
    }
)


class Column:
    """One column definition inside a :class:`Blueprint`."""

    def __init__(
        self,
        name: str,
        type_: Any,
        blueprint: Blueprint | None = None,
        **options: Any,
    ) -> None:
        self.name = name
        # A type class and an instance of it mean the same thing to SQLAlchemy;
        # the compiler here needs the instance.
        self.type = type_() if isinstance(type_, type) else type_
        self.options = options
        self._blueprint = blueprint

    # --- modifiers ----------------------------------------------------------

    def nullable(self, value: bool = True) -> Column:
        self.options["nullable"] = value
        return self

    def default(self, value: Any) -> Column:
        """The value a row gets when it does not say — written into the DDL.

        Laravel's default is the engine's, not the application's, so a row
        inserted by anything at all gets it.
        """
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
        """Place the column after ``column`` (MySQL / MariaDB)."""
        self.options["after"] = column
        self.options.pop("before", None)
        self.options.pop("first", None)
        return self

    def before(self, column: str) -> Column:
        """Place the column before ``column`` (MariaDB)."""
        self.options["before"] = column
        self.options.pop("after", None)
        self.options.pop("first", None)
        return self

    def first(self, value: bool = True) -> Column:
        """Place the column first in the table (MySQL / MariaDB)."""
        self.options["first"] = value
        self.options.pop("after", None)
        self.options.pop("before", None)
        return self

    def unsigned(self, value: bool = True) -> Column:
        """No negative values — MySQL and MariaDB only, ignored elsewhere."""
        self.options["unsigned"] = value
        return self

    def comment(self, text: str) -> Column:
        self.options["comment"] = text
        return self

    def charset(self, charset: str) -> Column:
        """The character set for this column (MySQL / MariaDB)."""
        self.options["charset"] = charset
        return self

    def collation(self, collation: str) -> Column:
        self.options["collation"] = collation
        return self

    def use_current(self) -> Column:
        """Default to the time the row was written."""
        self.options["use_current"] = True
        return self

    def use_current_on_update(self) -> Column:
        """Set to the current time on every update (MySQL / MariaDB)."""
        self.options["use_current_on_update"] = True
        return self

    def invisible(self) -> Column:
        """Hide the column from ``SELECT *`` (MySQL 8.0.23+ / MariaDB)."""
        self.options["invisible"] = True
        return self

    def virtual_as(self, expression: str) -> Column:
        """A column computed on read from ``expression``."""
        self.options["computed"] = (expression, False)
        return self

    def stored_as(self, expression: str) -> Column:
        """A column computed on write and stored."""
        self.options["computed"] = (expression, True)
        return self

    def generated_as(self, expression: str = "") -> Column:
        """An identity column — the engine supplies the value."""
        self.options["identity"] = expression
        return self

    def always(self, value: bool = True) -> Column:
        """An identity column the caller may not override."""
        self.options["identity_always"] = value
        return self

    def auto_increment(self, value: bool = True) -> Column:
        self.options["auto_increment"] = value
        self.options["autoincrement"] = value
        return self

    def start_from(self, value: int) -> Column:
        """Where auto-increment begins — Laravel's ``from``."""
        self.options["start_from"] = int(value)
        return self

    def change(self) -> Column:
        """Modify the existing column rather than adding one.

        Everything the column says is re-stated, exactly as Laravel requires:
        an attribute left out of the `change()` call is dropped, not kept.
        """
        self.options["change"] = True
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
        ref_table = table or guess_foreign_table(self.name)
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

    # --- compilation --------------------------------------------------------

    @property
    def changing(self) -> bool:
        return bool(self.options.get("change"))

    def sa_type(self, dialect: Any = None) -> Any:
        """The type this column compiles to, unsigned where that is asked for."""
        if not self.options.get("unsigned"):
            return self.type
        return _unsigned(self.type)

    def to_sqlalchemy(self, dialect: Any = None) -> sa.Column:
        options = {key: value for key, value in self.options.items() if key not in _OWN_OPTIONS}
        options.setdefault("nullable", not options.get("primary_key", False))
        references = self.options.get("references")
        computed = options.pop("computed", None)
        identity = options.pop("identity", None)
        identity_always = options.pop("identity_always", False)
        default = options.pop("default", _NO_DEFAULT)

        args: list[Any] = [self.name, self.sa_type(dialect)]
        if references:
            fk_kwargs: dict[str, Any] = {}
            if self.options.get("on_delete"):
                fk_kwargs["ondelete"] = self.options["on_delete"]
            if self.options.get("on_update"):
                fk_kwargs["onupdate"] = self.options["on_update"]
            args.append(sa.ForeignKey(references, **fk_kwargs))
        if computed is not None:
            args.append(sa.Computed(computed[0], persisted=computed[1] or None))
        if identity is not None:
            args.append(sa.Identity(always=identity_always, start=self.options.get("start_from")))

        server_default = self._server_default(default, dialect)
        if server_default is not None:
            options["server_default"] = server_default
        elif default is not _NO_DEFAULT:
            options["default"] = default
        if self.options.get("use_current_on_update") and _is_mysql(dialect):
            options["server_onupdate"] = sa.text("CURRENT_TIMESTAMP")
        if self.options.get("collation") and _takes_collation(self.type):
            options["type_"] = None  # collation travels on the type below
            options.pop("type_")
        return sa.Column(*args, **options)

    def _server_default(self, default: Any, dialect: Any) -> Any:
        """Laravel's default is the engine's, so it belongs in the DDL."""
        if self.options.get("use_current"):
            return sa.text("CURRENT_TIMESTAMP")
        if default is _NO_DEFAULT or default is None:
            return None
        if isinstance(default, (sa.sql.elements.ClauseElement, sa.sql.functions.Function)):
            return default
        if callable(default):
            return None
        return sa.text(_default_literal(default, dialect))


class _NoDefault:
    """Sentinel so ``default(None)`` stays distinguishable from omission."""

    __slots__ = ()


_NO_DEFAULT = _NoDefault()


def _default_literal(value: Any, dialect: Any) -> str:
    """A default value as the engine in front of us writes one."""
    if isinstance(value, bool):
        if dialect is not None and getattr(dialect, "supports_native_boolean", False):
            return "true" if value else "false"
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, dict)):
        import json

        return "'" + json.dumps(value).replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _is_mysql(dialect: Any) -> bool:
    return getattr(dialect, "name", "") == "mysql"


def _takes_collation(type_: Any) -> bool:
    return isinstance(type_, sa.String)


def _unsigned(type_: Any) -> Any:
    """``unsigned()`` is MySQL's; elsewhere the type is already what it was.

    The MySQL spelling a type already carries is the one that gains the
    keyword, so ``tiny_integer("n").unsigned()`` is `TINYINT UNSIGNED` rather
    than a widened `SMALLINT UNSIGNED`.
    """
    plain = type_.copy()
    mysql_type = plain._variant_mapping.get("mysql", plain)
    plain._variant_mapping = sa.util.immutabledict()
    unsigned = _unsigned_mysql(mysql_type)
    return plain if unsigned is None else plain.with_variant(unsigned, "mysql")


def _unsigned_mysql(type_: Any) -> Any | None:
    """The same MySQL type, told to hold no negatives."""
    if isinstance(type_, sa.Numeric) and not isinstance(type_, sa.Float):
        return mysql.DECIMAL(type_.precision, type_.scale, unsigned=True)
    if not isinstance(type_, sa.Integer):
        return None
    widths: list[tuple[type, Any]] = [
        (mysql.TINYINT, mysql.TINYINT),
        (mysql.MEDIUMINT, mysql.MEDIUMINT),
        (sa.SmallInteger, mysql.SMALLINT),
        (sa.BigInteger, mysql.BIGINT),
        (sa.Integer, mysql.INTEGER),
    ]
    for python_type, mysql_type in widths:
        if isinstance(type_, python_type):
            return mysql_type(unsigned=True)
    return None  # pragma: no cover - every integer matches a width above


def guess_foreign_table(column: str) -> str:
    """``user_id`` → ``users`` (Laravel's ``constrained`` convention)."""
    return pluralize(column.removesuffix("_id"))


class Blueprint:
    """Fluent table definition — every column Laravel's page names."""

    def __init__(self, table: str) -> None:
        self.table = table
        self.columns: list[Column] = []
        self._indexes: list[tuple[str, list[str], bool]] = []
        self._drop_columns: list[str] = []
        self._renames: list[tuple[str, str]] = []
        self._foreign_keys: list[ForeignKeyDefinition] = []
        self._drop_indexes: list[tuple[str, str]] = []
        self._drop_foreign_keys: list[str] = []
        self._rename_indexes: list[tuple[str, str]] = []
        self._primary: tuple[list[str], str | None] | None = None
        self._drop_primary = False
        self._options: dict[str, Any] = {}

    def _add(self, name: str, type_: Any, **options: Any) -> Column:
        column = Column(name, type_, blueprint=self, **options)
        self.columns.append(column)
        return column

    # --- keys ----------------------------------------------------------------

    def id(self, name: str = "id") -> Column:
        return self.big_increments(name)

    def increments(self, name: str = "id") -> Column:
        return self._key(name, sa.Integer())

    def tiny_increments(self, name: str = "id") -> Column:
        return self._key(name, _variant(sa.SmallInteger(), mysql=mysql.TINYINT(unsigned=True)))

    def small_increments(self, name: str = "id") -> Column:
        return self._key(name, sa.SmallInteger())

    def medium_increments(self, name: str = "id") -> Column:
        return self._key(name, _variant(sa.Integer(), mysql=mysql.MEDIUMINT(unsigned=True)))

    def big_increments(self, name: str = "id") -> Column:
        return self._key(name, sa.BigInteger())

    def _key(self, name: str, type_: Any) -> Column:
        """An auto-incrementing primary key.

        SQLite only counts up for an `INTEGER PRIMARY KEY` — any other width
        is an ordinary column that happens to be the key — so every width
        narrows to `INTEGER` there and keeps its own spelling elsewhere.
        """
        return self._add(
            name,
            _variant(type_, sqlite=sa.INTEGER()),
            primary_key=True,
            autoincrement=True,
        )

    # --- strings --------------------------------------------------------------

    def char(self, name: str, length: int = 255) -> Column:
        return self._add(name, sa.CHAR(length))

    def string(self, name: str, length: int | None = None) -> Column:
        return self._add(name, sa.String(length or Blueprint.default_string_length))

    def tiny_text(self, name: str) -> Column:
        return self._add(name, _variant(sa.Text(), mysql=mysql.TINYTEXT()))

    def text(self, name: str) -> Column:
        return self._add(name, sa.Text)

    def medium_text(self, name: str) -> Column:
        return self._add(name, _variant(sa.Text(), mysql=mysql.MEDIUMTEXT()))

    def long_text(self, name: str) -> Column:
        return self._add(name, _variant(sa.Text(), mysql=mysql.LONGTEXT()))

    #: What ``string()`` uses when no length is given — Laravel's `$stringLength`.
    default_string_length = 255

    # --- numbers ---------------------------------------------------------------

    def tiny_integer(self, name: str) -> Column:
        return self._add(name, _variant(sa.SmallInteger(), mysql=mysql.TINYINT()))

    def small_integer(self, name: str) -> Column:
        return self._add(name, sa.SmallInteger)

    def medium_integer(self, name: str) -> Column:
        return self._add(name, _variant(sa.Integer(), mysql=mysql.MEDIUMINT()))

    def integer(self, name: str) -> Column:
        return self._add(name, sa.Integer)

    def big_integer(self, name: str) -> Column:
        return self._add(name, sa.BigInteger)

    def unsigned_tiny_integer(self, name: str) -> Column:
        return self.tiny_integer(name).unsigned()

    def unsigned_small_integer(self, name: str) -> Column:
        return self.small_integer(name).unsigned()

    def unsigned_medium_integer(self, name: str) -> Column:
        return self.medium_integer(name).unsigned()

    def unsigned_integer(self, name: str) -> Column:
        return self.integer(name).unsigned()

    def unsigned_big_integer(self, name: str) -> Column:
        return self.big_integer(name).unsigned()

    def float(self, name: str, precision: int = 53) -> Column:
        return self._add(name, sa.Float(precision))

    def double(self, name: str) -> Column:
        return self._add(name, sa.Double)

    def decimal(self, name: str, precision: int = 8, scale: int = 2) -> Column:
        return self._add(name, sa.Numeric(precision, scale))

    def unsigned_decimal(self, name: str, precision: int = 8, scale: int = 2) -> Column:
        return self.decimal(name, precision, scale).unsigned()

    def boolean(self, name: str) -> Column:
        return self._add(name, sa.Boolean)

    # --- enumerations -----------------------------------------------------------

    def enum(self, name: str, values: list[str]) -> Column:
        """One of a fixed list — a check constraint everywhere but MySQL."""
        return self._add(
            name,
            _variant(
                sa.Enum(*values, name=f"{self.table}_{name}", native_enum=False),
                mysql=mysql.ENUM(*values),
            ),
        )

    def set(self, name: str, values: list[str]) -> Column:
        """Several of a fixed list, in one column — MySQL and MariaDB only."""
        return self._add(
            name,
            _variant(sa.String(max(sum(len(v) + 1 for v in values), 1)), mysql=mysql.SET(*values)),
        )

    # --- documents ---------------------------------------------------------------

    def json(self, name: str) -> Column:
        return self._add(name, sa.JSON)

    def jsonb(self, name: str) -> Column:
        return self._add(name, _variant(sa.JSON(), postgresql=postgresql.JSONB()))

    # --- dates and times ------------------------------------------------------------

    def date(self, name: str) -> Column:
        return self._add(name, sa.Date)

    def date_time(self, name: str, precision: int | None = None) -> Column:
        return self._add(name, sa.DateTime)

    def date_time_tz(self, name: str, precision: int | None = None) -> Column:
        return self._add(name, sa.DateTime(timezone=True))

    def time(self, name: str, precision: int | None = None) -> Column:
        return self._add(name, sa.Time)

    def time_tz(self, name: str, precision: int | None = None) -> Column:
        return self._add(name, sa.Time(timezone=True))

    def timestamp(self, name: str, precision: int | None = None) -> Column:
        return self._add(name, sa.DateTime)

    def timestamp_tz(self, name: str, precision: int | None = None) -> Column:
        return self._add(name, sa.DateTime(timezone=True))

    def timestamps(self, precision: int | None = None) -> None:
        self._add("created_at", sa.DateTime, nullable=True)
        self._add("updated_at", sa.DateTime, nullable=True)

    def timestamps_tz(self, precision: int | None = None) -> None:
        self._add("created_at", sa.DateTime(timezone=True), nullable=True)
        self._add("updated_at", sa.DateTime(timezone=True), nullable=True)

    #: Laravel keeps this name for the pair that were always nullable here.
    nullable_timestamps = timestamps

    def soft_deletes(self, name: str = "deleted_at", precision: int | None = None) -> Column:
        return self._add(name, sa.DateTime, nullable=True)

    def soft_deletes_tz(self, name: str = "deleted_at", precision: int | None = None) -> Column:
        return self._add(name, sa.DateTime(timezone=True), nullable=True)

    def year(self, name: str) -> Column:
        return self._add(name, _variant(sa.Integer(), mysql=mysql.YEAR()))

    # --- binary and identifiers ---------------------------------------------------------

    def binary(self, name: str, length: int | None = None) -> Column:
        return self._add(name, sa.LargeBinary(length) if length else sa.LargeBinary)

    def uuid(self, name: str = "uuid") -> Column:
        return self._add(name, _variant(sa.String(36), postgresql=postgresql.UUID(as_uuid=False)))

    def ulid(self, name: str = "ulid", length: int = 26) -> Column:
        return self._add(name, sa.String(length))

    def ip_address(self, name: str = "ip_address") -> Column:
        return self._add(name, sa.String(45))

    def mac_address(self, name: str = "mac_address") -> Column:
        return self._add(name, sa.String(17))

    def remember_token(self) -> Column:
        return self._add("remember_token", sa.String(100), nullable=True)

    # --- foreign keys ---------------------------------------------------------------------

    def foreign_id(self, name: str, references: str | None = None) -> Column:
        """The column a `belongs_to` reads — Laravel's ``foreignId``."""
        column = self._add(name, sa.BigInteger, nullable=True)
        if references:
            column.options["references"] = references
        return column

    def foreign_uuid(self, name: str) -> Column:
        return self.uuid(name).nullable()

    def foreign_ulid(self, name: str, length: int = 26) -> Column:
        return self.ulid(name, length).nullable()

    def foreign_id_for(self, model: Any, name: str | None = None) -> Column:
        """The foreign key for a model, named the way that model would name it."""
        table = getattr(model, "table", None) or getattr(model, "__name__", "")
        column = name or f"{_singular_key(table)}_{getattr(model, 'primary_key', 'id')}"
        key_type = str(getattr(model, "key_type", "int")).lower()
        if key_type in {"uuid", "string", "str"}:
            return self.foreign_uuid(column)
        return self.foreign_id(column)

    def foreign(self, *columns: str) -> ForeignKeyDefinition:
        """A foreign key on existing column(s) — Laravel's ``$table->foreign``."""
        return ForeignKeyDefinition(self, list(columns))

    # --- polymorphic pairs -------------------------------------------------------------------

    def morphs(self, name: str, index_name: str | None = None) -> None:
        self._add(f"{name}_id", sa.BigInteger, nullable=True)
        self._add(f"{name}_type", sa.String(255), nullable=True)
        self.index([f"{name}_type", f"{name}_id"], index_name)

    def nullable_morphs(self, name: str, index_name: str | None = None) -> None:
        self.morphs(name, index_name)

    def uuid_morphs(self, name: str, index_name: str | None = None) -> None:
        self.uuid(f"{name}_id").nullable()
        self._add(f"{name}_type", sa.String(255), nullable=True)
        self.index([f"{name}_type", f"{name}_id"], index_name)

    def ulid_morphs(self, name: str, index_name: str | None = None) -> None:
        self.ulid(f"{name}_id").nullable()
        self._add(f"{name}_type", sa.String(255), nullable=True)
        self.index([f"{name}_type", f"{name}_id"], index_name)

    # --- engine-specific ----------------------------------------------------------------------

    def vector(self, name: str, dimensions: int) -> Column:
        """A pgvector / MariaDB vector column, for the searches M42 can run."""
        return self._add(name, Vector(dimensions))

    def geometry(self, name: str, subtype: str | None = None, srid: int = 0) -> Column:
        return self._add(name, Geometry(subtype, srid))

    def geography(self, name: str, subtype: str | None = None, srid: int = 4326) -> Column:
        return self._add(name, Geography(subtype, srid))

    def raw_column(self, name: str, definition: str) -> Column:
        """A column written out in the engine's own words."""
        return self._add(name, _RawType(definition))

    # --- table-level ---------------------------------------------------------------------------

    def primary(self, columns: str | list[str], name: str | None = None) -> None:
        cols = [columns] if isinstance(columns, str) else list(columns)
        self._primary = (cols, name)

    def unique(self, columns: str | list[str], name: str | None = None) -> None:
        cols = [columns] if isinstance(columns, str) else list(columns)
        self.unique_index(cols, name)

    def unique_index(self, columns: list[str], name: str | None = None) -> None:
        self._indexes.append((name or self.index_name(columns, "uq"), columns, True))

    def index(self, columns: str | list[str], name: str | None = None) -> None:
        cols = [columns] if isinstance(columns, str) else list(columns)
        self._indexes.append((name or self.index_name(cols, "ix"), cols, False))

    def index_name(self, columns: list[str], kind: str = "ix") -> str:
        return f"{kind}_{self.table}_{'_'.join(columns)}"

    def engine(self, name: str) -> None:
        """The storage engine for a new table (MySQL / MariaDB)."""
        self._options["mysql_engine"] = name

    def charset(self, charset: str) -> None:
        self._options["mysql_charset"] = charset

    def collation(self, collation: str) -> None:
        self._options["mysql_collate"] = collation

    def comment(self, text: str) -> None:
        self._options["comment"] = text

    # --- dropping ------------------------------------------------------------------------------------

    def drop_column(self, *columns: str) -> None:
        """Queue column drops for ``Schema.table`` (Laravel ``dropColumn``)."""
        self._drop_columns.extend(columns)

    def rename_column(self, from_name: str, to_name: str) -> None:
        self._renames.append((from_name, to_name))

    def drop_index(self, name: str) -> None:
        self._drop_indexes.append((name, "index"))

    def drop_unique(self, columns: str | list[str] | None = None, name: str | None = None) -> None:
        self._drop_indexes.append((name or self._named(columns, "uq"), "unique"))

    def drop_primary(self, name: str | None = None) -> None:
        self._drop_primary = True

    def drop_foreign(self, columns: str | list[str] | None = None, name: str | None = None) -> None:
        cols = [columns] if isinstance(columns, str) else list(columns or [])
        self._drop_foreign_keys.append(name or f"{self.table}_{'_'.join(cols)}_foreign")

    def drop_constrained_foreign_id(self, column: str) -> None:
        """Drop the foreign key and the column it was on, in that order."""
        self.drop_foreign(column)
        self.drop_column(column)

    def rename_index(self, from_name: str, to_name: str) -> None:
        self._rename_indexes.append((from_name, to_name))

    def drop_morphs(self, name: str) -> None:
        self.drop_index(self.index_name([f"{name}_type", f"{name}_id"]))
        self.drop_column(f"{name}_id", f"{name}_type")

    def drop_soft_deletes(self, name: str = "deleted_at") -> None:
        self.drop_column(name)

    drop_soft_deletes_tz = drop_soft_deletes

    def drop_timestamps(self) -> None:
        self.drop_column("created_at", "updated_at")

    drop_timestamps_tz = drop_timestamps

    def drop_remember_token(self) -> None:
        self.drop_column("remember_token")

    def _named(self, columns: str | list[str] | None, kind: str) -> str:
        cols = [columns] if isinstance(columns, str) else list(columns or [])
        return self.index_name(cols, kind)

    # --- compilation --------------------------------------------------------------------------------------

    def to_table(self, metadata: sa.MetaData, dialect: Any = None) -> sa.Table:
        columns = [column.to_sqlalchemy(dialect) for column in self.columns]
        table = sa.Table(self.table, metadata, *columns, **self._options)
        for name, index_columns, unique in self._indexes:
            sa.Index(name, *[table.c[column] for column in index_columns], unique=unique)
        # A column that asked for its own index gets one here too; on the alter
        # path the same request becomes a CREATE INDEX after the column lands.
        for column in self.columns:
            if column.options.get("index"):
                sa.Index(self.index_name([column.name]), table.c[column.name])
        if self._primary is not None:
            names, _ = self._primary
            table.append_constraint(sa.PrimaryKeyConstraint(*names))
        return table


class _RawType(sa.types.UserDefinedType):
    """A column type written out exactly as given."""

    cache_ok = True

    def __init__(self, definition: str) -> None:
        self.definition = definition

    def get_col_spec(self, **_: Any) -> str:
        return self.definition


def _singular_key(table: str) -> str:
    """``users`` → ``user``, for the column a foreign key is named after."""
    if table.endswith("ies"):
        return table[:-3] + "y"
    if table.endswith(("ses", "xes")):
        return table[:-2]
    return table.removesuffix("s")


__all__ = [
    "Blueprint",
    "Column",
    "ForeignKeyDefinition",
    "SchemaError",
    "UnsupportedByDialectError",
    "guess_foreign_table",
]
