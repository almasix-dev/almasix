"""Request Laravel-parity coverage."""

from __future__ import annotations

import pytest
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from almasix.http import Middleware, Request, UploadedFile, make_response
from almasix.http.middleware import Middleware as MiddlewareBase
from almasix.routing import Route


def _starlette_request(
    path: str = "/demo/1",
    query: str = "q=1",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    body: bytes = b"",
) -> StarletteRequest:
    if headers is None:
        headers = [(b"authorization", b"Bearer secret-token")]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": headers,
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    request = StarletteRequest(scope, receive=_receive(body))
    request.scope["path_params"] = {"id": "1"}
    return request


def _receive(body: bytes):
    sent = False

    async def receive() -> dict:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


@pytest.mark.asyncio
async def test_request_query_and_meta() -> None:
    raw = _starlette_request()
    request = await Request.create(raw)
    assert request.method == "GET"
    assert request.path == "/demo/1"
    assert "demo" in request.url
    assert request.query("q") == "1"
    assert request.input("q") == "1"
    assert request.route("id") == "1"
    assert "id" not in request.all()  # route params are not in all()
    assert request.input("missing", "x") == "x"
    assert request.bearer_token() == "secret-token"
    assert request.path_params["id"] == "1"
    assert request.headers.get("authorization")
    assert request.ip() == "127.0.0.1"
    assert request.is_method("get")
    assert request.raw is raw


@pytest.mark.asyncio
async def test_request_json_bag_and_selectors() -> None:
    raw = _starlette_request(
        method="POST",
        query="q=from-query&flag=0",
        headers=[
            (b"content-type", b"application/json"),
            (b"user-agent", b"almasix-test"),
        ],
        body=b'{"name":"Almasix","flag":true,"count":"3","q":"from-body"}',
    )
    request = await Request.create(raw)
    assert request.is_json()
    assert request.all()["name"] == "Almasix"
    assert request.all()["q"] == "from-body"  # body wins
    assert request.query("q") == "from-query"
    assert request.post("name") == "Almasix"
    assert request.json("name") == "Almasix"
    assert request.only("name", "count") == {"name": "Almasix", "count": "3"}
    assert "flag" not in request.except_("flag")
    assert request.has("name", "flag")
    assert request.has_any("nope", "name")
    assert request.filled("name")
    assert request.missing("x")
    assert request.boolean("flag") is True
    assert request.integer("count") == 3
    assert request.string("name") == "Almasix"
    assert request.user_agent() == "almasix-test"
    assert "name" in request
    assert request["name"] == "Almasix"
    request.merge({"extra": 1})
    assert request.input("extra") == 1
    request.replace({"only": True})
    assert request.all() == {"only": True}


@pytest.mark.asyncio
async def test_request_form_and_files() -> None:
    boundary = "----almasix"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="title"\r\n\r\n'
        "Hello\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="doc"; filename="note.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "file-body\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    raw = _starlette_request(
        method="POST",
        query="",
        headers=[(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        body=body,
    )
    request = await Request.create(raw)
    assert request.post("title") == "Hello"
    assert request.has_file("doc")
    uploaded = request.file("doc")
    assert isinstance(uploaded, UploadedFile)
    assert uploaded.filename == "note.txt"
    assert await uploaded.read() == b"file-body"
    assert "doc" in request.files()


def test_request_bearer_absent() -> None:
    request = Request(_starlette_request(headers=[]), hydrated=True)
    assert request.bearer_token() is None


@pytest.mark.asyncio
async def test_middleware_default_passthrough() -> None:
    mw = MiddlewareBase()

    async def nxt(req: Request):
        return JSONResponse({"ok": True})

    response = await mw.handle(await Request.create(_starlette_request()), nxt)
    assert response.status_code == 200


def test_make_response_passthrough_headers() -> None:
    original = JSONResponse({"a": 1})
    wrapped = make_response(original, headers={"X-Test": "1"})
    assert wrapped.headers["x-test"] == "1"


def test_route_static_facade_methods() -> None:
    from almasix.routing.router import Router, set_router

    router = Router()
    set_router(router)
    Route.post("/p", lambda: None)
    Route.put("/u", lambda: None)
    Route.patch("/h", lambda: None)
    Route.delete("/d", lambda: None)
    Route.options("/o", lambda: None)
    Route.any("/any", lambda: None)
    Route.match(["GET"], "/m", lambda: None)
    with Route.group(prefix="/g"):
        Route.get("/x", lambda: None)
    assert any(route.uri == "/g/x" for route in router.routes)
