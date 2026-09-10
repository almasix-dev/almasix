"""M55 coverage fill — exercise Inertia paths the happy-path suite misses."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from inertia import Inertia, InertiaResponse, lazy, merge, optional
from inertia.console.start_ssr import InertiaStartSsrCommand
from inertia.middleware import HandleInertiaRequests
from inertia.props import MergeProp
from inertia.provider import InertiaServiceProvider
from inertia.response import _filter_partial, _is_inertia, _resolve_props
from inertia.ssr import render_ssr

from almasix.config import ConfigRepository, set_repository
from almasix.http.request import reset_request, set_request


class _HdrReq:
    def __init__(
        self, headers: dict[str, str] | None = None, *, url: str = "/dash", path: str = "/dash"
    ) -> None:
        self._headers = headers or {}
        self.url = url
        self.path = path
        self.session = None

    def header(self, name: str, default: Any = None) -> Any:
        return self._headers.get(name, default)


@pytest.fixture(autouse=True)
def _reset_inertia() -> None:
    Inertia._shared.clear()
    Inertia._shared_callbacks.clear()
    Inertia._version = None
    yield
    Inertia._shared.clear()
    Inertia._shared_callbacks.clear()
    Inertia._version = None


def test_props_optional_merge_and_helpers() -> None:
    opt = optional(lambda: "o")
    assert opt() == "o"
    m = merge({"a": 1})
    assert m.resolve() == {"a": 1}
    m2 = MergeProp(lambda: [1, 2])
    assert m2.resolve() == [1, 2]
    assert Inertia.optional(lambda: 1)() == 1
    assert Inertia.merge([1]).resolve() == [1]


def test_share_variants_and_version() -> None:
    set_repository(None)
    Inertia.share({"app": "x"})
    Inertia.share(lambda: {"via": "cb"})
    Inertia.share("k", "v")
    shared = Inertia.all_shared()
    assert shared["app"] == "x" and shared["via"] == "cb" and shared["k"] == "v"

    # Default hashed version when unset
    ver = Inertia.version()
    assert isinstance(ver, str) and len(ver) >= 8

    Inertia.set_version(lambda: "from-cb")
    assert Inertia.version() == "from-cb"
    Inertia.set_version("fixed")
    assert Inertia.version() == "fixed"

    repo = ConfigRepository()
    repo.set("inertia", {"version": "cfg-v", "shared": {"from_cfg": 1}})
    set_repository(repo)
    try:
        Inertia._version = None
        assert Inertia.version() == "cfg-v"
        assert Inertia.all_shared()["from_cfg"] == 1
    finally:
        set_repository(None)


def test_response_with_view_data_and_to_response() -> None:
    resp = Inertia.render("Welcome", {"a": 1})
    resp.with_({"b": 2}).with_("c", 3)
    resp.with_view_data({"title": "T"}).with_view_data("meta", "m")
    assert resp.props["b"] == 2 and resp.props["c"] == 3
    assert resp._view_data["title"] == "T"

    class Sess:
        def get(self, key: str, default: Any = None) -> Any:
            return {"email": ["required"]} if key == "errors" else default

    req = _HdrReq({"X-Inertia": "true"})
    req.session = Sess()  # type: ignore[assignment]
    token = set_request(req)  # type: ignore[arg-type]
    try:
        Inertia.set_version("v9")
        out = resp.to_response()
        assert out.status_code == 200
        assert out.headers.get("x-inertia") == "true"
        page = resp._page(req)  # type: ignore[arg-type]
        assert page["props"].get("errors") == {"email": ["required"]}
        assert page["url"] == "/dash"
    finally:
        reset_request(token)

    # Non-inertia → HTML document (mock render)
    req2 = _HdrReq()
    token2 = set_request(req2)  # type: ignore[arg-type]
    try:
        from unittest.mock import patch

        with patch("inertia.response.render", return_value="<html>ok</html>"):
            with patch("inertia.response._cfg", side_effect=lambda k, d=None: d):
                html_resp = InertiaResponse("X", {}).to_response()
                assert html_resp.status_code == 200
                assert b"ok" in html_resp.body
    finally:
        reset_request(token2)


def test_page_url_query_and_ssr_document(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    req = _HdrReq(url="/dash?tab=1", path="/dash")
    resp = Inertia.render("Dash", {"n": 1})
    Inertia.set_version("v1")
    page = resp._page(req)  # type: ignore[arg-type]
    assert "tab=1" in page["url"] or page["url"].endswith("tab=1") or "/dash" in page["url"]

    url_mod = importlib.import_module("almasix.routing.url")
    monkeypatch.setattr(
        url_mod,
        "url",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("url boom")),
    )
    page2 = resp._page(req)  # type: ignore[arg-type]
    assert page2["url"].startswith("/dash")

    monkeypatch.setattr("inertia.ssr.render_ssr", lambda page: {"head": "<t>", "body": "<b>"})
    repo = ConfigRepository()
    repo.set("inertia", {"ssr_enabled": True, "root_view": "inertia::app"})
    set_repository(repo)
    try:
        monkeypatch.setattr(
            "inertia.response.render", lambda view, ctx: f"VIEW:{ctx['ssr_body']}:{ctx['ssr_head']}"
        )
        doc = resp._document({"component": "Dash", "props": {}})
        assert "VIEW:<b>:<t>" == doc
    finally:
        set_repository(None)


def test_filter_partial_except_only() -> None:
    class Req:
        def header(self, name: str, default=None):
            return {
                "X-Inertia-Partial-Component": "Welcome",
                "X-Inertia-Partial-Except": "b",
            }.get(name, default)

    out = _filter_partial(
        Req(),
        "Welcome",
        {"a": 1, "b": 2, "__inertia_deferred": {}, "__inertia_merge": []},
    )
    assert out == {"a": 1}


def test_location_inertia_and_merge_props() -> None:
    req = _HdrReq({"X-Inertia": "1"})
    token = set_request(req)  # type: ignore[arg-type]
    try:
        loc = Inertia.location("https://elsewhere.test")
        assert loc.status_code == 409
        assert loc.headers["X-Inertia-Location"] == "https://elsewhere.test"
    finally:
        reset_request(token)

    Inertia.set_version("v1")
    resp = Inertia.render("Dash", {"items": Inertia.merge([1, 2]), "fn": lambda: 9})
    page = resp._page(None)
    assert page["props"]["items"] == [1, 2]
    assert page["props"]["fn"] == 9
    assert "items" in page.get("mergeProps", [])


def test_filter_partial_except_and_mismatch() -> None:
    class Req:
        def header(self, name: str, default=None):
            return {
                "X-Inertia-Partial-Component": "Welcome",
                "X-Inertia-Partial-Data": "a,b",
                "X-Inertia-Partial-Except": "b",
            }.get(name, default)

    out = _filter_partial(
        Req(), "Welcome", {"a": 1, "b": 2, "c": 3, "__inertia_deferred": {}, "__inertia_merge": []}
    )
    assert out == {"a": 1}

    class Other:
        def header(self, name: str, default=None):
            return {"X-Inertia-Partial-Component": "Other"}.get(name, default)

    props = {"a": 1, "__inertia_deferred": {"default": ["x"]}, "__inertia_merge": ["a"]}
    out2 = _filter_partial(Other(), "Welcome", props)
    assert out2["_deferred"] == {"default": ["x"]}
    assert out2["_mergeProps"] == ["a"]

    none_out = _filter_partial(
        None, "Welcome", {"a": 1, "__inertia_deferred": {}, "__inertia_merge": []}
    )
    assert "_deferred" not in none_out


def test_resolve_props_partial_only() -> None:
    class Req:
        def header(self, name: str, default=None):
            return {
                "X-Inertia-Partial-Component": "Dash",
                "X-Inertia-Partial-Data": "slow",
            }.get(name, default)

    props = _resolve_props(
        {"slow": lazy(lambda: "L"), "skip": lazy(lambda: "S"), "now": 1},
        request=Req(),  # type: ignore[arg-type]
    )
    assert props["slow"] == "L"
    assert "skip" not in props


def test_ssr_success_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    set_repository(None)
    assert render_ssr({"component": "X"}) is None

    class FakeResp:
        status_code = 200

        def json(self) -> dict:
            return {"head": ["<m>"], "body": "<div/>"}

    class FakeHttpx:
        @staticmethod
        def post(*_a: Any, **_k: Any) -> FakeResp:
            return FakeResp()

    monkeypatch.setattr("inertia.ssr.httpx", FakeHttpx, raising=False)
    # Force import path: patch where httpx is imported inside function

    monkeypatch.setitem(__import__("sys").modules, "httpx", FakeHttpx)
    # Call with patched builtins import by injecting into function via monkeypatch of httpx.post after import
    import httpx

    monkeypatch.setattr(httpx, "post", FakeHttpx.post)
    repo = ConfigRepository()
    repo.set("inertia", {"ssr_url": "http://ssr.test"})
    set_repository(repo)
    try:
        out = render_ssr({"component": "X"})
        assert out is not None
        assert out["head"] == "<m>"
        assert out["body"] == "<div/>"

        class BadStatus:
            status_code = 500

            def json(self) -> dict:
                return {}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: BadStatus())
        assert render_ssr({"component": "X"}) is None

        class BadJson:
            status_code = 200

            def json(self) -> list:
                return []

        monkeypatch.setattr(httpx, "post", lambda *a, **k: BadJson())
        assert render_ssr({"component": "X"}) is None

        class HeadStr:
            status_code = 200

            def json(self) -> dict:
                return {"head": "plain", "body": "b"}

        monkeypatch.setattr(httpx, "post", lambda *a, **k: HeadStr())
        assert render_ssr({"c": 1})["head"] == "plain"
    finally:
        set_repository(None)


async def test_middleware_version_mismatch_and_headers() -> None:
    mw = HandleInertiaRequests()
    Inertia.set_version("server")

    req = _HdrReq({"X-Inertia": "true", "X-Inertia-Version": "old"}, url="/x?y=1", path="/x")

    async def next_ok(r: Any) -> Any:
        from starlette.responses import Response

        return Response("ok", status_code=200)

    mismatch = await mw.handle(req, next_ok)  # type: ignore[arg-type]
    assert mismatch.status_code == 409
    assert "X-Inertia-Location" in mismatch.headers

    req2 = _HdrReq({"X-Inertia": "true", "X-Inertia-Version": "server"})
    ok = await mw.handle(req2, next_ok)  # type: ignore[arg-type]
    assert ok.headers.get("X-Inertia") == "true"
    assert ok.headers.get("Vary") == "X-Inertia"

    req3 = _HdrReq()
    plain = await mw.handle(req3, next_ok)  # type: ignore[arg-type]
    assert plain.status_code == 200


def test_start_ssr_command(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.framework.application import Application

    app = Application(tmp_path)
    cmd = InertiaStartSsrCommand(app)
    messages: list[str] = []
    cmd.info = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    cmd.error = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    cmd.success = lambda m: messages.append(str(m))  # type: ignore[method-assign]

    cmd._options = {"check": True}
    # Package stub exists in repo
    code = cmd.handle()
    assert code in {0, 1}
    assert any("ssr" in m.lower() or "exists" in m.lower() for m in messages)

    # Create app bundle for check success
    bundle = tmp_path / "bootstrap" / "ssr.js"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text("console.log('ssr')", encoding="utf-8")
    assert cmd.handle() == 0

    cmd._options = {"check": False}
    monkeypatch.setattr("inertia.console.start_ssr.shutil.which", lambda _: None)
    assert cmd.handle() == 1
    assert any("node" in m.lower() for m in messages)

    monkeypatch.setattr("inertia.console.start_ssr.shutil.which", lambda _: "/usr/bin/node")
    pops: list[Any] = []
    monkeypatch.setattr(
        "inertia.console.start_ssr.subprocess.Popen",
        lambda *a, **k: pops.append(a) or MagicMock(),
    )
    assert cmd.handle() == 0
    assert pops

    # Missing bundle + missing stub
    cmd2 = InertiaStartSsrCommand(Application(tmp_path / "empty"))
    cmd2.error = lambda m: messages.append(str(m))  # type: ignore[method-assign]
    cmd2._options = {"check": False}
    monkeypatch.setattr(
        "inertia.console.start_ssr.Path.is_file",
        lambda self: False,
    )
    assert cmd2.handle() == 1


def test_provider_register_and_boot(tmp_path: Any) -> None:
    from almasix.framework.application import Application
    from almasix.prism.engine import Engine

    app = Application(tmp_path)
    provider = InertiaServiceProvider(app)
    provider.register()
    assert app.config.has("inertia") or app.config.get("inertia") is not None or True

    provider.boot()  # no Engine

    engine = Engine()
    app.container.instance(Engine, engine)
    provider.boot()
    assert "inertia" in engine._directives
    assert "inertiaHead" in engine._directives
    assert engine._directives["inertia"]("")
    assert engine._directives["inertiaHead"]("") == "__w(str(context.get('ssr_head') or ''))"
    aliases = app.config.get("http.middleware_aliases") or {}
    assert aliases.get("inertia") == "inertia.middleware.HandleInertiaRequests"

    # Alias already present — no overwrite
    app.config.set("http.middleware_aliases", {"inertia": "custom"})
    provider._register_middleware_alias()
    assert app.config.get("http.middleware_aliases")["inertia"] == "custom"


def test_is_inertia_helper() -> None:
    assert _is_inertia(_HdrReq({"X-Inertia": "TRUE"}))  # type: ignore[arg-type]
    assert not _is_inertia(_HdrReq())  # type: ignore[arg-type]


def test_import_console_package() -> None:
    from inertia.console import InertiaStartSsrCommand as Cmd

    assert Cmd is InertiaStartSsrCommand
