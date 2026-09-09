"""Configuration repository (Laravel ``config()`` equivalent)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


class ConfigRepository:
    """Nested config store loaded from ``config/*.py`` modules."""

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def load_directory(self, directory: str | Path) -> None:
        path = Path(directory)
        if not path.is_dir():
            return

        for file in sorted(path.glob("*.py")):
            if file.name.startswith("_"):
                continue
            key = file.stem
            self._items[key] = self._load_module_config(file)

    def _load_module_config(self, file: Path) -> Any:
        module_name = f"almasix_app_config_{file.stem}_{id(file)}"
        spec = importlib.util.spec_from_file_location(module_name, file)
        if spec is None or spec.loader is None:  # pragma: no cover
            raise ImportError(f"Cannot load config file: {file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(module_name, None)

        if hasattr(module, "config"):
            return module.config

        return {
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith("_") and name != "env"
        }

    def get(self, key: str, default: Any = None) -> Any:
        if not key:
            return default

        parts = key.split(".")
        current: Any = self._items
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def set(self, key: str, value: Any) -> None:
        parts = key.split(".")
        current = self._items
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value

    def has(self, key: str) -> bool:
        sentinel = object()
        return self.get(key, sentinel) is not sentinel

    def all(self) -> dict[str, Any]:
        return self._items
