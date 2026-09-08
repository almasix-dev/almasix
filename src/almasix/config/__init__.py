"""Configuration helpers."""

from __future__ import annotations

from typing import Any

from almasix.config.env import env, load_environment
from almasix.config.repository import ConfigRepository

_repository: ConfigRepository | None = None


def set_repository(repository: ConfigRepository | None) -> None:
    global _repository
    _repository = repository


def get_repository() -> ConfigRepository:
    if _repository is None:
        raise RuntimeError("Configuration repository is not set. Bootstrap the Application first.")
    return _repository


def config(key: str, default: Any = None) -> Any:
    """Read a config value using dot notation, e.g. ``config('app.name')``."""
    return get_repository().get(key, default)


__all__ = [
    "ConfigRepository",
    "config",
    "env",
    "get_repository",
    "load_environment",
    "set_repository",
]
