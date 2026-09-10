"""Application symbol index for the Almasix language server.

Boots the application the same way Smith / ``bootstrap.app`` does, then
collects views, named routes, config keys, models, translation keys, and
middleware aliases.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from almasix.lsp.env_context import EnvVarInfo, discover_env_keys
from almasix.lsp.schema_context import (
    TableInfo,
    discover_live_schema,
    discover_migration_schema,
    discover_model_tables,
    live_schema_enabled,
    merge_tables,
)
from almasix.lsp.view_context import (
    ViewVarInfo,
    auth_shared_vars,
    builtin_helpers,
    discover_composer_keys,
    discover_view_data_keys,
    discover_vite_entries,
)


@dataclass(frozen=True)
class RouteInfo:
    """One named route as the router knows it, plus best-effort source location."""

    name: str
    uri: str
    methods: tuple[str, ...]
    path: Path | None = None
    line: int = 0  # 0-based


@dataclass
class AppIndex:
    """Symbols discovered by booting an Almasix application."""

    base_path: Path
    views: dict[str, Path] = field(default_factory=dict)
    routes: dict[str, RouteInfo] = field(default_factory=dict)
    config_keys: tuple[str, ...] = ()
    config_files: dict[str, Path] = field(default_factory=dict)  # stem → path
    models: dict[str, Path] = field(default_factory=dict)
    translation_keys: tuple[str, ...] = ()
    has_lang: bool = False
    middleware_aliases: tuple[str, ...] = ()
    error: str | None = None
    # Prism template variables: view() data keys + helpers + composers.
    view_data: dict[str, dict[str, ViewVarInfo]] = field(default_factory=dict)
    view_helpers: tuple[ViewVarInfo, ...] = ()
    view_shared: dict[str, ViewVarInfo] = field(default_factory=dict)
    vite_entries: dict[str, Path] = field(default_factory=dict)
    #: ``.env`` / ``.env.*`` declarations plus keys only read via ``env()``.
    env_keys: dict[str, EnvVarInfo] = field(default_factory=dict)
    #: Tables and columns from migrations + models (+ a live connection when enabled).
    tables: dict[str, TableInfo] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


def find_app_root(start: Path | None = None) -> Path | None:
    """Locate an Almasix app root (directory with ``bootstrap/app.py``).

    Walks upward from ``start``, then does a shallow downward search so opening
    the framework monorepo still resolves ``examples/progress`` (or another
    nested demo app) instead of indexing the whole tree.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "bootstrap" / "app.py").is_file():
            return candidate
    return _find_nested_app_root(current)


def _find_nested_app_root(root: Path) -> Path | None:
    """Prefer known demo apps, then ``examples/*``, then one-level children."""
    preferred = (
        root / "examples" / "progress",
        root / "examples" / "web",
        root / "examples" / "deploy",
    )
    for candidate in preferred:
        if (candidate / "bootstrap" / "app.py").is_file():
            return candidate.resolve()
    examples = root / "examples"
    if examples.is_dir():
        try:
            children = sorted(examples.iterdir())
        except OSError:  # pragma: no cover
            children = []
        for child in children:
            if child.is_dir() and (child / "bootstrap" / "app.py").is_file():
                return child.resolve()
    try:
        siblings = sorted(root.iterdir())
    except OSError:  # pragma: no cover
        return None
    for child in siblings:
        if child.is_dir() and (child / "bootstrap" / "app.py").is_file():
            return child.resolve()
    return None


def flatten_config(data: dict[str, Any], prefix: str = "") -> list[str]:
    """Turn nested config dicts into dotted keys (``app.name``, …)."""
    keys: list[str] = []
    for name, value in data.items():
        if not isinstance(name, str) or name.startswith("_"):
            continue
        dotted = f"{prefix}.{name}" if prefix else name
        keys.append(dotted)
        if isinstance(value, dict):
            keys.extend(flatten_config(value, dotted))
    return keys


def discover_views(views_root: Path, *, extension: str = ".prism.html") -> dict[str, Path]:
    """Map dotted view names to template paths under ``resources/views``."""
    found: dict[str, Path] = {}
    if not views_root.is_dir():
        return found
    root = views_root.resolve()
    for path in sorted(root.rglob(f"*{extension}")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        name = _view_name_from_path(relative, extension)
        found[name] = path.resolve()
    return found


def _view_name_from_path(relative: Path, extension: str) -> str:
    text = str(relative).replace("\\", "/")
    if text.endswith(extension):
        text = text[: -len(extension)]
    return text.replace("/", ".")


def discover_models(models_root: Path) -> dict[str, Path]:
    """Map model module stems to their files under ``app/models``."""
    found: dict[str, Path] = {}
    if not models_root.is_dir():
        return found
    for path in sorted(models_root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        found[path.stem] = path.resolve()
    return found


def discover_config_files(config_root: Path) -> dict[str, Path]:
    """Map config file stems to paths (``app`` → ``config/app.py``)."""
    found: dict[str, Path] = {}
    if not config_root.is_dir():
        return found
    for path in sorted(config_root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        found[path.stem] = path.resolve()
    return found


_ROUTE_NAME_RE = re.compile(r"""(?:\.name\(\s*|name\s*=\s*)(?P<q>['"])(?P<name>[^'"]+)(?P=q)""")


def discover_route_locations(routes_dir: Path) -> dict[str, tuple[Path, int]]:
    """Best-effort map of route name → (file, 0-based line) from ``routes/*.py``."""
    found: dict[str, tuple[Path, int]] = {}
    if not routes_dir.is_dir():
        return found
    for path in sorted(routes_dir.glob("*.py")):
        if path.name.startswith("_") or path.name in {"console.py", "channels.py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        for match in _ROUTE_NAME_RE.finditer(text):
            name = match.group("name")
            line = text.count("\n", 0, match.start("name"))
            found[name] = (path.resolve(), line)
    return found


def fallback_route_file(routes_dir: Path, uri: str = "") -> Path | None:
    """Prefer ``routes/web.py`` / ``routes/api.py`` when a name has no source hit."""
    if not routes_dir.is_dir():
        return None
    if uri.startswith("/api") or uri.startswith("api"):
        api = routes_dir / "api.py"
        if api.is_file():
            return api.resolve()
    web = routes_dir / "web.py"
    if web.is_file():
        return web.resolve()
    api = routes_dir / "api.py"
    if api.is_file():
        return api.resolve()
    for path in sorted(routes_dir.glob("*.py")):
        if path.name.startswith("_") or path.name in {"console.py", "channels.py"}:
            continue
        return path.resolve()
    return None


def discover_translation_keys(lang_root: Path) -> tuple[str, ...]:
    """Flatten ``lang/`` catalogs into dotted / JSON keys (best-effort)."""
    if not lang_root.is_dir():
        return ()
    keys: set[str] = set()
    for path in sorted(lang_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith(".") or "__pycache__" in path.parts:
            continue
        if path.suffix == ".json":
            keys.update(_json_translation_keys(path))
        elif path.suffix == ".py":
            keys.update(_py_translation_keys(path, lang_root))
        elif path.suffix == ".php":
            keys.update(_php_translation_keys(path, lang_root))
    return tuple(sorted(keys))


def _json_translation_keys(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {str(key) for key in data}


def _py_translation_keys(path: Path, lang_root: Path) -> set[str]:
    data = _load_py_dict(path)
    if not data:
        return set()
    try:
        relative = path.relative_to(lang_root)
    except ValueError:  # pragma: no cover
        return set()
    parts = list(relative.parts)
    # lang/en/messages.py → group ``messages``; skip locale segment.
    if len(parts) < 2:
        return set()
    group = Path(parts[-1]).stem
    return {f"{group}.{key}" for key in _flatten_dict_keys(data)}


def _php_translation_keys(path: Path, lang_root: Path) -> set[str]:
    """Pull quoted keys from a PHP return-array file (best-effort)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        return set()
    try:
        relative = path.relative_to(lang_root)
    except ValueError:  # pragma: no cover
        return set()
    parts = list(relative.parts)
    if len(parts) < 2:
        return set()
    group = Path(parts[-1]).stem
    keys = re.findall(r"""['"]([^'"]+)['"]\s*=>""", text)
    return {f"{group}.{key}" for key in keys}


def _flatten_dict_keys(data: dict[str, Any], prefix: str = "") -> list[str]:
    out: list[str] = []
    for name, value in data.items():
        if not isinstance(name, str):
            continue
        dotted = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            out.extend(_flatten_dict_keys(value, dotted))
        else:
            out.append(dotted)
    return out


def _load_py_dict(path: Path) -> dict[str, Any]:
    module_name = f"almasix_lsp_lang_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - stdlib always returns a loader
        return {}
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        return {}
    finally:
        sys.modules.pop(module_name, None)
    for attr in ("translations", "messages", "config", "lang", path.stem):
        candidate = getattr(module, attr, None)
        if isinstance(candidate, dict):
            return candidate
    return {}


def config_file_for_key(index: AppIndex, key: str) -> Path | None:
    """Resolve ``config("app.name")`` → ``config/app.py``."""
    if not key:
        return None
    stem = key.split(".", 1)[0]
    return index.config_files.get(stem)


def view_path_for_name(base_path: Path, name: str, *, extension: str = ".prism.html") -> Path:
    """Filesystem path a view name would occupy under ``resources/views``."""
    relative = name.replace(".", "/") + extension
    return (base_path / "resources" / "views" / relative).resolve()


def _boot_application(root: Path) -> Any:
    """Prefer ``bootstrap.app.application`` so middleware aliases match HTTP."""
    root_s = str(root.resolve())
    if root_s not in sys.path:
        sys.path.insert(0, root_s)

    # Drop a stale bootstrap from another app root.
    for key in list(sys.modules):
        if key == "bootstrap" or key.startswith("bootstrap."):
            del sys.modules[key]

    try:
        module = importlib.import_module("bootstrap.app")
        app = getattr(module, "application", None)
        if app is not None:
            return app
    except Exception:
        pass

    from almasix.framework.application import Application

    app = Application(root)
    app.bootstrap()
    return app


def build_index(base_path: Path | str | None = None) -> AppIndex:
    """Boot the app at ``base_path`` (or discover it) and collect symbols."""
    root = Path(base_path).resolve() if base_path else find_app_root()
    if root is None:
        return AppIndex(
            base_path=Path.cwd().resolve(),
            error="No Almasix application found (missing bootstrap/app.py).",
        )

    views = discover_views(root / "resources" / "views")
    models = discover_models(root / "app" / "models")
    config_files = discover_config_files(root / "config")
    lang_root = root / "lang"
    has_lang = lang_root.is_dir()
    translation_keys = discover_translation_keys(lang_root) if has_lang else ()
    route_locations = discover_route_locations(root / "routes")
    routes_dir = root / "routes"
    view_data = discover_view_data_keys(root)
    helpers = tuple(builtin_helpers())
    shared = {info.name: info for info in auth_shared_vars()}
    shared.update(discover_composer_keys(root))
    vite_entries = discover_vite_entries(root)
    env_keys = discover_env_keys(root)
    # Migrations describe a table more precisely than a model's `fillable`, so
    # they are merged last of the two static sources.
    static_tables = merge_tables(discover_model_tables(root), discover_migration_schema(root))

    try:
        app = _boot_application(root)
    except Exception as exc:
        return AppIndex(
            base_path=root,
            views=views,
            models=models,
            config_files=config_files,
            translation_keys=translation_keys,
            has_lang=has_lang,
            view_data=view_data,
            view_helpers=helpers,
            view_shared=shared,
            vite_entries=vite_entries,
            env_keys=env_keys,
            tables=static_tables,
            error=f"Application failed to boot: {type(exc).__name__}: {exc}",
        )

    from almasix.http.middleware import FRAMEWORK_ALIASES

    aliases = {
        **FRAMEWORK_ALIASES,
        **dict(getattr(app, "config", None) and app.config.get("http.middleware_aliases") or {}),
    }
    named = app.router.named_routes()
    routes: dict[str, RouteInfo] = {}
    for name, route in named.items():
        loc = route_locations.get(name)
        if loc is not None:
            path, line = loc
        else:
            path = fallback_route_file(routes_dir, route.uri)
            line = 0
        routes[name] = RouteInfo(
            name=name,
            uri=route.uri,
            methods=tuple(route.methods),
            path=path,
            line=line,
        )

    config_keys = tuple(sorted(flatten_config(app.config.all())))
    # The app is booted, so a connection exists — but only reach for it when
    # asked; see `live_schema_enabled`.
    tables = (
        merge_tables(static_tables, discover_live_schema())
        if live_schema_enabled()
        else static_tables
    )
    return AppIndex(
        base_path=root,
        views=views,
        routes=routes,
        config_keys=config_keys,
        config_files=config_files,
        models=models,
        translation_keys=translation_keys,
        has_lang=has_lang,
        middleware_aliases=tuple(sorted(aliases)),
        view_data=view_data,
        view_helpers=helpers,
        view_shared=shared,
        vite_entries=vite_entries,
        env_keys=env_keys,
        tables=tables,
    )
