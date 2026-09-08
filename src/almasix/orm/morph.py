"""The morph map — stable aliases for polymorphic types.

Storing `"App\\Models\\Post"`-style class names in `*_type` columns welds the
database to the code layout. A morph map stores a short alias instead, so
classes can move without a migration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MAP: dict[str, type[Any]] = {}
_ENFORCED = False


def morph_map(
    mapping: Mapping[str, type[Any]] | None = None,
    merge: bool = True,
) -> dict[str, type[Any]]:
    """Register or read the morph map."""
    global _MAP
    if mapping is not None:
        _MAP = {**_MAP, **dict(mapping)} if merge else dict(mapping)
    return dict(_MAP)


def enforce_morph_map(mapping: Mapping[str, type[Any]], merge: bool = True) -> dict[str, type[Any]]:
    """Register the map and reject any type that is missing from it."""
    global _ENFORCED
    _ENFORCED = True
    return morph_map(mapping, merge)


def clear_morph_map() -> None:
    """Forget the map — for tests and for reboots."""
    global _MAP, _ENFORCED
    _MAP = {}
    _ENFORCED = False


def morph_enforced() -> bool:
    return _ENFORCED


def morph_alias(model_class: type[Any]) -> str:
    """The alias stored in a `*_type` column for this model."""
    for alias, mapped in _MAP.items():
        if mapped is model_class:
            return alias
    if _ENFORCED:
        raise LookupError(
            f"{model_class.__name__} is missing from the enforced morph map. "
            f"Add it with morph_map({{'alias': {model_class.__name__}}})."
        )
    return model_class.__name__


def morph_target(alias: str) -> type[Any] | None:
    """The model a stored alias points at, if the map knows it."""
    return _MAP.get(str(alias))
