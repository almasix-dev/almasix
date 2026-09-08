"""Queued auth cookies (remember-me) applied by ``StartAuth`` on the way out."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from starlette.responses import Response as StarletteResponse

_queued: ContextVar[list[QueuedCookie] | None] = ContextVar("almasix_auth_cookies", default=None)


@dataclass
class QueuedCookie:
    name: str
    value: str = ""
    max_age: int | None = None
    path: str = "/"
    secure: bool = False
    httponly: bool = True
    samesite: str = "lax"
    delete: bool = False


def begin_cookie_queue() -> Token[list[QueuedCookie] | None]:
    return _queued.set([])


def reset_cookie_queue(token: Token[list[QueuedCookie] | None]) -> None:
    _queued.reset(token)


def queue_cookie(
    name: str,
    value: str,
    *,
    max_age: int | None = None,
    path: str = "/",
    secure: bool = False,
    httponly: bool = True,
    samesite: str = "lax",
) -> None:
    bag = _queued.get()
    if bag is None:
        bag = []
        _queued.set(bag)
    bag.append(
        QueuedCookie(
            name=name,
            value=value,
            max_age=max_age,
            path=path,
            secure=secure,
            httponly=httponly,
            samesite=samesite,
        )
    )


def queue_forget_cookie(name: str, *, path: str = "/") -> None:
    bag = _queued.get()
    if bag is None:
        bag = []
        _queued.set(bag)
    bag.append(QueuedCookie(name=name, path=path, delete=True))


def apply_queued_cookies(response: StarletteResponse) -> None:
    bag = _queued.get() or []
    for cookie in bag:
        if cookie.delete:
            response.delete_cookie(cookie.name, path=cookie.path)
            continue
        kwargs: dict[str, Any] = {
            "path": cookie.path,
            "httponly": cookie.httponly,
            "samesite": cookie.samesite,
            "secure": cookie.secure,
        }
        if cookie.max_age is not None:
            kwargs["max_age"] = cookie.max_age
        response.set_cookie(cookie.name, cookie.value, **kwargs)
