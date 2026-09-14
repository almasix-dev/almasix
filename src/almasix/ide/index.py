"""Almasix IDE symbol index — JSON dump for JetBrains (and other native tools).

Builds on :func:`almasix.lsp.index.build_index` and adds surfaces the language
server baseline still defers: gates, components, relations, casts, disks /
queues / caches / mailers, validation rules, Smith commands, Inertia pages.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from almasix.lsp.directives import PRISM_DIRECTIVES
from almasix.lsp.index import AppIndex, build_index, discover_views
from almasix.lsp.schema_context import TableInfo

#: Common Articulate cast type strings (string-form casts).
KNOWN_CASTS: tuple[str, ...] = (
    "int",
    "integer",
    "real",
    "float",
    "double",
    "decimal",
    "string",
    "bool",
    "boolean",
    "object",
    "array",
    "json",
    "dict",
    "collection",
    "date",
    "datetime",
    "immutable_date",
    "immutable_datetime",
    "timestamp",
    "encrypted",
    "encrypted:array",
    "encrypted:collection",
    "encrypted:json",
    "encrypted:object",
    "hashed",
    "AsEnumCollection",
)

_RELATION_CALLS = frozenset(
    {
        "has_one",
        "has_many",
        "belongs_to",
        "belongs_to_many",
        "has_many_through",
        "has_one_through",
        "morph_to",
        "morph_one",
        "morph_many",
        "morph_to_many",
        "morphed_by_many",
    }
)

_POLICY_METHOD_SKIP = frozenset({"__init__", "before", "after"})


def index_to_dict(index: AppIndex, *, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize an :class:`AppIndex` (plus optional extras) to JSON-ready dict."""
    payload: dict[str, Any] = {
        "base_path": str(index.base_path),
        "ok": index.ok,
        "error": index.error,
        "views": {name: str(path) for name, path in sorted(index.views.items())},
        "routes": {
            name: {
                "name": info.name,
                "uri": info.uri,
                "methods": list(info.methods),
                "path": str(info.path) if info.path else None,
                "line": info.line,
            }
            for name, info in sorted(index.routes.items())
        },
        "config_keys": list(index.config_keys),
        "config_files": {stem: str(path) for stem, path in sorted(index.config_files.items())},
        "config_locations": discover_config_key_locations(index.config_files),
        "models": {stem: str(path) for stem, path in sorted(index.models.items())},
        "controllers": {name: str(path) for name, path in sorted(index.controllers.items())},
        "controller_actions": _controller_actions(index),
        "translation_keys": list(index.translation_keys),
        "has_lang": index.has_lang,
        "middleware_aliases": list(index.middleware_aliases),
        "view_data": {
            view: {var: _dataclass_to_jsonable(info) for var, info in sorted(vars_.items())}
            for view, vars_ in sorted(index.view_data.items())
        },
        "view_helpers": [_dataclass_to_jsonable(h) for h in index.view_helpers],
        "view_shared": {
            name: _dataclass_to_jsonable(info) for name, info in sorted(index.view_shared.items())
        },
        "vite_entries": {name: str(path) for name, path in sorted(index.vite_entries.items())},
        "env_keys": {
            name: _dataclass_to_jsonable(info) for name, info in sorted(index.env_keys.items())
        },
        "env_options": {key: list(vals) for key, vals in sorted(index.env_options.items())},
        "tables": {name: _table_to_dict(table) for name, table in sorted(index.tables.items())},
        "directives": sorted(PRISM_DIRECTIVES),
    }
    if extras:
        payload.update(extras)
    return payload


def build_ide_index(base_path: Path | str | None = None) -> dict[str, Any]:
    """Boot the app, collect the full IDE symbol set, return a JSON-ready dict."""
    index = build_index(base_path)
    extras = discover_extras(index)
    return index_to_dict(index, extras=extras)


def discover_extras(index: AppIndex) -> dict[str, Any]:
    """Surfaces beyond the LSP :class:`AppIndex` baseline."""
    root = index.base_path
    model_meta = discover_model_metadata(index.models)
    components = discover_components(root)
    gates = discover_gates(root, index)
    config_slices = discover_config_slices(index.config_keys)
    inertia = discover_inertia_pages(root)
    smith = discover_smith_commands()
    validation = discover_validation_rules()
    return {
        "model_metadata": model_meta,
        "relations": {model: meta["relations"] for model, meta in model_meta.items()},
        "casts": list(KNOWN_CASTS),
        "components": components,
        "gates": gates,
        "disks": config_slices["disks"],
        "queues": config_slices["queues"],
        "caches": config_slices["caches"],
        "mailers": config_slices["mailers"],
        "inertia_pages": inertia,
        "smith_commands": smith,
        "validation_rules": validation,
    }


def discover_model_metadata(models: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Per-model fillable / casts / relation method names (static AST)."""
    out: dict[str, dict[str, Any]] = {}
    for stem, path in models.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        fillable: list[str] = []
        guarded: list[str] = []
        hidden: list[str] = []
        casts: dict[str, str] = {}
        relations: list[str] = []
        relation_lines: dict[str, int] = {}
        class_name = stem
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            class_name = node.name
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if not isinstance(target, ast.Name):
                            continue
                        if target.id == "fillable":
                            fillable = _string_list(item.value)
                        elif target.id == "guarded":
                            guarded = _string_list(item.value)
                        elif target.id == "hidden":
                            hidden = _string_list(item.value)
                        elif target.id == "casts":
                            casts = _string_dict(item.value)
                if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                    if item.name.startswith("_"):
                        continue
                    if _returns_relation(item):
                        relations.append(item.name)
                        relation_lines[item.name] = max(item.lineno - 1, 0)
        out[class_name] = {
            "module": stem,
            "path": str(path),
            "fillable": fillable,
            "guarded": guarded,
            "hidden": hidden,
            "casts": casts,
            "relations": sorted(set(relations)),
            "relation_lines": relation_lines,
        }
    return out


def discover_components(root: Path) -> dict[str, str]:
    """Prism / class component names → path (Blade-style ``x-…`` names)."""
    found: dict[str, str] = {}
    views = discover_views(root / "resources" / "views" / "components")
    for name, path in views.items():
        # components.alert.banner → alert.banner (x-alert.banner)
        found[name] = str(path)
    # Class components under app/view/components or app/views/components
    for folder in (
        root / "app" / "view" / "components",
        root / "app" / "views" / "components",
        root / "app" / "http" / "components",
    ):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in re.finditer(r"^class\s+([A-Za-z_][\w]*)\s*[:(]", text, re.M):
                cls = match.group(1)
                # AlertBanner → alert-banner
                kebab = re.sub(r"(?<!^)(?=[A-Z])", "-", cls).lower()
                found[kebab] = str(path.resolve())
    return dict(sorted(found.items()))


def discover_gates(root: Path, index: AppIndex) -> list[str]:
    """Gate / policy ability names (boot when possible, else static scan)."""
    abilities: set[str] = set()
    try:
        from almasix.auth.access.facade import Gate

        for name in Gate.abilities().keys():
            if isinstance(name, str):
                abilities.add(name)
    except Exception:
        pass

    policies = root / "app" / "policies"
    if policies.is_dir():
        for path in sorted(policies.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError):
                continue
            for node in tree.body:
                if not isinstance(node, ast.ClassDef):
                    continue
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if item.name.startswith("_") or item.name in _POLICY_METHOD_SKIP:
                            continue
                        abilities.add(item.name)

    # AuthProvider / AuthServiceProvider style Gate.define("…")
    for folder in (root / "app" / "providers", root / "app"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for match in re.finditer(
                r"""(?:Gate\.define|\.define)\(\s*['"]([^'"]+)['"]""",
                text,
            ):
                abilities.add(match.group(1))

    # Common ability from middleware / routes when nothing else registered
    if not abilities and index.middleware_aliases:
        pass
    return sorted(abilities)


def discover_config_slices(config_keys: tuple[str, ...]) -> dict[str, list[str]]:
    """Disk / queue / cache / mailer names derived from dotted config keys."""

    def children(prefix: str) -> list[str]:
        names: set[str] = set()
        needle = prefix + "."
        for key in config_keys:
            if not key.startswith(needle):
                continue
            name = key[len(needle) :].split(".", 1)[0]
            if name and name != "default":
                names.add(name)
        return sorted(names)

    return {
        "disks": children("filesystems.disks"),
        "queues": children("queue.connections"),
        "caches": children("cache.stores"),
        "mailers": children("mail.mailers"),
        "database": children("database.connections"),
        "logging": children("logging.channels"),
        "broadcasting": children("broadcasting.connections"),
        "auth_guards": children("auth.guards"),
        "auth_passwords": children("auth.passwords"),
        "concurrency": children("concurrency.drivers"),
        "redis": children("redis.connections"),
    }


def discover_config_key_locations(config_files: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Map dotted config keys (``app.env``) → ``{path, line}`` via AST of ``config/*.py``.

    Line numbers are 0-based. Nested dict keys under ``config = {…}`` or ``return {…}``
    become ``{stem}.{nested…}``. Missing / dynamic keys are omitted (callers fall back
    to the stem file).
    """
    out: dict[str, dict[str, Any]] = {}
    for stem, path in config_files.items():
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, SyntaxError):
            continue
        resolved = str(path.resolve())
        for dict_node in _config_root_dicts(tree):
            for rel_key, line in _walk_string_dict_keys(dict_node):
                full = f"{stem}.{rel_key}" if rel_key else stem
                out.setdefault(full, {"path": resolved, "line": line})
        # Stem alone → top of file when present as a runtime key
        out.setdefault(stem, {"path": resolved, "line": 0})
    return dict(sorted(out.items()))


def _config_root_dicts(tree: ast.Module) -> list[ast.Dict]:
    """``config = {…}`` assignments and ``return {…}`` dicts in module functions."""
    found: list[ast.Dict] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id in {"config", "CONFIG"}
                    and isinstance(node.value, ast.Dict)
                ):
                    found.append(node.value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in node.body:
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                    found.append(sub.value)
                # ``return { **base, "x": 1 }`` still yields a Dict node
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Call):
                    continue
    return found


def _walk_string_dict_keys(node: ast.Dict, prefix: str = "") -> list[tuple[str, int]]:
    """Flatten nested string-keyed dicts to ``(relative.key, 0-based line)``."""
    out: list[tuple[str, int]] = []
    for key, value in zip(node.keys, node.values, strict=False):
        if key is None:
            continue
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
            continue
        name = f"{prefix}.{key.value}" if prefix else key.value
        line = max(getattr(key, "lineno", 1) - 1, 0)
        out.append((name, line))
        if isinstance(value, ast.Dict):
            out.extend(_walk_string_dict_keys(value, name))
    return out


def discover_inertia_pages(root: Path) -> list[str]:
    """Inertia page names under ``resources/js/Pages`` (dotted / slash)."""
    pages_root = root / "resources" / "js" / "Pages"
    if not pages_root.is_dir():
        pages_root = root / "resources" / "js" / "pages"
    if not pages_root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(pages_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".vue", ".jsx", ".tsx", ".js", ".ts", ".svelte"}:
            continue
        rel = path.relative_to(pages_root).with_suffix("")
        name = str(rel).replace("\\", "/")
        found.append(name)
    return found


def discover_smith_commands() -> list[str]:
    """Framework Smith command names (signature scan; no app boot required)."""
    import importlib
    import inspect
    import pkgutil

    from almasix.console.command import Command

    names: set[str] = set()
    packages = (
        "almasix.console.commands",
        "almasix.ide.commands",
        "almasix.lsp.commands",
    )
    for package_name in packages:
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            continue
        paths = getattr(package, "__path__", None)
        if paths is None:
            continue
        for module_info in pkgutil.walk_packages(paths, prefix=package_name + "."):
            try:
                module = importlib.import_module(module_info.name)
            except Exception:
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if obj is Command or not issubclass(obj, Command):
                    continue
                if not getattr(obj, "signature", None):
                    continue
                try:
                    names.add(obj.name())
                except Exception:
                    continue
    return sorted(names)


def discover_validation_rules() -> list[str]:
    """Built-in validation rule names."""
    try:
        from almasix.validation.rules.registry import LARAVEL_RULES

        return list(LARAVEL_RULES)
    except Exception:
        return []


def dump_index_json(base_path: Path | str | None = None, *, indent: int = 2) -> str:
    """Build the IDE index and return a JSON string."""
    return json.dumps(build_ide_index(base_path), indent=indent, ensure_ascii=False)


def _controller_actions(index: AppIndex) -> dict[str, list[str]]:
    from almasix.lsp.index import controller_methods

    out: dict[str, list[str]] = {}
    for name, path in index.controllers.items():
        out[name] = sorted(controller_methods(path).keys())
    return out


def _table_to_dict(table: TableInfo) -> dict[str, Any]:
    return {
        "name": table.name,
        "source": table.source,
        "path": str(table.path) if table.path else None,
        "line": table.line,
        "model": table.model,
        "detail": getattr(table, "detail", "") or "",
        "columns": {
            col.name: {
                "name": col.name,
                "table": col.table,
                "type": col.type,
                "source": col.source,
                "path": str(col.path) if col.path else None,
                "line": col.line,
            }
            for col in sorted(table.columns.values(), key=lambda c: c.name)
        },
    }


def _dataclass_to_jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        raw = asdict(value)
        return {k: _pathish(v) for k, v in raw.items()}
    return _pathish(value)


def _pathish(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: _pathish(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_pathish(v) for v in value]
    return value


def _string_list(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        out: list[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
        return out
    return []


def _string_dict(node: ast.AST) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}
    out: dict[str, str] = {}
    for key, value in zip(node.keys, node.values, strict=False):
        if key is None:
            continue
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                out[key.value] = value.value
    return out


def _returns_relation(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in _RELATION_CALLS:
                return True
            if isinstance(func, ast.Name) and func.id in _RELATION_CALLS:
                return True
    return False
