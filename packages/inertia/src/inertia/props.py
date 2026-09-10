"""Inertia deferred / lazy / optional / once / merge prop wrappers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class LazyProp:
    """Resolved only when requested via partial reload (Inertia lazy props)."""

    def __init__(self, callback: Callable[[], Any]) -> None:
        self.callback = callback

    def __call__(self) -> Any:
        return self.callback()


class OptionalProp(LazyProp):
    """Alias for lazy — omitted unless listed in ``X-Inertia-Partial-Data``."""


class DeferProp:
    """Included on first visit as a deferred placeholder; client fetches later."""

    def __init__(self, callback: Callable[[], Any], *, group: str = "default") -> None:
        self.callback = callback
        self.group = group

    def __call__(self) -> Any:
        return self.callback()


class OnceProp:
    """Resolved once per visit; subsequent partials may skip re-evaluation."""

    def __init__(self, callback: Callable[[], Any]) -> None:
        self.callback = callback
        self._value: Any = None
        self._resolved = False

    def __call__(self) -> Any:
        if not self._resolved:
            self._value = self.callback()
            self._resolved = True
        return self._value


class MergeProp:
    """Mark a prop for client-side merge (Inertia merge props)."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def resolve(self) -> Any:
        if callable(self.value) and not isinstance(self.value, type):
            return self.value()
        return self.value


def lazy(callback: Callable[[], Any]) -> LazyProp:
    return LazyProp(callback)


def optional(callback: Callable[[], Any]) -> OptionalProp:
    return OptionalProp(callback)


def defer(callback: Callable[[], Any], *, group: str = "default") -> DeferProp:
    return DeferProp(callback, group=group)


def once(callback: Callable[[], Any]) -> OnceProp:
    return OnceProp(callback)


def merge(value: Any) -> MergeProp:
    return MergeProp(value)
