"""Environment helpers (Laravel ``env()`` equivalent)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv as _load_dotenv

T = TypeVar("T")

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def load_environment(base_path: str | Path, filename: str = ".env") -> bool:
    """Load a ``.env`` file from the application base path into ``os.environ``."""
    path = Path(base_path) / filename
    if not path.is_file():
        return False
    _load_dotenv(path, override=False)
    return True


def env(key: str, default: T | None = None) -> Any:
    """Read an environment variable with light boolean/int coercion."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return _coerce(raw, default)


def _coerce(raw: str, default: Any) -> Any:
    value = raw.strip()
    lowered = value.lower()

    if isinstance(default, bool) or lowered in _TRUE | _FALSE:
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False

    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except ValueError:
            return default

    if isinstance(default, float):
        try:
            return float(value)
        except ValueError:
            return default

    return value
