"""Language catalog loader — PHP-style groups + JSON string-as-key files."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


class FileLoader:
    """Loads `lang/<locale>/<group>.py` and `lang/<locale>.json` catalogs."""

    def __init__(self) -> None:
        self._paths: list[Path] = []
        self._json_paths: list[Path] = []
        self._namespaces: dict[str, Path] = {}
        self._hints: dict[str, Path] = {}  # namespace → package lang root
        self._cache: dict[tuple[str, str, str], dict[str, Any]] = {}
        self._json_cache: dict[str, dict[str, str]] = {}
        self._lines: dict[tuple[str, str], dict[str, Any]] = {}  # (locale, ns) runtime

    def add_path(self, path: str | Path) -> None:
        resolved = Path(path).resolve()
        if resolved not in self._paths:
            self._paths.append(resolved)

    def add_json_path(self, path: str | Path) -> None:
        resolved = Path(path).resolve()
        if resolved not in self._json_paths:
            self._json_paths.append(resolved)

    def add_namespace(self, namespace: str, hint: str | Path) -> None:
        self._namespaces[namespace] = Path(hint).resolve()
        self._hints[namespace] = Path(hint).resolve()

    def add_lines(self, lines: dict[str, Any], locale: str, namespace: str = "*") -> None:
        key = (locale, namespace)
        bag = self._lines.setdefault(key, {})
        self._merge(bag, lines)
        # Bust group cache for this locale.
        self._cache = {k: v for k, v in self._cache.items() if k[1] != locale}

    def clear_cache(self) -> None:
        self._cache.clear()
        self._json_cache.clear()

    def load(self, namespace: str, group: str, locale: str) -> dict[str, Any]:
        cache_key = (namespace, locale, group)
        if cache_key in self._cache:
            return self._cache[cache_key]

        lines: dict[str, Any] = {}

        # Framework / app paths (later paths override earlier — app last wins).
        for root in self._paths:
            self._merge(lines, self._load_group_file(root, locale, group, namespace))

        # Package namespace hint.
        if namespace != "*" and namespace in self._namespaces:
            hint = self._namespaces[namespace]
            self._merge(lines, self._load_group_file(hint, locale, group, namespace="*"))

        # Vendor overrides: lang/vendor/<package>/<locale>/<group>.py
        if namespace != "*":
            for root in self._paths:
                vendor = root / "vendor" / namespace / locale / f"{group}.py"
                self._merge(lines, self._load_py(vendor))

        # Runtime lines.
        runtime = self._lines.get((locale, namespace)) or self._lines.get((locale, "*"))
        if runtime:
            self._merge(lines, runtime)

        self._cache[cache_key] = lines
        return lines

    def load_json(self, locale: str) -> dict[str, str]:
        if locale in self._json_cache:
            return self._json_cache[locale]

        lines: dict[str, str] = {}
        search = [*self._json_paths, *self._paths]
        for root in search:
            path = root / f"{locale}.json"
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):  # pragma: no branch
                    for key, value in data.items():
                        lines[str(key)] = str(value)
        self._json_cache[locale] = lines
        return lines

    def _load_group_file(
        self,
        root: Path,
        locale: str,
        group: str,
        namespace: str,
    ) -> dict[str, Any]:
        del namespace  # reserved for future namespaced path layouts
        return self._load_py(root / locale / f"{group}.py")

    def _load_py(self, path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        module_name = f"almasix_lang_{abs(hash(path))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:  # noqa: BLE001 — lang files are user-authored
            return {}
        data = getattr(module, "translations", None)
        if data is None:
            data = getattr(module, "messages", None)
        if isinstance(data, dict):
            return data
        # Laravel PHP files `return [...]` — allow a bare `translations` or
        # convention: module-level dict named after the file stem.
        for attr in ("config", "lang", path.stem):
            candidate = getattr(module, attr, None)
            if isinstance(candidate, dict):
                return candidate
        return {}

    @staticmethod
    def _merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        for key, value in source.items():
            if (
                key in target
                and isinstance(target[key], dict)
                and isinstance(value, dict)
            ):
                FileLoader._merge(target[key], value)
            else:
                target[key] = value
