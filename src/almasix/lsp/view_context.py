"""Index Prism view context: ``view()`` data keys, helpers, and shared composers."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

# Scan roots under the app for ``view("…", {…})`` and composer key writes.
_SCAN_DIRS = (
    "app",
    "routes",
    "bootstrap",
    "database",
)

# Helper name → (package-relative path under almasix/, def needle).
_HELPER_DEFS: tuple[tuple[str, str, str, str], ...] = (
    ("config", "config/__init__.py", "def config", "Config helper"),
    ("url", "routing/url.py", "def url", "Generate a URL for a path"),
    ("asset", "routing/url.py", "def asset", "Public asset URL"),
    ("route", "routing/url.py", "def route", "Named route URL"),
    ("signed_route", "routing/url.py", "def signed_route", "Signed named route URL"),
    ("action", "routing/url.py", "def action", "Controller action URL"),
    ("secure_url", "routing/url.py", "def secure_url", "HTTPS URL"),
    ("secure_asset", "routing/url.py", "def secure_asset", "HTTPS asset URL"),
    ("route_is", "routing/router.py", "def is_", "Whether the current route matches a pattern"),
    ("current_route_name", "routing/router.py", "def current_route_name", "Current named route"),
    ("vite", "prism/vite.py", "def vite", "Vite entry tags"),
    (
        "vite_react_refresh",
        "prism/vite.py",
        "def vite_react_refresh",
        "Vite React refresh preamble",
    ),
    ("e", "prism/escape.py", "def e", "HTML escape"),
    ("csrf_field", "prism/helpers.py", "def csrf_field", "CSRF hidden input HTML"),
    ("method_field", "prism/helpers.py", "def method_field", "Method spoof hidden input"),
    ("old", "session/helpers.py", "def old", "Old input from the session"),
    ("csp_nonce", "http/security.py", "def csp_nonce", "Content-Security-Policy nonce"),
    ("__", "translation/helpers.py", "def __", "Translate a key"),
    ("trans", "translation/helpers.py", "def trans", "Alias for __"),
    ("trans_choice", "translation/helpers.py", "def trans_choice", "Pluralized translation"),
)


@dataclass(frozen=True)
class ViewVarInfo:
    """One name available inside a Prism template."""

    name: str
    kind: str  # "data" | "helper" | "shared"
    detail: str
    path: Path | None = None
    line: int = 0  # 0-based
    view: str | None = None  # logical view name when kind == "data"


def _almasix_src() -> Path:
    """``…/src/almasix`` when running from a checkout or installed package."""
    import almasix

    return Path(almasix.__file__).resolve().parent


def builtin_helpers() -> list[ViewVarInfo]:
    """Names injected by ``Engine._inject_helpers`` (always available)."""
    root = _almasix_src()
    out: list[ViewVarInfo] = []
    for name, rel, needle, detail in _HELPER_DEFS:
        path = root / rel
        # Fallbacks when package layout differs slightly.
        if not path.is_file():
            for alt in (
                root / rel.replace("__init__.py", "helpers.py"),
                root / "prism" / "engine.py",
            ):
                if alt.is_file():
                    path = alt
                    break
        line = _line_containing(path, needle) or 0
        out.append(
            ViewVarInfo(
                name=name,
                kind="helper",
                detail=detail,
                path=path if path.is_file() else None,
                line=line,
            )
        )
    return out


def auth_shared_vars() -> list[ViewVarInfo]:
    """Names shared by ``AuthServiceProvider``'s ``composer("*", …)``."""
    provider = _almasix_src() / "auth" / "provider.py"
    line = _line_containing(provider, 'context["csrf_token"]') or 0
    names = (
        ("csrf_token", "CSRF token string (auth composer)"),
        ("auth_user", "Authenticated user or None"),
        ("__authenticated", "Whether a user is logged in"),
        ("version", "Almasix framework version"),
        ("error", "Flash error string"),
        ("errors", "Flash validation errors"),
        ("status", "Flash status string"),
    )
    return [
        ViewVarInfo(
            name=name,
            kind="shared",
            detail=detail,
            path=provider if provider.is_file() else None,
            line=line,
        )
        for name, detail in names
    ]


def discover_vite_entries(root: Path) -> dict[str, Path]:
    """Best-effort Vite entry labels / paths from ``vite.config.*`` and ``resources/js``."""
    found: dict[str, Path] = {}
    for name in ("vite.config.js", "vite.config.ts", "vite.config.mjs"):
        config = root / name
        if not config.is_file():
            continue
        try:
            text = config.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        # input: { app: resolve("resources/js/app.js"), … } or input: ["…"]
        for match in re.finditer(
            r"""(?:['"](?P<label>[^'"]+)['"]\s*:\s*)?"""
            r"""(?:resolve\s*\(\s*)?['"](?P<path>resources/[^'"]+)['"]""",
            text,
        ):
            label = match.group("label") or Path(match.group("path")).stem
            path = (root / match.group("path")).resolve()
            found[label] = path
            found[match.group("path")] = path
            # Also accept bare filename stems commonly passed to vite().
            found[Path(match.group("path")).name] = path
    js_root = root / "resources" / "js"
    if js_root.is_dir():
        for path in sorted(js_root.rglob("*")):
            if path.suffix.lower() not in {".js", ".ts", ".jsx", ".tsx", ".css"}:
                continue
            if not path.is_file():
                continue
            rel = str(path.relative_to(root)).replace("\\", "/")
            found[rel] = path.resolve()
            found[path.name] = path.resolve()
    return found


def _line_containing(path: Path, needle: str) -> int | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover
        return None
    for index, line in enumerate(text.splitlines()):
        if needle in line:
            return index
    return None


def discover_view_data_keys(root: Path) -> dict[str, dict[str, ViewVarInfo]]:
    """Map view name → {key → ViewVarInfo} from ``view("name", {…})`` call sites."""
    result: dict[str, dict[str, ViewVarInfo]] = {}
    for path in _iter_python_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        for view_name, key, line in _extract_view_dict_keys(text):
            bucket = result.setdefault(view_name, {})
            if key in bucket:
                continue
            bucket[key] = ViewVarInfo(
                name=key,
                kind="data",
                detail=f"Passed to view({view_name!r})",
                path=path.resolve(),
                line=line,
                view=view_name,
            )
    return result


def discover_composer_keys(root: Path) -> dict[str, ViewVarInfo]:
    """Best-effort: ``context["key"]`` / ``context.setdefault("key"`` in app code."""
    found: dict[str, ViewVarInfo] = {}
    pattern = re.compile(
        r"""context\s*(?:\[\s*(?P<q>['"])(?P<key>[^'"]+)(?P=q)\s*\]"""
        r"""|\.setdefault\s*\(\s*(?P<q2>['"])(?P<key2>[^'"]+)(?P=q2))"""
    )
    for path in _iter_python_files(root):
        if "site-packages" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        if "composer" not in text and "context[" not in text and "context.setdefault" not in text:
            continue
        if "composer" not in text and "def share" not in text:
            continue
        for match in pattern.finditer(text):
            key = match.group("key") or match.group("key2")
            if not key or key.startswith("_"):
                continue
            if key in found:
                continue
            line = text.count("\n", 0, match.start())
            found[key] = ViewVarInfo(
                name=key,
                kind="shared",
                detail="Shared via view composer (best-effort)",
                path=path.resolve(),
                line=line,
            )
    return found


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    skip = {".venv", "__pycache__", "node_modules", ".git", "vendor", "storage"}
    for relative in _SCAN_DIRS:
        base = root / relative
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in skip or part.startswith(".") for part in path.parts):
                continue
            if path.name.startswith("_") and path.name != "__init__.py":
                continue
            files.append(path)
    return files


def _extract_view_dict_keys(source: str) -> list[tuple[str, str, int]]:
    """Return ``(view_name, key, line)`` from ``view(...)`` calls with a dict arg."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_view_dict_keys_regex(source)

    out: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_view_call(node.func):
            continue
        view_name = _string_arg(node, 0, "name")
        if view_name is None:
            continue
        data_node = _data_arg(node)
        if data_node is None:
            continue
        for key, line in _dict_keys(data_node):
            out.append((view_name, key, line))
    return out


def _is_view_call(func: ast.AST) -> bool:
    if isinstance(func, ast.Name) and func.id == "view":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "view":
        return True
    return False


def _string_arg(call: ast.Call, pos: int, keyword: str) -> str | None:
    if len(call.args) > pos:
        return _const_str(call.args[pos])
    for kw in call.keywords:
        if kw.arg == keyword:
            return _const_str(kw.value)
    return None


def _data_arg(call: ast.Call) -> ast.AST | None:
    if len(call.args) >= 2:
        return call.args[1]
    for kw in call.keywords:
        if kw.arg in {"data", "context"}:
            return kw.value
    return None


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _dict_keys(node: ast.AST) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    if isinstance(node, ast.Dict):
        for key_node in node.keys:
            if key_node is None:
                continue
            name = _const_str(key_node)
            if name is None:
                continue
            line = getattr(key_node, "lineno", 1) - 1
            keys.append((name, line))
        return keys
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        for kw in node.keywords:
            if kw.arg is None:
                continue
            line = getattr(kw.value, "lineno", getattr(node, "lineno", 1)) - 1
            keys.append((kw.arg, line))
    return keys


_VIEW_CALL_RE = re.compile(
    r"""\bview\s*\(\s*(?P<q>['"])(?P<name>[^'"]+)(?P=q)\s*,\s*\{""",
)


def _extract_view_dict_keys_regex(source: str) -> list[tuple[str, str, int]]:
    """Fallback when the module does not parse as Python."""
    out: list[tuple[str, str, int]] = []
    for match in _VIEW_CALL_RE.finditer(source):
        view_name = match.group("name")
        window = source[match.end() - 1 : match.end() + 800]
        close = window.find("})")
        if close < 0:
            close = window.find("}")
        body = window[1:close] if close >= 0 else window[1:]
        base_line = source.count("\n", 0, match.start())
        for key_match in re.finditer(
            r"""(?P<q>['"])(?P<key>[A-Za-z_][\w]*)(?P=q)\s*:""",
            body,
        ):
            line = base_line + body.count("\n", 0, key_match.start())
            out.append((view_name, key_match.group("key"), line))
    return out


def view_name_for_template(index_views: dict[str, Path], template_path: Path) -> str | None:
    """Resolve a ``.prism.html`` path to its dotted view name."""
    resolved = template_path.resolve()
    for name, path in index_views.items():
        if path.resolve() == resolved:
            return name
    return None


def merge_vars_for_view(
    view_name: str | None,
    *,
    view_data: dict[str, dict[str, ViewVarInfo]],
    helpers: list[ViewVarInfo],
    shared: dict[str, ViewVarInfo],
) -> dict[str, ViewVarInfo]:
    """Data keys override shared/helpers for the same name."""
    merged: dict[str, ViewVarInfo] = {}
    for info in helpers:
        merged[info.name] = info
    for info in shared.values():
        merged[info.name] = info
    if view_name and view_name in view_data:
        for name, info in view_data[view_name].items():
            merged[name] = info
    return merged
