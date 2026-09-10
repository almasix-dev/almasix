"""Database schema index for the language server.

Tables and columns are read statically from ``database/migrations`` (applied in
filename order, so a later ``Schema.table`` alteration wins) and from model
``fillable`` / ``casts`` declarations. A live connection can fill in what the
static read cannot see — it is opt-in because a language server must never
block on a database.
"""

from __future__ import annotations

import ast
import asyncio
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

#: ``method name -> column type shown in completion``. Only methods whose first
#: string argument names a column belong here.
_COLUMN_METHODS: dict[str, str] = {
    "char": "char",
    "string": "string",
    "tiny_text": "tinytext",
    "text": "text",
    "medium_text": "mediumtext",
    "long_text": "longtext",
    "tiny_integer": "tinyint",
    "small_integer": "smallint",
    "medium_integer": "mediumint",
    "integer": "integer",
    "big_integer": "bigint",
    "unsigned_tiny_integer": "unsigned tinyint",
    "unsigned_small_integer": "unsigned smallint",
    "unsigned_medium_integer": "unsigned mediumint",
    "unsigned_integer": "unsigned integer",
    "unsigned_big_integer": "unsigned bigint",
    "increments": "auto-increment",
    "tiny_increments": "auto-increment",
    "small_increments": "auto-increment",
    "medium_increments": "auto-increment",
    "big_increments": "auto-increment",
    "float": "float",
    "double": "double",
    "decimal": "decimal",
    "unsigned_decimal": "unsigned decimal",
    "boolean": "boolean",
    "enum": "enum",
    "set": "set",
    "json": "json",
    "jsonb": "jsonb",
    "date": "date",
    "date_time": "datetime",
    "date_time_tz": "datetime tz",
    "time": "time",
    "time_tz": "time tz",
    "timestamp": "timestamp",
    "timestamp_tz": "timestamp tz",
    "year": "year",
    "binary": "binary",
    "uuid": "uuid",
    "ulid": "ulid",
    "ip_address": "ip",
    "mac_address": "mac",
    "vector": "vector",
    "geometry": "geometry",
    "geography": "geography",
    "raw_column": "raw",
    "foreign_id": "foreign id",
    "foreign_uuid": "foreign uuid",
    "foreign_ulid": "foreign ulid",
}

#: Methods that add fixed column names. ``id`` / ``soft_deletes`` accept an
#: override as their first argument.
_IMPLICIT_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "id": (("id", "bigint pk"),),
    "timestamps": (("created_at", "timestamp"), ("updated_at", "timestamp")),
    "timestamps_tz": (("created_at", "timestamp tz"), ("updated_at", "timestamp tz")),
    "nullable_timestamps": (("created_at", "timestamp"), ("updated_at", "timestamp")),
    "soft_deletes": (("deleted_at", "timestamp"),),
    "soft_deletes_tz": (("deleted_at", "timestamp tz"),),
    "remember_token": (("remember_token", "string"),),
}

#: ``morphs("owner")`` -> ``owner_type`` + ``owner_id``.
_MORPH_METHODS: dict[str, str] = {
    "morphs": "string",
    "nullable_morphs": "string",
    "uuid_morphs": "uuid",
    "ulid_morphs": "ulid",
}

_DROP_IMPLICIT: dict[str, tuple[str, ...]] = {
    "drop_soft_deletes": ("deleted_at",),
    "drop_soft_deletes_tz": ("deleted_at",),
    "drop_timestamps": ("created_at", "updated_at"),
    "drop_timestamps_tz": ("created_at", "updated_at"),
    "drop_remember_token": ("remember_token",),
}


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    table: str
    type: str = ""
    #: ``migration`` / ``model`` / ``live``.
    source: str = "migration"
    path: Path | None = None
    line: int = 0

    @property
    def detail(self) -> str:
        parts = [part for part in (self.table, self.type) if part]
        return " · ".join(parts) if parts else self.table


@dataclass(frozen=True)
class TableInfo:
    name: str
    columns: dict[str, ColumnInfo] = field(default_factory=dict)
    source: str = "migration"
    path: Path | None = None
    line: int = 0
    #: Model class backing this table, when one declares it.
    model: str | None = None

    @property
    def detail(self) -> str:
        parts = [f"{len(self.columns)} columns", self.source]
        if self.model:
            parts.append(self.model)
        return " · ".join(parts)


def resolve_table(hint: str | None, tables: dict[str, TableInfo]) -> str | None:
    """Turn ``"posts"`` or a model class like ``"Post"`` into a known table name."""
    if not hint:
        return None
    if hint in tables:
        return hint
    for name, table in tables.items():
        if table.model == hint:
            return name
    from almasix.orm.inflector import table_name as derive_table_name

    derived = derive_table_name(hint)
    return derived if derived in tables else None


def discover_migration_schema(root: Path) -> dict[str, TableInfo]:
    """Replay ``database/migrations`` in filename order into a table map."""
    tables: dict[str, TableInfo] = {}
    for path in migration_files(root):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:  # pragma: no cover - app code that does not parse
            continue
        _apply_migration(tables, tree, path)
    return tables


def migration_files(root: Path) -> list[Path]:
    """Migration modules, ordered the way the migrator applies them."""
    base = root / "database" / "migrations"
    if not base.is_dir():
        return []
    return sorted(
        path for path in base.rglob("*.py") if path.is_file() and not path.name.startswith("_")
    )


def _apply_migration(tables: dict[str, TableInfo], tree: ast.AST, path: Path) -> None:
    # Blueprints are often methods (`Schema.create("users", self.users)`), so the
    # bodies to walk may live anywhere in the module.
    callables: dict[str, ast.AST] = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    # Only ``up()``: ``down()`` drops everything the migration just created.
    for node in ast.walk(_up_method(tree) or tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == "Schema"):
            continue
        action = func.attr

        if action in {"drop", "drop_if_exists"}:
            name = _const_str_arg(node, 0)
            if name is not None:
                tables.pop(name, None)
            continue
        if action == "rename":
            old = _const_str_arg(node, 0)
            new = _const_str_arg(node, 1)
            if old is None or new is None:
                continue
            existing = tables.pop(old, None)
            if existing is not None:
                tables[new] = replace(
                    existing,
                    name=new,
                    columns={key: replace(col, table=new) for key, col in existing.columns.items()},
                )
            continue
        if action not in {"create", "create_if_not_exists", "table"}:
            continue

        name = _const_str_arg(node, 0)
        if name is None or len(node.args) < 2:
            continue
        creating = action != "table"
        table = tables.get(name)
        if table is None or creating:
            table = TableInfo(name=name, path=path.resolve(), line=node.lineno - 1)
        columns = dict(table.columns)
        _apply_blueprint(columns, node.args[1], name, path, callables=callables)
        tables[name] = replace(table, columns=columns)


def _apply_blueprint(
    columns: dict[str, ColumnInfo],
    callback: ast.AST,
    table_name: str,
    path: Path,
    *,
    callables: dict[str, ast.AST],
) -> None:
    """Collect / drop columns from the blueprint body of a Schema call."""
    body = _resolve_callback(callback, callables)
    if body is None:
        return
    param = _callback_param(body)
    if param is None:
        return
    for node in ast.walk(body):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Only direct calls on the blueprint: `table.string("x")`. Chained
        # modifiers (`.unique()`, `.after("y")`) hang off a Call, not the param,
        # and `table.unique("token")` is an index rather than a column.
        if not isinstance(func, ast.Attribute):
            continue
        if not (isinstance(func.value, ast.Name) and func.value.id == param):
            continue
        method = func.attr
        line = node.lineno - 1

        def _add(name: str, type_label: str, *, line: int = line) -> None:
            columns[name] = ColumnInfo(
                name=name,
                table=table_name,
                type=type_label,
                source="migration",
                path=path.resolve(),
                line=line,
            )

        if method in _COLUMN_METHODS:
            name = _const_str_arg(node, 0)
            if name is not None:
                _add(name, _COLUMN_METHODS[method])
            continue
        if method in _IMPLICIT_COLUMNS:
            override = _const_str_arg(node, 0)
            implied = _IMPLICIT_COLUMNS[method]
            if override is not None and len(implied) == 1:
                _add(override, implied[0][1])
                continue
            for name, type_label in implied:
                _add(name, type_label)
            continue
        if method in _MORPH_METHODS:
            base = _const_str_arg(node, 0)
            if base is not None:
                _add(f"{base}_type", "string")
                _add(f"{base}_id", _MORPH_METHODS[method])
            continue
        if method == "drop_column":
            for name in _str_args(node):
                columns.pop(name, None)
            continue
        if method == "drop_morphs":
            base = _const_str_arg(node, 0)
            if base is not None:
                columns.pop(f"{base}_type", None)
                columns.pop(f"{base}_id", None)
            continue
        if method in _DROP_IMPLICIT:
            for name in _DROP_IMPLICIT[method]:
                columns.pop(name, None)
            continue
        if method == "rename_column":
            old = _const_str_arg(node, 0)
            new = _const_str_arg(node, 1)
            if old is None or new is None:
                continue
            previous = columns.pop(old, None)
            _add(new, previous.type if previous else "")


def discover_model_tables(root: Path) -> dict[str, TableInfo]:
    """Tables implied by ``app/models``: declared ``table`` or the plural of the class."""
    from almasix.orm.inflector import table_name as derive_table_name

    tables: dict[str, TableInfo] = {}
    base = root / "app" / "models"
    if not base.is_dir():
        return tables
    for path in sorted(base.rglob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):  # pragma: no cover - unreadable / invalid
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or not _is_model(node):
                continue
            declared = _class_string(node, "table")
            name = declared or derive_table_name(node.name)
            columns: dict[str, ColumnInfo] = {}
            for column, line in _model_columns(node):
                columns[column] = ColumnInfo(
                    name=column,
                    table=name,
                    type="",
                    source="model",
                    path=path.resolve(),
                    line=line,
                )
            tables[name] = TableInfo(
                name=name,
                columns=columns,
                source="model",
                path=path.resolve(),
                line=node.lineno - 1,
                model=node.name,
            )
    return tables


def merge_tables(*sources: dict[str, TableInfo]) -> dict[str, TableInfo]:
    """Later sources win per column, so live schema can correct a static read."""
    merged: dict[str, TableInfo] = {}
    for source in sources:
        for name, table in source.items():
            existing = merged.get(name)
            if existing is None:
                merged[name] = table
                continue
            columns = dict(existing.columns)
            columns.update(table.columns)
            merged[name] = replace(
                existing,
                columns=columns,
                source=table.source,
                path=table.path or existing.path,
                line=table.line or existing.line,
                model=existing.model or table.model,
            )
    return merged


def live_schema_enabled() -> bool:
    """Live inspection is opt-in via ``ALMASIX_LSP_DB_SCHEMA=1``.

    Off by default on purpose: indexing runs on every save, and a language
    server that dials a remote database on each keystroke is a hang waiting to
    happen.
    """
    return os.environ.get("ALMASIX_LSP_DB_SCHEMA", "").strip().lower() in {"1", "true", "yes", "on"}


def discover_live_schema(
    *,
    connection: str | None = None,
    timeout: float = 2.0,
) -> dict[str, TableInfo]:
    """Read tables and columns from a configured connection, or ``{}`` on any trouble."""
    try:
        return asyncio.run(_read_live_schema(connection=connection, timeout=timeout))
    except Exception:
        return {}


async def _read_live_schema(
    *,
    connection: str | None,
    timeout: float,
) -> dict[str, TableInfo]:
    from almasix.orm.schema import Schema

    async def _read() -> dict[str, TableInfo]:
        tables: dict[str, TableInfo] = {}
        for name in await Schema.table_names(connection):
            columns: dict[str, ColumnInfo] = {}
            for column in await Schema.columns(name, connection):
                column_name = str(column.get("name", ""))
                if not column_name:
                    continue
                columns[column_name] = ColumnInfo(
                    name=column_name,
                    table=name,
                    type=str(column.get("type", "")),
                    source="live",
                )
            tables[name] = TableInfo(name=name, columns=columns, source="live")
        return tables

    return await asyncio.wait_for(_read(), timeout=timeout)


def _up_method(tree: ast.AST) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "up":
            return node
    return None


def _resolve_callback(callback: ast.AST, callables: dict[str, ast.AST]) -> ast.AST | None:
    """A lambda as written, or the body behind ``self.users`` / ``users``."""
    if isinstance(callback, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
        return callback
    if isinstance(callback, ast.Attribute):
        return callables.get(callback.attr)
    if isinstance(callback, ast.Name):
        return callables.get(callback.id)
    return None


def _callback_param(callback: ast.AST) -> str | None:
    args = getattr(callback, "args", None)
    positional = list(getattr(args, "args", []) or [])
    if positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    return positional[0].arg if positional else None


def _is_model(node: ast.ClassDef) -> bool:
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id == "Model":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "Model":
            return True
    return False


def _class_string(node: ast.ClassDef, name: str) -> str | None:
    for stmt in node.body:
        targets = (
            stmt.targets
            if isinstance(stmt, ast.Assign)
            else [stmt.target]
            if isinstance(stmt, ast.AnnAssign)
            else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = getattr(stmt, "value", None)
                if value is not None:
                    return _const_str(value)
    return None


def _model_columns(node: ast.ClassDef) -> list[tuple[str, int]]:
    """Column names a model admits to: ``fillable`` entries plus ``casts`` keys."""
    out: list[tuple[str, int]] = []
    for stmt in node.body:
        targets = (
            stmt.targets
            if isinstance(stmt, ast.Assign)
            else [stmt.target]
            if isinstance(stmt, ast.AnnAssign)
            else []
        )
        names = {t.id for t in targets if isinstance(t, ast.Name)}
        value = getattr(stmt, "value", None)
        if value is None:
            continue
        if names & {"fillable", "guarded", "hidden"} and isinstance(
            value, (ast.Tuple, ast.List, ast.Set)
        ):
            if "fillable" not in names:
                continue
            for element in value.elts:
                text = _const_str(element)
                if text and text != "*":
                    out.append((text, getattr(element, "lineno", stmt.lineno) - 1))
        elif "casts" in names and isinstance(value, ast.Dict):
            for key in value.keys:
                text = _const_str(key) if key is not None else None
                if text:
                    out.append((text, getattr(key, "lineno", stmt.lineno) - 1))
    return out


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _const_str_arg(call: ast.Call, position: int) -> str | None:
    if len(call.args) <= position:
        return None
    return _const_str(call.args[position])


def _str_args(call: ast.Call) -> list[str]:
    """Strings in the first argument, whether scalar or a list/tuple."""
    if not call.args:
        return []
    first = call.args[0]
    if isinstance(first, (ast.List, ast.Tuple, ast.Set)):
        return [text for text in (_const_str(e) for e in first.elts) if text]
    text = _const_str(first)
    return [text] if text else []
