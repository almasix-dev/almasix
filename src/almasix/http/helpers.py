"""``request()`` and ``response()`` — the current request, and a response factory."""

from __future__ import annotations

from typing import Any

from almasix.http.request import Request, get_request
from almasix.http.response import ResponseFactory, make_response

_factory = ResponseFactory()


def request(key: str | None = None, default: Any = None) -> Any:
    """Return the request being handled, or one of its inputs (Laravel ``request``).

    Outside a request this returns ``None`` rather than an empty request, so
    console and queue code can ask without pretending there is a caller.
    """
    current: Request | None = get_request()
    if key is None:
        return current
    if current is None:
        return default
    return current.input(key, default)


def response(
    content: Any = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> Any:
    """Build a response, or return the factory when given no content.

    ``response()`` hands back a :class:`~almasix.http.response.ResponseFactory`
    for ``json`` / ``view`` / ``download`` / ``no_content`` and friends; use
    ``response().no_content()`` for an empty body, since ``response(None)``
    returns the factory rather than a 204.
    """
    if content is None and status == 200 and not headers:
        return _factory
    return make_response(content, status=status, headers=headers)


def response_factory() -> ResponseFactory:
    """Return the response factory without the ``response()`` overload."""
    return _factory


__all__ = ["request", "response", "response_factory"]
