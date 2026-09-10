"""Environment variable index for the language server.

Keys come from three places, in decreasing authority: the app's ``.env``, any
``.env.*`` template beside it (``.env.example`` is the convention), and
``env("KEY", default)`` call sites under ``config/``. A key used in config but
absent from every file still completes — that is exactly the key someone
forgot to document.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, replace
from pathlib import Path

#: Key fragments whose values are never echoed back to the editor. Mirrors
#: ``config:show``'s redaction — hover happens over shoulders and in recordings.
_SECRET_HINTS = ("password", "secret", "token", "key", "credential", "private", "salt", "dsn")

_REDACTED = "********"

#: ``KEY=value`` — dotenv allows an optional ``export`` prefix and blank values.
_ENV_LINE_RE = re.compile(r"^\s*(?:export\s+)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=(?P<value>.*)$")

#: ``${OTHER}`` inside a value; python-dotenv expands this form (not bare ``$OTHER``).
ENV_INTERPOLATION_RE = re.compile(r"\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}")

_ENV_FILE_GLOBS = (".env", ".env.*")

#: Never read these: encrypted payloads are noise, backups are stale.
_ENV_FILE_SKIP_SUFFIXES = (".encrypted", ".bak", ".backup", ".save")


@dataclass(frozen=True)
class EnvVarInfo:
    """One environment variable as the app could see it."""

    name: str
    #: ``env`` (declared in ``.env``), ``example`` (a template), ``config`` (used only).
    kind: str
    detail: str
    value: str | None = None
    path: Path | None = None
    line: int = 0
    #: ``config/app.py:16`` style origins for a key read via ``env()``.
    used_by: tuple[str, ...] = ()

    @property
    def declared(self) -> bool:
        return self.kind in {"env", "example"}


def is_secret_key(name: str) -> bool:
    """Whether a variable's value should be hidden from hover / completion."""
    lowered = name.lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def display_value(name: str, value: str | None) -> str | None:
    """The value as it is safe to show in an editor popup."""
    if value is None or value == "":
        return value
    if is_secret_key(name):
        return _REDACTED
    return value


def parse_env_file(path: Path) -> dict[str, tuple[str, int]]:
    """Return ``{KEY: (value, line)}`` for a dotenv file (last assignment wins)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - unreadable file
        return {}
    found: dict[str, tuple[str, int]] = {}
    for number, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENV_LINE_RE.match(raw)
        if match is None:
            continue
        found[match.group("name")] = (_unquote(match.group("value").strip()), number)
    return found


def env_files(root: Path) -> list[Path]:
    """``.env`` first, then ``.env.*`` templates, so declarations win over examples."""
    seen: dict[Path, None] = {}
    for pattern in _ENV_FILE_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            if path.suffix in _ENV_FILE_SKIP_SUFFIXES:
                continue
            seen.setdefault(path.resolve(), None)
    return list(seen)


def discover_env_keys(root: Path) -> dict[str, EnvVarInfo]:
    """Index every environment variable the app declares or reads."""
    found: dict[str, EnvVarInfo] = {}

    for path in env_files(root):
        is_example = path.name != ".env"
        kind = "example" if is_example else "env"
        for name, (value, line) in parse_env_file(path).items():
            existing = found.get(name)
            if existing is not None and existing.kind == "env":
                continue
            found[name] = EnvVarInfo(
                name=name,
                kind=kind,
                detail=f"{'Template' if is_example else 'Set'} in {path.name}",
                value=value,
                path=path,
                line=line,
            )

    for name, origin, default in discover_env_usages(root):
        existing = found.get(name)
        if existing is None:
            found[name] = EnvVarInfo(
                name=name,
                kind="config",
                detail=f"Read by {origin}" + (f" (default: {default})" if default else ""),
                value=None,
                used_by=(origin,),
            )
            continue
        if origin not in existing.used_by:
            found[name] = replace(existing, used_by=(*existing.used_by, origin))
    return found


def discover_env_usages(root: Path) -> list[tuple[str, str, str]]:
    """Return ``(key, "config/app.py:16", default)`` for each ``env()`` call."""
    usages: list[tuple[str, str, str]] = []
    for path in _iter_config_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover - unreadable file
            continue
        relative = _relative(path, root)
        for name, line, default in _extract_env_calls(text):
            usages.append((name, f"{relative}:{line + 1}", default))
    return usages


def _iter_config_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for relative in ("config", "bootstrap"):
        base = root / relative
        if base.is_dir():
            files.extend(sorted(base.rglob("*.py")))
    return files


def _extract_env_calls(source: str) -> list[tuple[str, int, str]]:
    """``(key, line, default)`` for ``env("KEY", default)`` — AST first, regex fallback."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _extract_env_calls_regex(source)

    out: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name_ok = (isinstance(func, ast.Name) and func.id == "env") or (
            isinstance(func, ast.Attribute) and func.attr == "env"
        )
        if not name_ok or not node.args:
            continue
        key = _const_str(node.args[0])
        if key is None:
            continue
        out.append((key, node.lineno - 1, _default_repr(node)))
    return out


_ENV_CALL_RE = re.compile(r"""\benv\s*\(\s*(?P<q>['"])(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?P=q)""")


def _extract_env_calls_regex(source: str) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for match in _ENV_CALL_RE.finditer(source):
        line = source.count("\n", 0, match.start())
        out.append((match.group("name"), line, ""))
    return out


def _default_repr(call: ast.Call) -> str:
    if len(call.args) < 2:
        return ""
    node = call.args[1]
    if isinstance(node, ast.Constant):
        return "" if node.value is None else str(node.value)
    if isinstance(node, ast.Call):  # nested env("OTHER", …)
        return "env(…)"
    return ""


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:  # pragma: no cover - path outside the app
        return path.name


def _unquote(value: str) -> str:
    """Strip a trailing ``# comment`` then matching quotes the way dotenv does."""
    head, hash_sign, _tail = value.partition(" #")
    text = head.strip() if hash_sign else value
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text
