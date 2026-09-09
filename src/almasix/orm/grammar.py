"""The SQL that engines spell differently.

Most of the query builder compiles through SQLAlchemy Core, which already
knows each dialect. A handful of clauses do not: JSON containment, full-text
search, and vector distance are written three different ways by SQLite,
MySQL/MariaDB, and PostgreSQL, and SQLAlchemy has no portable construct for
them. Those live here as compiled expressions, one compiler per dialect — the
same job Laravel's grammar classes do.

An engine that cannot do the operation raises rather than compiling something
that quietly means the wrong thing.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement


class UnsupportedByDialectError(RuntimeError):
    """Raised when an engine has no way to express a clause."""

    def __init__(self, operation: str, dialect: str) -> None:
        self.operation = operation
        self.dialect = dialect
        super().__init__(f"{dialect} has no {operation} support.")


def split_json_path(reference: str) -> tuple[str, list[str]]:
    """Split Laravel's ``"options->dining->meal"`` into a column and a path."""
    column, _, rest = reference.partition("->")
    if not rest:
        return column.strip(), []
    return column.strip(), [segment.strip() for segment in rest.split("->") if segment.strip()]


def is_json_path(reference: Any) -> bool:
    """Whether a column reference reaches inside a JSON document."""
    return isinstance(reference, str) and "->" in reference


def _dotted_path(path: list[str]) -> str:
    """The ``$."a"."b"`` path literal MySQL and SQLite both read."""
    return "$" + "".join(f'."{segment}"' for segment in path)


def _brace_path(path: list[str]) -> str:
    """The ``{a,b}`` path literal PostgreSQL's ``#>`` operator reads."""
    return "{" + ",".join(path) + "}"


def _pg_json_extract(column_sql: str, path_sql: str) -> str:
    """``#>`` needs ``jsonb`` on the left and ``text[]`` on the right.

    A plain ``json`` column and a string bind both fail under asyncpg —
    cast both sides so ``json`` / ``jsonb`` columns share one spelling.
    """
    return f"(CAST({column_sql} AS JSONB) #> CAST({path_sql} AS text[]))"


def _is_mariadb(dialect: Any) -> bool:
    return bool(getattr(dialect, "is_mariadb", False))


class JsonContains(ColumnElement[bool]):
    """``whereJsonContains`` — is this value inside the JSON array?"""

    type = sa.Boolean()
    inherit_cache = True

    def __init__(self, column: Any, value: Any, path: list[str]) -> None:
        self.column = column
        self.value = value
        self.path = path


@compiles(JsonContains, "sqlite")
def _json_contains_sqlite(element: JsonContains, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    value = compiler.process(sa.literal(element.value), **kw)
    return f"EXISTS (SELECT 1 FROM json_each({column}, {path}) WHERE json_each.value = {value})"


@compiles(JsonContains, "mysql")
def _json_contains_mysql(element: JsonContains, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    document = compiler.process(sa.literal(json.dumps(element.value)), **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    return f"JSON_CONTAINS({column}, {document}, {path})"


@compiles(JsonContains, "postgresql")
def _json_contains_postgresql(element: JsonContains, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    document = compiler.process(sa.literal(json.dumps(element.value)), **kw)
    if element.path:
        path = compiler.process(sa.literal(_brace_path(element.path)), **kw)
        column = _pg_json_extract(column, path)
    return f"CAST({column} AS JSONB) @> CAST({document} AS JSONB)"


@compiles(JsonContains)
def _json_contains_unsupported(element: JsonContains, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("JSON contains", compiler.dialect.name)


class JsonContainsKey(ColumnElement[bool]):
    """``whereJsonContainsKey`` — does the document have this key at all?"""

    type = sa.Boolean()
    inherit_cache = True

    def __init__(self, column: Any, path: list[str]) -> None:
        self.column = column
        self.path = path


@compiles(JsonContainsKey, "sqlite")
def _json_key_sqlite(element: JsonContainsKey, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    return f"JSON_TYPE({column}, {path}) IS NOT NULL"


@compiles(JsonContainsKey, "mysql")
def _json_key_mysql(element: JsonContainsKey, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    return f"IFNULL(JSON_CONTAINS_PATH({column}, 'one', {path}), 0)"


@compiles(JsonContainsKey, "postgresql")
def _json_key_postgresql(element: JsonContainsKey, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    return f"JSONB_PATH_EXISTS(CAST({column} AS JSONB), CAST({path} AS JSONPATH))"


@compiles(JsonContainsKey)
def _json_key_unsupported(element: JsonContainsKey, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("JSON key", compiler.dialect.name)


class JsonLength(ColumnElement[int]):
    """``whereJsonLength`` — how many entries the JSON array holds."""

    type = sa.Integer()
    inherit_cache = True

    def __init__(self, column: Any, path: list[str]) -> None:
        self.column = column
        self.path = path


@compiles(JsonLength, "sqlite")
def _json_length_sqlite(element: JsonLength, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    return f"JSON_ARRAY_LENGTH({column}, {path})"


@compiles(JsonLength, "mysql")
def _json_length_mysql(element: JsonLength, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    return f"JSON_LENGTH({column}, {path})"


@compiles(JsonLength, "postgresql")
def _json_length_postgresql(element: JsonLength, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    if element.path:
        path = compiler.process(sa.literal(_brace_path(element.path)), **kw)
        column = _pg_json_extract(column, path)
    return f"JSONB_ARRAY_LENGTH(CAST({column} AS JSONB))"


@compiles(JsonLength)
def _json_length_unsupported(element: JsonLength, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("JSON length", compiler.dialect.name)


class FullText(ColumnElement[bool]):
    """``whereFullText`` — a match against a full-text index.

    ``mode`` is Laravel's: ``natural`` (the default), ``boolean``, ``plain``,
    ``phrase``, or ``websearch``. MySQL and MariaDB read the first two;
    PostgreSQL reads the last three.
    """

    type = sa.Boolean()
    inherit_cache = True

    def __init__(
        self,
        columns: list[Any],
        value: Any,
        mode: str = "natural",
        language: str = "english",
    ) -> None:
        self.columns = columns
        self.value = value
        self.mode = mode
        self.language = language


@compiles(FullText, "mysql")
def _full_text_mysql(element: FullText, compiler: Any, **kw: Any) -> str:
    columns = ", ".join(compiler.process(column, **kw) for column in element.columns)
    value = compiler.process(sa.literal(element.value), **kw)
    against = "IN BOOLEAN MODE" if element.mode == "boolean" else "IN NATURAL LANGUAGE MODE"
    expanded = " WITH QUERY EXPANSION" if element.mode == "expanded" else ""
    return f"MATCH ({columns}) AGAINST ({value} {against}{expanded})"


@compiles(FullText, "postgresql")
def _full_text_postgresql(element: FullText, compiler: Any, **kw: Any) -> str:
    language = compiler.process(sa.literal(element.language), **kw)
    vectors = " || ".join(
        f"TO_TSVECTOR({language}, {compiler.process(column, **kw)})" for column in element.columns
    )
    query = {"plain": "PLAINTO_TSQUERY", "phrase": "PHRASETO_TSQUERY"}.get(
        element.mode, "WEBSEARCH_TO_TSQUERY" if element.mode == "websearch" else "PLAINTO_TSQUERY"
    )
    value = compiler.process(sa.literal(element.value), **kw)
    return f"({vectors}) @@ {query}({language}, {value})"


@compiles(FullText)
def _full_text_unsupported(element: FullText, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("full-text search", compiler.dialect.name)


class JsonSet(ColumnElement[Any]):
    """Rewrite one path inside a JSON document, leaving the rest alone.

    Nests: the ``column`` of one ``JsonSet`` may be another, which is how
    several edits to the same column become a single expression.
    """

    inherit_cache = True

    def __init__(self, column: Any, path: list[str], value: Any) -> None:
        self.column = column
        self.path = path
        self.value = value

    @property
    def encoded(self) -> str:
        """The new value as JSON text, so every type survives the round trip."""
        return json.dumps(self.value)


@compiles(JsonSet, "sqlite")
def _json_set_sqlite(element: JsonSet, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    value = compiler.process(sa.literal(element.encoded), **kw)
    return f"JSON_SET({column}, {path}, JSON({value}))"


@compiles(JsonSet, "mysql")
def _json_set_mysql(element: JsonSet, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_dotted_path(element.path)), **kw)
    value = compiler.process(sa.literal(element.encoded), **kw)
    return f"JSON_SET({column}, {path}, CAST({value} AS JSON))"


@compiles(JsonSet, "postgresql")
def _json_set_postgresql(element: JsonSet, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    path = compiler.process(sa.literal(_brace_path(element.path)), **kw)
    value = compiler.process(sa.literal(element.encoded), **kw)
    return f"JSONB_SET(CAST({column} AS JSONB), CAST({path} AS text[]), CAST({value} AS JSONB))"


@compiles(JsonSet)
def _json_set_unsupported(element: JsonSet, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("JSON update", compiler.dialect.name)


class CaseSensitiveLike(ColumnElement[bool]):
    """``whereLike(..., case_sensitive=True)``.

    Only MySQL and MariaDB need saying: their default collations make ``LIKE``
    case-insensitive, so a case-sensitive match asks for ``LIKE BINARY``.
    Every other engine we support already compares ``LIKE`` byte for byte —
    except SQLite, whose ``LIKE`` is case-insensitive for ASCII and has no
    per-query way to say otherwise.
    """

    type = sa.Boolean()
    inherit_cache = True

    def __init__(self, column: Any, pattern: Any, negate: bool = False) -> None:
        self.column = column
        self.pattern = pattern
        self.negate = negate


@compiles(CaseSensitiveLike, "mysql")
def _like_binary_mysql(element: CaseSensitiveLike, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    pattern = compiler.process(sa.literal(element.pattern), **kw)
    operator = "NOT LIKE BINARY" if element.negate else "LIKE BINARY"
    return f"{column} {operator} {pattern}"


@compiles(CaseSensitiveLike)
def _like_binary_default(element: CaseSensitiveLike, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    pattern = compiler.process(sa.literal(element.pattern), **kw)
    operator = "NOT LIKE" if element.negate else "LIKE"
    return f"{column} {operator} {pattern}"


class VectorDistance(ColumnElement[float]):
    """Cosine distance between a vector column and a query vector.

    ``0.0`` is identical and ``1.0`` is orthogonal, which is the convention
    pgvector's ``<=>`` operator uses; similarity is ``1 - distance``.
    """

    type = sa.Float()
    inherit_cache = True

    def __init__(self, column: Any, vector: Any) -> None:
        self.column = column
        self.vector = vector

    @property
    def literal(self) -> str:
        """The query vector as the bracketed text both engines parse."""
        if isinstance(self.vector, str):
            return self.vector
        return "[" + ",".join(repr(float(value)) for value in self.vector) + "]"


@compiles(VectorDistance, "postgresql")
def _vector_postgresql(element: VectorDistance, compiler: Any, **kw: Any) -> str:
    column = compiler.process(element.column, **kw)
    vector = compiler.process(sa.literal(element.literal), **kw)
    return f"({column} <=> CAST({vector} AS VECTOR))"


@compiles(VectorDistance, "mysql")
def _vector_mysql(element: VectorDistance, compiler: Any, **kw: Any) -> str:
    if not _is_mariadb(compiler.dialect):
        raise UnsupportedByDialectError("vector distance", "MySQL")
    column = compiler.process(element.column, **kw)
    vector = compiler.process(sa.literal(element.literal), **kw)
    return f"VEC_DISTANCE_COSINE({column}, VEC_FROMTEXT({vector}))"


@compiles(VectorDistance)
def _vector_unsupported(element: VectorDistance, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("vector distance", compiler.dialect.name)


class Vector(sa.types.UserDefinedType[Any]):
    """A fixed-width embedding — pgvector's ``VECTOR(n)``, MariaDB's ``VECTOR(n)``.

    SQLite and SQL Server have nothing to store one in, so a blueprint that
    asks for a vector column says so when it is compiled rather than quietly
    creating text.
    """

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = int(dimensions)

    def get_col_spec(self, **_: Any) -> str:
        return f"VECTOR({self.dimensions})"


@compiles(Vector, "sqlite")
@compiles(Vector, "mssql")
@compiles(Vector, "oracle")
def _vector_type_unsupported(element: Vector, compiler: Any, **kw: Any) -> str:
    raise UnsupportedByDialectError("vector columns", compiler.dialect.name)


class Geometry(sa.types.UserDefinedType[Any]):
    """A shape on a plane — ``GEOMETRY``, or ``POINT``/``POLYGON`` when narrowed."""

    cache_ok = True
    keyword = "GEOMETRY"

    def __init__(self, subtype: str | None = None, srid: int = 0) -> None:
        self.subtype = subtype
        self.srid = srid

    def get_col_spec(self, **_: Any) -> str:
        return (self.subtype or self.keyword).upper()


@compiles(Geometry, "postgresql")
def _geometry_postgresql(element: Geometry, compiler: Any, **kw: Any) -> str:
    """PostGIS carries the shape and the reference system in the type itself."""
    inner = (element.subtype or element.keyword).upper()
    if element.srid:
        return f"GEOMETRY({inner},{element.srid})"
    return f"GEOMETRY({inner})"


@compiles(Geometry, "sqlite")
def _geometry_sqlite(element: Geometry, compiler: Any, **kw: Any) -> str:
    """SpatiaLite is an extension; plain SQLite keeps the well-known binary."""
    return "BLOB"


class Geography(Geometry):
    """A shape on the globe — PostGIS ``GEOGRAPHY``, MySQL's SRID-4326 geometry."""

    keyword = "GEOGRAPHY"


@compiles(Geography, "postgresql")
def _geography_postgresql(element: Geography, compiler: Any, **kw: Any) -> str:
    inner = (element.subtype or "GEOMETRY").upper()
    return f"GEOGRAPHY({inner},{element.srid or 4326})"


@compiles(Geography, "mysql")
def _geography_mysql(element: Geography, compiler: Any, **kw: Any) -> str:
    """MySQL has one spatial type; a geography is it, pinned to WGS 84."""
    return (element.subtype or "GEOMETRY").upper() + f" SRID {element.srid or 4326}"


@compiles(Geography, "sqlite")
def _geography_sqlite(element: Geography, compiler: Any, **kw: Any) -> str:
    return "BLOB"


def json_value(column: Any, path: list[str], sample: Any) -> Any:
    """A JSON path read, typed to compare against ``sample``.

    SQLAlchemy compiles the extraction per dialect; what it needs from us is
    the type to read the extracted value back as, which Laravel infers from
    the value being compared — a boolean comparison reads a boolean.
    """
    document = sa.type_coerce(column, sa.JSON)
    target = document[tuple(path)] if len(path) > 1 else document[path[0]]
    if isinstance(sample, bool):
        return target.as_boolean()
    if isinstance(sample, int):
        return target.as_integer()
    if isinstance(sample, float):
        return target.as_float()
    return target.as_string()
