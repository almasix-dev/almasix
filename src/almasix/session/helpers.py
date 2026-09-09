"""``session()``, ``old()``, and ``cookie()``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from almasix.session.store import Session, get_session

if TYPE_CHECKING:
    from almasix.auth.cookies import QueuedCookie

_OLD_INPUT = "_old_input"

# Ten years, in minutes — Laravel's ``Cookie::forever``.
_FOREVER = 60 * 24 * 365 * 10


def session(key: str | Mapping[str, Any] | None = None, default: Any = None) -> Any:
    """Read the session, one of its values, or write a mapping (Laravel ``session``).

    - ``session()`` → the session bag
    - ``session('cart.total')`` → a value
    - ``session({'cart.total': 12})`` → write every pair, returning ``None``
    """
    store = _require_session()
    if key is None:
        return store
    if isinstance(key, Mapping):
        for name, value in key.items():
            store.put(str(name), value)
        return None
    return store.get(key, default)


def old(key: str | None = None, default: Any = None) -> Any:
    """Read input flashed by ``redirect().with_input()`` (Laravel ``old``).

    Returns ``default`` when nothing was flashed, and outside a session too:
    templates re-render old input on paths that may have no session at all.
    """
    store = get_session()
    values = store.get(_OLD_INPUT, {}) if store is not None else {}
    if not isinstance(values, Mapping):
        values = {}
    if key is None:
        return dict(values)
    return values.get(key, default)


def flash_input(values: Mapping[str, Any]) -> None:
    """Flash input for the next request's ``old()`` reads."""
    _require_session().flash(_OLD_INPUT, dict(values))


def _require_session() -> Session:
    store = get_session()
    if store is None:
        raise RuntimeError(
            "Session store not started. Add StartSession to the web middleware group."
        )
    return store


class CookieJar:
    """Laravel's cookie factory — what ``cookie()`` returns with no name."""

    def make(
        self,
        name: str,
        value: str = "",
        minutes: int | None = None,
        *,
        path: str = "/",
        secure: bool = False,
        http_only: bool = True,
        same_site: str = "lax",
    ) -> QueuedCookie:
        """Build a cookie without sending it — queue it, or set it yourself."""
        from almasix.auth.cookies import QueuedCookie

        return QueuedCookie(
            name=name,
            value=value,
            max_age=None if minutes is None else minutes * 60,
            path=path,
            secure=secure,
            httponly=http_only,
            samesite=same_site,
        )

    def forever(self, name: str, value: str = "", **kwargs: Any) -> QueuedCookie:
        """Build a cookie that lasts ten years."""
        return self.make(name, value, _FOREVER, **kwargs)

    def queue(
        self,
        name: str | QueuedCookie,
        value: str = "",
        minutes: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Attach a cookie to the response on the way out."""
        from almasix.auth.cookies import QueuedCookie, queue_cookie

        built = (
            name if isinstance(name, QueuedCookie) else self.make(name, value, minutes, **kwargs)
        )
        queue_cookie(
            built.name,
            built.value,
            max_age=built.max_age,
            path=built.path,
            secure=built.secure,
            httponly=built.httponly,
            samesite=built.samesite,
        )

    def forget(self, name: str, *, path: str = "/") -> None:
        """Queue a cookie's deletion."""
        from almasix.auth.cookies import queue_forget_cookie

        queue_forget_cookie(name, path=path)

    def __call__(
        self,
        name: str,
        value: str = "",
        minutes: int | None = None,
        **kwargs: Any,
    ) -> QueuedCookie:
        return self.make(name, value, minutes, **kwargs)


_jar = CookieJar()


def cookie(
    name: str | None = None,
    value: str = "",
    minutes: int | None = None,
    **kwargs: Any,
) -> Any:
    """Build a cookie, or return the jar when given no name (Laravel ``cookie``).

    The cookie is built, not sent: queue it with ``cookie().queue(...)``, which
    the auth middleware flushes onto the outgoing response.
    """
    if name is None:
        return _jar
    return _jar.make(name, value, minutes, **kwargs)


def cookie_jar() -> CookieJar:
    """Return the cookie jar without the ``cookie()`` overload."""
    return _jar


__all__ = ["CookieJar", "cookie", "cookie_jar", "flash_input", "old", "session"]
