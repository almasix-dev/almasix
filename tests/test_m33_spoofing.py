"""M33 — method spoofing at the ASGI layer.

The HTTP tests prove a form can claim PUT. These prove the parts that are hard
to reach through a client: a multipart body, a body that arrives in chunks, a
body too big to buffer, and every way the field can be wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

from almasix.http.spoofing import (
    MAX_BUFFER,
    REAL_METHOD,
    SpoofMethodASGI,
    _boundary,
    _buffer,
    _multipart_field,
)

BOUNDARY = "----almasix"
MULTIPART = f"multipart/form-data; boundary={BOUNDARY}"


def _multipart(fields: dict[str, str]) -> bytes:
    parts = [
        f'--{BOUNDARY}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in fields.items()
    ]
    return ("".join(parts) + f"--{BOUNDARY}--\r\n").encode()


class Recorder:
    """Stands in for the application, remembering the scope it was handed."""

    def __init__(self) -> None:
        self.scope: dict[str, Any] | None = None
        self.body = b""

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        self.scope = scope
        chunks = []
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        self.body = b"".join(chunks)


def _scope(
    method: str = "POST",
    content_type: str = "application/x-www-form-urlencoded",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    encoded = [(b"content-type", content_type.encode())]
    encoded += [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    return {"type": "http", "method": method, "headers": encoded}


def _receive(*bodies: bytes) -> Any:
    messages = [
        {"type": "http.request", "body": body, "more_body": index < len(bodies) - 1}
        for index, body in enumerate(bodies)
    ]
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        message = messages[index]
        index += 1
        return message

    return receive


async def _run(scope: dict[str, Any], *bodies: bytes) -> Recorder:
    recorder = Recorder()
    await SpoofMethodASGI(recorder)(scope, _receive(*bodies or (b"",)), None)
    return recorder


# --- the happy paths --------------------------------------------------------


@pytest.mark.parametrize("verb", ["PUT", "PATCH", "DELETE", "put", "Delete"])
async def test_a_form_field_rewrites_the_scope(verb: str) -> None:
    recorder = await _run(_scope(), f"_method={verb}".encode())

    assert recorder.scope is not None
    assert recorder.scope["method"] == verb.upper()
    assert recorder.scope[REAL_METHOD] == "POST"


async def test_the_body_still_reaches_the_application() -> None:
    recorder = await _run(_scope(), b"_method=PUT&title=hello")

    assert recorder.body == b"_method=PUT&title=hello"


async def test_a_body_that_arrives_in_pieces_is_read_and_replayed() -> None:
    recorder = await _run(_scope(), b"_method=", b"PATCH&a=1")

    assert recorder.scope is not None
    assert recorder.scope["method"] == "PATCH"
    assert recorder.body == b"_method=PATCH&a=1"


async def test_a_multipart_form_may_spoof_too() -> None:
    recorder = await _run(
        _scope(content_type=MULTIPART), _multipart({"_method": "DELETE", "title": "x"})
    )

    assert recorder.scope is not None
    assert recorder.scope["method"] == "DELETE"


# --- what must not be spoofed -----------------------------------------------


@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "OPTIONS"])
async def test_only_a_post_is_examined(method: str) -> None:
    recorder = await _run(_scope(method=method), b"_method=DELETE")

    assert recorder.scope is not None
    assert recorder.scope["method"] == method
    assert REAL_METHOD not in recorder.scope


@pytest.mark.parametrize("claimed", ["GET", "HEAD", "BREW", "", "put post"])
async def test_a_verb_outside_the_spoofable_set_is_ignored(claimed: str) -> None:
    recorder = await _run(_scope(), f"_method={claimed}".encode())

    assert recorder.scope is not None
    assert recorder.scope["method"] == "POST"


async def test_a_body_that_is_not_a_form_is_not_read() -> None:
    recorder = await _run(_scope(content_type="application/json"), b'{"_method":"PUT"}')

    assert recorder.scope is not None
    assert recorder.scope["method"] == "POST"
    assert recorder.body == b'{"_method":"PUT"}'


async def test_a_scope_that_is_not_http_passes_straight_through() -> None:
    recorder = Recorder()
    scope = {"type": "lifespan"}

    await SpoofMethodASGI(recorder)(scope, _receive(b""), None)

    assert recorder.scope is scope


async def test_a_form_with_no_method_field_is_left_alone() -> None:
    recorder = await _run(_scope(), b"title=hello")

    assert recorder.scope is not None
    assert recorder.scope["method"] == "POST"


# --- the header form --------------------------------------------------------


async def test_the_override_header_spoofs_without_reading_the_body() -> None:
    recorder = await _run(
        _scope(content_type="application/json", headers={"x-http-method-override": "delete"}),
        b'{"big":"payload"}',
    )

    assert recorder.scope is not None
    assert recorder.scope["method"] == "DELETE"
    assert recorder.body == b'{"big":"payload"}'


async def test_an_override_header_naming_a_verb_nobody_may_spoof_is_ignored() -> None:
    recorder = await _run(_scope(headers={"x-http-method-override": "GET"}), b"")

    assert recorder.scope is not None
    assert recorder.scope["method"] == "POST"


# --- buffering limits -------------------------------------------------------


async def test_a_body_past_the_buffer_limit_stops_being_read() -> None:
    body, replay = await _buffer(_receive(b"x" * (MAX_BUFFER + 1), b"never read"))

    assert len(body) == MAX_BUFFER + 1
    # The rest is still there for the application, which is what replay means.
    assert (await replay())["body"] == b"x" * (MAX_BUFFER + 1)


async def test_buffering_stops_at_a_disconnect() -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    body, replay = await _buffer(receive)

    assert body == b""
    assert (await replay())["type"] == "http.disconnect"


async def test_replay_falls_through_to_the_real_receive_once_it_is_spent() -> None:
    calls = [
        {"type": "http.request", "body": b"a", "more_body": False},
        {"type": "http.request", "body": b"later", "more_body": False},
    ]
    index = 0

    async def receive() -> dict[str, Any]:
        nonlocal index
        message = calls[index]
        index += 1
        return message

    _, replay = await _buffer(receive)

    assert (await replay())["body"] == b"a"
    assert (await replay())["body"] == b"later"


# --- multipart parsing ------------------------------------------------------


def test_a_multipart_body_with_no_boundary_yields_nothing() -> None:
    assert _multipart_field(b"whatever", b"multipart/form-data") is None
    assert _boundary(b"multipart/form-data") is None


def test_a_quoted_boundary_is_unquoted() -> None:
    assert _boundary(b'multipart/form-data; boundary="abc"') == b"abc"


def test_a_multipart_body_without_the_field_yields_nothing() -> None:
    body = _multipart({"title": "x"})

    assert _multipart_field(body, MULTIPART.encode()) is None
