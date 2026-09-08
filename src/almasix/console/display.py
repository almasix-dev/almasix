"""Pretty display for Loupe — models, collections, JSON, and plain values."""

from __future__ import annotations

import json
from typing import Any


def is_model(value: Any) -> bool:
    return (
        callable(getattr(value, "to_dict", None))
        and callable(getattr(value, "get_key", None))
        and hasattr(value, "_attributes")
    )


def is_model_collection(value: Any) -> bool:
    return callable(getattr(value, "to_dict", None)) and callable(
        getattr(value, "model_keys", None)
    )


def is_support_collection(value: Any) -> bool:
    cls = type(value)
    return cls.__name__ == "Collection" and cls.__module__.startswith("almasix.")


def is_paginator(value: Any) -> bool:
    return callable(getattr(value, "to_dict", None)) and hasattr(value, "items")


def describe(value: Any) -> str:
    """Short caption for the value, e.g. ``Collection[User] (2)``."""
    if is_model(value):
        return f"{type(value).__name__} #{value.get_key()!r}"
    if is_model_collection(value):
        items = list(value)
        name = type(items[0]).__name__ if items and is_model(items[0]) else "Model"
        return f"Collection[{name}] ({len(items)})"
    if is_paginator(value):
        return f"{type(value).__name__}"
    if is_support_collection(value):
        return f"Collection ({len(value)})"
    if isinstance(value, dict):
        return f"dict ({len(value)} keys)"
    if isinstance(value, (list, tuple)):
        return f"{type(value).__name__} ({len(value)})"
    return type(value).__name__


def serialize(value: Any) -> Any:
    """Convert Almasix objects into JSON-friendly structures for display."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if is_model(value):
        return value.to_dict()
    if is_model_collection(value) or is_paginator(value):
        return value.to_dict()
    if is_support_collection(value):
        # A support collection is a sequence, not a record: the one that does
        # carry a ``to_dict`` is Articulate's, and it was handled above.
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except TypeError:
            pass
    return value


def to_json(value: Any, *, indent: int = 2) -> str:
    """Pretty JSON string for any displayable value."""
    return json.dumps(serialize(value), indent=indent, default=str, ensure_ascii=False)


def dump(*values: Any, as_json: bool = True) -> tuple[Any, ...]:
    """Laravel ``dump()`` — prefer ``almasix.debug.dump`` for full chrome."""
    from almasix.debug import dump as debug_dump

    return debug_dump(*values, as_json=as_json, _depth=2)


def render(value: Any, *, console: Any | None = None, as_json: bool = True) -> None:
    """Print a Tinker-class dump to the terminal."""
    from almasix.debug import render as debug_render

    debug_render(value, console=console, as_json=as_json)
