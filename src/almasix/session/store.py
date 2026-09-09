"""In-request session bag + contextvar access."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_current: ContextVar[Session | None] = ContextVar("almasix_session", default=None)


class Session:
    """Mutable key/value bag persisted by :class:`StartSession`."""

    def __init__(self, data: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(data or {})
        self._dirty = False

    def all(self) -> dict[str, Any]:
        return dict(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._dirty = True

    def forget(self, key: str) -> None:
        if key in self._data:
            del self._data[key]
            self._dirty = True

    def flush(self) -> None:
        self._data.clear()
        self._dirty = True

    def regenerate(self) -> None:
        """Mark dirty so the cookie is rewritten (id rotation is cookie-store simple)."""
        self._dirty = True

    def has(self, key: str) -> bool:
        return key in self._data

    def pull(self, key: str, default: Any = None) -> Any:
        value = self.get(key, default)
        self.forget(key)
        return value

    def flash(self, key: str, value: Any) -> None:
        """Store a value for the next request only."""
        flashes = dict(self.get("_flash", {}) or {})
        flashes[key] = value
        self.put("_flash", flashes)

    def age_flash(self) -> None:
        """Promote flash bag into readable keys and clear the flash store."""
        flashes = dict(self.get("_flash", {}) or {})
        old = dict(self.get("_old_flash", {}) or {})
        for key in old:
            self.forget(key)
        for key, value in flashes.items():
            self._data[key] = value
        self.put("_old_flash", flashes)
        self.put("_flash", {})

    @property
    def dirty(self) -> bool:
        return self._dirty

    def __bool__(self) -> bool:
        return bool(self._data)


def get_session() -> Session | None:
    return _current.get()


def set_session(session: Session | None) -> Token[Session | None]:
    #: The session a test asserts on is the one the request finished with, and
    #: by then the contextvar has been reset. Keep the last bag for `almasix.testing`.
    global _last
    if session is not None:
        _last = session
    return _current.set(session)


_last: Session | None = None


def last_session() -> Session | None:
    """The session the most recent request used (`almasix.testing` reads this)."""
    return _last


def reset_session(token: Token[Session | None]) -> None:
    _current.reset(token)
