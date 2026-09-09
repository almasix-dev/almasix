"""Additional Request / invoke edge coverage for M2 parity."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile
from starlette.requests import Request as StarletteRequest

from almasix.framework import Application
from almasix.http import Request, UploadedFile
from almasix.http.kernel import HttpKernel
from almasix.http.request import _is_empty
from almasix.routing import Route, Router, set_router
from tests.support import purge_generated_app_modules
from tests.test_m2_request import _receive, _starlette_request


@pytest.mark.asyncio
async def test_uploaded_file_wrapper_and_multi_values() -> None:
    upload = UploadFile(filename="a.txt", file=__import__("io").BytesIO(b"abc"))
    wrapped = UploadedFile(upload)
    assert wrapped.name == "a.txt"
    assert wrapped.content_type is None
    assert wrapped.size is None or isinstance(wrapped.size, int)
    assert wrapped.raw is upload
    assert await wrapped.read() == b"abc"
    await wrapped.seek(0)
    assert await wrapped.read() == b"abc"

    boundary = "----bound"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tags"\r\n\r\n'
        "a\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tags"\r\n\r\n'
        "b\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="docs"; filename="one.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "1\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="docs"; filename="two.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "2\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    raw = _starlette_request(
        method="POST",
        query="q=1&q=2",
        headers=[(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        body=body,
    )
    request = await Request.create(raw)
    await request._hydrate()
    assert request.query("q") == ["1", "2"]
    assert request.post("tags") == ["a", "b"]
    docs = request.file("docs")
    assert isinstance(docs, list) and len(docs) == 2
    assert request.has_file("docs")
    assert request.file("missing", "x") == "x"
    assert not request.has_file("nope")


@pytest.mark.asyncio
async def test_request_coercion_cookies_and_mapping() -> None:
    raw = _starlette_request(
        method="POST",
        query="",
        headers=[
            (b"content-type", b"application/json"),
            (b"cookie", b"session=abc"),
        ],
        body=b'["not-an-object"]',
    )
    # no client
    raw.scope["client"] = None
    request = await Request.create(raw)
    assert request.ip() is None
    assert request.cookie("session") == "abc"
    assert request.cookies.get("session") == "abc"
    assert request.json() == ["not-an-object"]
    assert request.json("x", "d") == "d"
    assert request.float("missing", 1.5) == 1.5
    assert request.boolean("missing", True) is True
    assert request.integer("missing", 9) == 9
    assert request.string("missing", "z") == "z"
    assert request.input() == {}
    assert request.only(["a"]) == {}
    with pytest.raises(KeyError):
        _ = request["nope"]
    assert "nope" not in request
    assert "Request POST" in repr(request)
    assert _is_empty(None)
    assert _is_empty("")
    assert _is_empty([])
    assert _is_empty({})
    assert not _is_empty("x")

    request.merge({"n": "2.5", "flag": "yes", "empty": "", "bad": "x"})
    assert request.float("n") == 2.5
    assert request.boolean("flag") is True
    assert not request.filled("empty")
    assert request.integer("bad", 0) == 0
    assert request.float("bad", 0.0) == 0.0
    assert request.string("empty") == ""
    assert request.boolean("empty") is False


@pytest.mark.asyncio
async def test_kernel_rejects_unresolvable_param() -> None:
    app = Application()
    kernel = HttpKernel(app, Router())

    def needs_unknown(orphan: str) -> dict[str, str]:
        return {"orphan": orphan}

    request = Request(
        StarletteRequest(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/",
                "raw_path": b"/",
                "query_string": b"",
                "headers": [],
            }
        ),
        hydrated=True,
    )
    with pytest.raises(TypeError, match="Cannot resolve"):
        await kernel._invoke(needs_unknown, request)


def test_controller_di_and_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "DI", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)

    async def with_default(limit: int = 5) -> dict[str, int]:
        return {"limit": limit}

    Route.get("/default", with_default)
    app._routes_loaded = True
    client = TestClient(app.asgi)
    assert client.get("/default").json() == {"limit": 5}


@pytest.mark.asyncio
async def test_urlencoded_form() -> None:
    raw = StarletteRequest(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/f",
            "raw_path": b"/f",
            "query_string": b"",
            "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
            "client": ("127.0.0.1", 1),
            "server": ("test", 80),
        },
        receive=_receive(b"name=almasix&empty="),
    )
    request = await Request.create(raw)
    assert request.post("name") == "almasix"
    assert request.has("empty")
    assert not request.filled("empty")
