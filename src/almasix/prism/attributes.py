"""Blade-shaped HTML attribute bag for Prism components."""

from __future__ import annotations

from typing import Any


class AttributeBag:
    """Minimal ``$attributes`` parallel for component templates."""

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        self._attrs = dict(attrs or {})

    def merge(self, defaults: dict[str, Any]) -> AttributeBag:
        merged = dict(defaults)
        for key, value in self._attrs.items():
            if key == "class" and "class" in merged:
                merged["class"] = f"{merged['class']} {value}".strip()
            else:
                merged[key] = value
        return AttributeBag(merged)

    def except_(self, *keys: str) -> AttributeBag:
        skip = set(keys)
        return AttributeBag({k: v for k, v in self._attrs.items() if k not in skip})

    def only(self, *keys: str) -> AttributeBag:
        keep = set(keys)
        return AttributeBag({k: v for k, v in self._attrs.items() if k in keep})

    def get(self, key: str, default: Any = None) -> Any:
        return self._attrs.get(key, default)

    def __str__(self) -> str:
        parts: list[str] = []
        for key, value in self._attrs.items():
            if value is True:
                parts.append(key)
            elif value is False or value is None:
                continue
            else:
                parts.append(f'{key}="{value}"')
        return " ".join(parts)

    def __html__(self) -> str:
        return str(self)
