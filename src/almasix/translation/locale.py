"""Request-scoped locale — never a process-wide mutable global under ASGI."""

from __future__ import annotations

from contextvars import ContextVar

_locale: ContextVar[str | None] = ContextVar("almasix_locale", default=None)
_fallback: ContextVar[str | None] = ContextVar("almasix_fallback_locale", default=None)
_date_locale: ContextVar[str | None] = ContextVar("almasix_date_locale", default=None)

_DEFAULT_LOCALE = "en"
_DEFAULT_FALLBACK = "en"


def set_locale(locale: str) -> None:
    """Set the active locale for the current context (request / task)."""
    normalized = (locale or _DEFAULT_LOCALE).replace("_", "-")
    _locale.set(normalized)
    _date_locale.set(normalized)


def get_locale() -> str:
    value = _locale.get()
    return value if value is not None else _DEFAULT_LOCALE


def peek_locale() -> str | None:
    """Return the context locale without applying the default."""
    return _locale.get()


def is_locale(locale: str) -> bool:
    return get_locale().lower() == (locale or "").replace("_", "-").lower()


def set_fallback_locale(locale: str) -> None:
    _fallback.set((locale or _DEFAULT_FALLBACK).replace("_", "-"))


def get_fallback_locale() -> str:
    return _fallback.get() or _DEFAULT_FALLBACK


def get_date_locale() -> str:
    return _date_locale.get() or get_locale()


def reset_locale_context() -> None:
    """Clear request-scoped locale (tests / after request)."""
    _locale.set(None)
    _fallback.set(None)
    _date_locale.set(None)
