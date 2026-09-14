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

#: Framework / convention option sets that are not always listed as config dicts.
KNOWN_ENV_OPTIONS: dict[str, tuple[str, ...]] = {
    "APP_ENV": ("local", "production", "testing", "staging", "development"),
    "APP_DEBUG": ("true", "false", "1", "0"),
    "SESSION_DRIVER": ("cookie", "file", "database", "redis"),
    "SESSION_SECURE_COOKIE": ("true", "false", "1", "0"),
    "HASH_DRIVER": ("bcrypt", "argon2", "argon2id", "argon"),
    "LOG_LEVEL": (
        "debug",
        "info",
        "notice",
        "warning",
        "error",
        "critical",
        "alert",
        "emergency",
    ),
    # Laravel-style alias; Almasix progress uses QUEUE_CONNECTION.
    "QUEUE_DRIVER": ("sync", "database", "redis", "beanstalkd", "sqs", "null"),
    "CACHE_DRIVER": ("array", "file", "database", "redis", "memcached", "null"),
    "MAIL_ENCRYPTION": ("tls", "ssl", "null", ""),
    "SCOUT_DRIVER": ("database", "meilisearch", "algolia", "collection", "null"),
}

#: Env keys whose values are connection/store/mailer/… names from config slices.
_SLICE_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "queues": ("QUEUE_CONNECTION", "QUEUE_DRIVER"),
    "caches": ("CACHE_STORE", "CACHE_LIMITER_STORE", "CACHE_DRIVER"),
    "mailers": ("MAIL_MAILER",),
    "disks": ("FILESYSTEM_DISK",),
    "database": ("DB_CONNECTION",),
    "logging": ("LOG_CHANNEL", "LOG_STACK"),
    "broadcasting": ("BROADCAST_CONNECTION", "BROADCAST_DRIVER"),
    "auth_guards": ("AUTH_GUARD",),
    "auth_passwords": ("AUTH_PASSWORD_BROKER",),
    "concurrency": ("CONCURRENCY_DRIVER",),
    "redis": (
        "REDIS_CLIENT",
        "REDIS_QUEUE_CONNECTION",
        "REDIS_CACHE_CONNECTION",
        "BROADCAST_REDIS_CONNECTION",
        "SESSION_CONNECTION",
    ),
    "scout": ("SCOUT_DRIVER",),
    "hash": ("HASH_DRIVER",),
}

#: Sibling dict field names that hold named options next to an env()-backed default.
_OPTION_DICT_KEYS = frozenset(
    {
        "connections",
        "stores",
        "mailers",
        "disks",
        "channels",
        "guards",
        "passwords",
        "drivers",
        "providers",
    }
)


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


def discover_env_options(
    root: Path,
    *,
    config_keys: tuple[str, ...] | list[str] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Map env keys → allowed / suggested values (drivers, stores, connections, …).

    Sources, merged in order (later additions fill gaps, do not replace):

    1. Framework / convention tables (:data:`KNOWN_ENV_OPTIONS`)
    2. Config-slice children (``queue.connections.*`` → ``QUEUE_CONNECTION``, …)
    3. AST: ``env("X")`` next to a sibling ``connections`` / ``stores`` / … dict
    """
    options: dict[str, set[str]] = {key: set(vals) for key, vals in KNOWN_ENV_OPTIONS.items()}

    keys = tuple(config_keys) if config_keys is not None else ()
    if not keys:
        # Static walk still works without a booted app when callers only pass root.
        keys = ()
    slices = _config_option_slices(keys)
    for slice_name, names in slices.items():
        if not names:
            continue
        for env_key in _SLICE_ENV_KEYS.get(slice_name, ()):
            options.setdefault(env_key, set()).update(names)

    for env_key, names in _discover_env_options_from_ast(root).items():
        options.setdefault(env_key, set()).update(names)

    return {key: tuple(sorted(vals)) for key, vals in sorted(options.items()) if vals}


def options_for_env_key(env_options: dict[str, tuple[str, ...]], key: str) -> tuple[str, ...]:
    """Lookup helpers including ``QUEUE_DRIVER`` ↔ ``QUEUE_CONNECTION`` aliases."""
    if key in env_options:
        return env_options[key]
    aliases = {
        "QUEUE_DRIVER": "QUEUE_CONNECTION",
        "QUEUE_CONNECTION": "QUEUE_DRIVER",
        "CACHE_DRIVER": "CACHE_STORE",
        "CACHE_STORE": "CACHE_DRIVER",
        "BROADCAST_DRIVER": "BROADCAST_CONNECTION",
        "BROADCAST_CONNECTION": "BROADCAST_DRIVER",
    }
    alt = aliases.get(key)
    if alt and alt in env_options:
        return env_options[alt]
    return ()


def _config_option_slices(config_keys: tuple[str, ...]) -> dict[str, list[str]]:
    """Named option buckets derived from dotted config keys."""

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
        "scout": children("scout"),
        "hash": children("hashing.drivers"),
    }


def _discover_env_options_from_ast(root: Path) -> dict[str, set[str]]:
    """When ``default``/``driver`` is ``env("KEY")`` beside a named-options dict."""
    found: dict[str, set[str]] = {}
    for path in _iter_config_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for dict_node in _module_config_dicts(tree):
            _collect_env_options_from_dict(dict_node, found)
    return found


def _module_config_dicts(tree: ast.Module) -> list[ast.Dict]:
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
    return found


def _collect_env_options_from_dict(node: ast.Dict, found: dict[str, set[str]]) -> None:
    string_keys: dict[str, ast.AST] = {}
    for key, value in zip(node.keys, node.values, strict=False):
        if key is None:
            continue
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            string_keys[key.value] = value

    option_names: set[str] = set()
    for field in _OPTION_DICT_KEYS:
        sibling = string_keys.get(field)
        if isinstance(sibling, ast.Dict):
            for nested_key, _ in zip(sibling.keys, sibling.values, strict=False):
                if nested_key is None:
                    continue
                if isinstance(nested_key, ast.Constant) and isinstance(nested_key.value, str):
                    option_names.add(nested_key.value)

    if option_names:
        for field in ("default", "driver"):
            value = string_keys.get(field)
            env_key = _env_key_from_value(value)
            if env_key:
                found.setdefault(env_key, set()).update(option_names)

    for value in string_keys.values():
        if isinstance(value, ast.Dict):
            _collect_env_options_from_dict(value, found)


def _env_key_from_value(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    # env("KEY", …) or bool(env(...)) / int(env(...))
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "env" and node.args:
            return _const_str(node.args[0])
        if isinstance(func, ast.Attribute) and func.attr == "env" and node.args:
            return _const_str(node.args[0])
        if isinstance(func, ast.Name) and func.id in {"bool", "int", "str", "float"} and node.args:
            return _env_key_from_value(node.args[0])
    return None


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
