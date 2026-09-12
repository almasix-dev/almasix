"""Validation rule protocol and helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Protocol


class Fail(Protocol):
    def __call__(
        self, message: str | None = None, *, rule: str | None = None, **params: Any
    ) -> None: ...


class ValidationRule(Protocol):
    """One Laravel-shaped validation rule."""

    name: str
    implicit: bool

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool: ...

    def message(self) -> str | None:
        """Optional custom message; None → catalog lookup by ``name``."""
        return None


class RuleBase:
    """Concrete base for built-in rules."""

    name: str = "custom"
    implicit: bool = False

    def passes(self, attribute: str, value: Any, data: Mapping[str, Any]) -> bool:
        raise NotImplementedError

    def message(self) -> str | None:
        return None

    def params(self) -> dict[str, Any]:
        return {}

    def size_kind(self, value: Any) -> str | None:
        return None

    def __call__(self, value: Any) -> Any:
        """Pydantic ``AfterValidator`` adapter (single-field rules only)."""
        if not self.passes("_", value, {}):
            raise ValueError(self.message() or f"The given value failed {self.name}.")
        return value


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, dict, tuple, set)) and len(value) == 0:
        return True
    return False


def data_get(data: Mapping[str, Any], key: str, default: Any = None) -> Any:
    """Laravel ``data_get`` — dotted paths."""
    if key in data:
        return data[key]
    current: Any = data
    for part in key.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return default
    return current


Invokable = Callable[[str, Any, Mapping[str, Any]], bool]

__all__ = [
    "Fail",
    "Invokable",
    "RuleBase",
    "ValidationRule",
    "data_get",
    "is_blank",
]
