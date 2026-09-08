"""Auth lifecycle events (Laravel Auth::* event parity, lightweight)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

Listener = Callable[..., Awaitable[None] | None]

_listeners: dict[str, list[Listener]] = {}


@dataclass(frozen=True)
class Attempting:
    credentials: dict[str, Any]
    guard: str
    remember: bool


@dataclass(frozen=True)
class Validated:
    user: Any
    guard: str


@dataclass(frozen=True)
class Login:
    user: Any
    guard: str
    remember: bool


@dataclass(frozen=True)
class Failed:
    credentials: dict[str, Any]
    guard: str


@dataclass(frozen=True)
class Authenticated:
    user: Any
    guard: str


@dataclass(frozen=True)
class Logout:
    user: Any
    guard: str


@dataclass(frozen=True)
class OtherDeviceLogout:
    user: Any
    guard: str


@dataclass(frozen=True)
class PasswordReset:
    user: Any


def listen(event: type | str, callback: Listener) -> None:
    key = event if isinstance(event, str) else event.__name__
    _listeners.setdefault(key, []).append(callback)


def forget(event: type | str | None = None) -> None:
    if event is None:
        _listeners.clear()
        return
    key = event if isinstance(event, str) else event.__name__
    _listeners.pop(key, None)


async def dispatch(event: Any) -> None:
    key = type(event).__name__
    for callback in list(_listeners.get(key, [])):
        result = callback(event)
        if hasattr(result, "__await__"):
            await result  # type: ignore[misc]
