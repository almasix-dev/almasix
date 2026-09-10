"""Livewire-shaped attribute helpers for Conduit components."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def Computed(fn: F | None = None, *, persist: bool = False) -> Any:
    """Mark a method as a computed property (cached per request / render)."""

    def decorator(method: F) -> F:
        method._conduit_computed = True  # type: ignore[attr-defined]
        method._conduit_computed_persist = persist  # type: ignore[attr-defined]
        return method

    return decorator if fn is None else decorator(fn)


def Locked(fn: F | None = None) -> Any:
    """Prevent a public property from being updated from the client."""

    def decorator(method: F) -> F:
        method._conduit_locked = True  # type: ignore[attr-defined]
        return method

    if fn is not None and not callable(fn):
        # Used as assignment marker on class body via descriptor — store name later.
        return _LockedMarker(fn)
    return decorator if fn is None else decorator(fn)


class _LockedMarker:
    def __init__(self, default: Any) -> None:
        self.default = default
        self._conduit_locked = True


def On(event: str) -> Callable[[F], F]:
    """Listen for a browser/component event and call the method."""

    def decorator(method: F) -> F:
        method._conduit_on = event  # type: ignore[attr-defined]
        return method

    return decorator


def Modelable(fn: F) -> F:
    """Allow the component to be used as ``wire:model`` on a parent (entangle target)."""
    fn._conduit_modelable = True  # type: ignore[attr-defined]
    return fn


def locked_property_names(cls: type) -> set[str]:
    names: set[str] = set()
    for klass in cls.__mro__:
        for key, value in vars(klass).items():
            if getattr(value, "_conduit_locked", False):
                names.add(key)
            if isinstance(value, _LockedMarker):
                names.add(key)
    # Class-level ``_locked = ("foo",)`` convention
    extra = getattr(cls, "_locked", None) or getattr(cls, "locked", None)
    if isinstance(extra, (list, tuple, set)):
        names.update(str(x) for x in extra)
    return names
