"""Form method spoofing — an HTML form that means PUT.

A browser form can send GET and POST, and nothing else. Laravel's answer is a
hidden `_method` field, which Prism's `method_field()` already emits; this is
the half that reads it.

It has to happen before routing, not inside the handler: Starlette matches on
the verb in the ASGI scope, so a form posting to a route that only answers PUT
would be told 405 (or fall through to the catch-all) before any handler ran.
So this rewrites `scope["method"]`, which means reading the body early and
replaying it — the cost is buffering one form submission, and only when the
request is a POST that could be carrying the field.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qsl

#: The verbs a form may claim. Spoofing GET would let a link mutate state.
SPOOFABLE = frozenset({"PUT", "PATCH", "DELETE"})

#: Laravel reads this header too, for clients that cannot send a body.
OVERRIDE_HEADER = b"x-http-method-override"

#: The field `method_field()` writes.
FIELD = "_method"

#: Where the verb the client actually sent is kept, so `request.real_method`
#: can still report POST after the scope has been rewritten.
REAL_METHOD = "almasix.real_method"

_FORM_TYPES = (b"application/x-www-form-urlencoded", b"multipart/form-data")

#: A form big enough to exceed this is not carrying a `_method` field it put
#: first, and buffering an upload to look for one would be the wrong trade.
MAX_BUFFER = 1024 * 1024

Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class SpoofMethodASGI:
    """Rewrites `scope["method"]` from `_method` before the router sees it."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope.get("type") != "http" or scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        override = _from_header(headers)
        if override:
            await self.app(_spoofed(scope, override), receive, send)
            return

        content_type = headers.get(b"content-type", b"")
        if not content_type.startswith(_FORM_TYPES):
            await self.app(scope, receive, send)
            return

        body, replay = await _buffer(receive)
        spoofed = _from_body(body, content_type)
        target = _spoofed(scope, spoofed) if spoofed else scope
        await self.app(target, replay, send)


def _spoofed(scope: dict[str, Any], method: str) -> dict[str, Any]:
    """``scope`` routed as ``method``, remembering the verb that arrived."""
    return {**scope, "method": method, REAL_METHOD: scope.get("method", "POST")}


def _from_header(headers: dict[bytes, bytes]) -> str | None:
    value = headers.get(OVERRIDE_HEADER, b"").decode("latin-1").strip().upper()
    return value if value in SPOOFABLE else None


def _from_body(body: bytes, content_type: bytes) -> str | None:
    if content_type.startswith(b"multipart/form-data"):
        value = _multipart_field(body, content_type)
    else:
        value = dict(parse_qsl(body.decode("utf-8", "replace"))).get(FIELD)
    found = str(value or "").strip().upper()
    return found if found in SPOOFABLE else None


def _multipart_field(body: bytes, content_type: bytes) -> str | None:
    """Read one field out of a multipart body without parsing all of it."""
    boundary = _boundary(content_type)
    if boundary is None:
        return None
    marker = f'name="{FIELD}"'.encode()
    for part in body.split(b"--" + boundary):
        if marker not in part:
            continue
        _, _, value = part.partition(b"\r\n\r\n")
        return value.strip().decode("utf-8", "replace")
    return None


def _boundary(content_type: bytes) -> bytes | None:
    for piece in content_type.split(b";"):
        key, _, value = piece.strip().partition(b"=")
        if key.lower() == b"boundary":
            return value.strip(b'"')
    return None


async def _buffer(receive: Receive) -> tuple[bytes, Receive]:
    """Read the body, and hand back a `receive` that serves it again."""
    chunks: list[bytes] = []
    messages: list[dict[str, Any]] = []
    size = 0
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        size += len(chunks[-1])
        if not message.get("more_body", False) or size > MAX_BUFFER:
            break

    index = 0

    async def replay() -> dict[str, Any]:
        nonlocal index
        if index < len(messages):
            message = messages[index]
            index += 1
            return message
        return await receive()

    return b"".join(chunks), replay
