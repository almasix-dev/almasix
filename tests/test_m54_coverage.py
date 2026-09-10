"""M54 coverage fill — exercise Conduit paths the happy-path suite misses."""

from __future__ import annotations

from typing import Any

import pytest

from almasix.conduit import (
    Component,
    Computed,
    Conduit,
    Locked,
    Modelable,
    On,
    WithPagination,
    parity_rows,
)
from almasix.conduit.attributes import locked_property_names
from almasix.conduit.commands.make_conduit import MakeConduitCommand
from almasix.conduit.demo.counter import Counter as DemoCounter
from almasix.conduit.features import nest
from almasix.conduit.manager import ComponentRegistry, _studly
from almasix.conduit.mechanism import (
    conduit_assets_script,
    embed_component,
    handle_update,
    hydrate_from_snapshot,
    render_html,
    snapshot,
    verify_checksum,
    wrap_root,
)
from almasix.conduit.provider import ConduitServiceProvider
from almasix.conduit.routing import mount_full_page, resolve_component
from almasix.conduit.signing import (
    public_signed_update_url,
    sign_update_url,
    update_path,
    urlunsplit_path_query,
    verify_update_request_url,
)
from almasix.conduit.uploads import store_upload
from almasix.config import ConfigRepository, set_repository
from almasix.validation.form_request import ValidationException


def _signing_repo(**extra: Any) -> ConfigRepository:
    repo = ConfigRepository()
    repo.set("app.url", "http://example.test")
    repo.set("app.key", "base64:test-conduit-signing-key")
    repo.set("app.base_path", "")
    repo.set(
        "conduit", {"endpoint": "/conduit/update", "asset_url": "/conduit/conduit.js", **extra}
    )
    return repo


class _Req:
    def __init__(
        self,
        payload: Any = None,
        *,
        post: Any = None,
        query: dict | None = None,
        path: str = "/conduit/update",
    ) -> None:
        self._payload = payload
        self._post = post
        self._query = query or {}
        self.path = path

    def json(self) -> Any:
        return self._payload

    def post(self) -> Any:
        return self._post

    def query(self) -> dict:
        return self._query


class _Html(Component):
    count = 0
    label = "x"
    flag = False
    page = 1

    def increment(self) -> None:
        self.count += 1

    def boom(self) -> None:
        self.validate({"label": "required"})

    def render(self) -> str:
        return f"<div class='c'>{self.count}</div>"


@pytest.fixture(autouse=True)
def _fresh_registry() -> None:
    Conduit._registry = ComponentRegistry()
    Conduit.register("html", _Html)
    yield
    Conduit._registry = None


def test_parity_rows_sorted() -> None:
    from almasix.conduit.parity import parity_summary

    rows = parity_rows()
    assert rows == sorted(rows)
    assert len(rows) >= 35
    summary = parity_summary()
    assert summary["complete"] == len(rows)


def test_attributes_and_locked_names() -> None:
    @Computed
    def total(self) -> int:
        return 1

    @Computed(persist=True)
    def cached(self) -> int:
        return 2

    @Locked
    def secret(self) -> None:
        return None

    @On("saved")
    def on_saved(self) -> None:
        return None

    @Modelable
    def value(self) -> int:
        return 0

    assert total._conduit_computed is True
    assert cached._conduit_computed_persist is True
    assert secret._conduit_locked is True
    assert on_saved._conduit_on == "saved"
    assert value._conduit_modelable is True

    marker = Locked(0)
    assert marker._conduit_locked is True
    assert marker.default == 0

    class Marked(Component):
        pin = Locked(9)
        _locked = ("count",)
        count = 0

        @Locked
        def token(self) -> str:
            return "t"

        def render(self) -> str:
            return "<div></div>"

    names = locked_property_names(Marked)
    assert "pin" in names and "count" in names and "token" in names


def test_demo_counter_methods() -> None:
    c = DemoCounter()
    c.increment()
    c.decrement()
    c.reset()
    assert c.count == 0
    assert c.render() == "conduit::counter"


def test_with_pagination_query_and_sequence() -> None:
    class Paged(_Html, WithPagination):
        per_page = 2

    p = Paged()
    p.page = 2
    p.reset_page()
    assert p.page == 1
    p.updating_page()

    class Q:
        def paginate(self, size: int, *, page: int = 1) -> dict:
            return {"size": size, "page": page}

    assert p.paginate(Q(), per_page=5) == {"size": 5, "page": 1}
    p.page = 2
    simple = p.paginate([1, 2, 3, 4, 5], per_page=2)
    assert simple.items == [3, 4]
    assert simple.total == 5
    assert simple.last_page == 3


def test_component_lifecycle_aliases_and_errors() -> None:
    c = Conduit.component("html", count=2)
    assert c.count == 2
    c.flux_id = "fid"
    assert c.conduit_id == "fid"
    assert c.flux_id == "fid"
    c.flux_name = "html"
    assert c.conduit_name == "html" and c.flux_name == "html"
    assert c.errors == {}

    c.add_error("x", "bad")
    assert c.get_error_bag()["x"] == ["bad"]
    c.reset_error_bag("x")
    assert c.get_error_bag() == {}
    c.add_error("y", "no")
    c.reset_error_bag()
    assert c.get_error_bag() == {}

    c.skip_render()
    assert c.should_render() is False
    c.reset_skip_render()
    c.renderless()
    assert c.should_render() is False
    c.reset_skip_render()
    c.target_island("stats")
    assert c.take_island() == "stats"
    assert c.take_island() is None

    c.dispatch_self("ping", n=1)
    c.dispatch_to("other", "pong", n=2)
    c.js("alert(1)")
    events = c.take_dispatches()
    assert events[0]["to"] == "self"
    assert events[1]["to"] == "other"
    assert events[2]["event"] == "__js"

    c.toggle("flag")
    assert c.flag is True
    with pytest.raises(AttributeError):
        c.toggle("missing")
    with pytest.raises(AttributeError):
        c.set_property("missing", 1)
    with pytest.raises(AttributeError):
        c.call("mount")
    with pytest.raises(AttributeError):
        c.call("nope")
    c.call("$toggle", "flag")
    assert c.flag is False

    def ago(self) -> str:
        return "__coro__"

    c.ago = ago.__get__(c, type(c))  # type: ignore[method-assign]
    import almasix.conduit.component as comp_mod

    real_iscoro = comp_mod.inspect.iscoroutine
    comp_mod.inspect.iscoroutine = lambda obj: obj == "__coro__" or real_iscoro(obj)  # type: ignore[method-assign]
    try:
        with pytest.raises(TypeError, match="synchronous"):
            c.call("ago")
    finally:
        comp_mod.inspect.iscoroutine = real_iscoro  # type: ignore[method-assign]

    with pytest.raises(NotImplementedError):
        Component().render()

    class Islands(_Html):
        island_views = {"stats": "conduit.stats"}

        def render_island(self, name: str) -> str | None:
            return super().render_island(name)

    i = Islands()
    assert i.render_island("stats") == "conduit.stats"
    assert i.render_island("missing") is None


def test_validate_success_and_failure() -> None:
    from pydantic import BaseModel, Field

    class LabelRules(BaseModel):
        label: str = Field(min_length=1)
        count: int = 0
        flag: bool = False
        page: int = 1

    class Form(_Html):
        rules = LabelRules

        def save(self) -> dict:
            return self.validate()

    ok = Form()
    ok.label = "hi"
    assert ok.save()["label"] == "hi"
    assert ok.validate(None)["label"] == "hi"

    bad = Form()
    bad.label = ""
    with pytest.raises(ValidationException):
        bad.save()
    assert "label" in bad.get_error_bag()

    bare = _Html()
    assert bare.validate() == bare.get_public_properties()

    # Explicit ValidationException path used by wire calls
    class Boom(_Html):
        def save(self) -> None:
            raise ValidationException({"label": ["nope"]})

    Conduit.register("boom", Boom)


def test_query_string_dict_and_coercion() -> None:
    class Q(Component):
        page = 1
        flag = False
        label = "a"
        query_string = {"page": "p", "flag": "on", "label": "q"}

        def render(self) -> str:
            return "<div></div>"

    Conduit.register("qmap", Q)
    c = Conduit.component("qmap")
    assert c.query_string_map() == {"page": "p", "flag": "on", "label": "q"}
    c.apply_query_string({"p": "4", "on": "yes", "q": "z"})
    assert c.page == 4 and c.flag is True and c.label == "z"
    c.apply_query_string({"p": "nope"})
    assert c.page == "nope"
    assert c.sync_query_string()["p"] == "nope"


def test_manager_register_resolve_and_studly(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(TypeError):
        Conduit.registry().register("bad", object)  # type: ignore[arg-type]

    with pytest.raises(KeyError, match="Invalid"):
        Conduit.registry().resolve("9bad")

    with pytest.raises(KeyError, match="not found"):
        Conduit.registry().resolve("totally.missing.thing")

    assert _studly("my-counter") == "MyCounter"
    assert Conduit.mount("html").startswith("<div")
    from almasix.conduit.manager import conduit as embed

    assert "wire:id=" in embed("html")
    Conduit._registry = None
    assert Conduit.registry() is not None

    # Namespace discovery via importlib
    pkg = tmp_path / "cov_conduit_ns"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "widget.py").write_text(
        "from almasix.conduit import Component\n"
        "class Widget(Component):\n"
        "    def render(self):\n"
        "        return '<span>w</span>'\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    Conduit.registry().add_namespace("cov_conduit_ns")
    Conduit.registry().add_namespace("cov_conduit_ns")  # duplicate no-op
    cls = Conduit.registry().resolve("widget")
    assert cls.__name__ == "Widget"
    assert Conduit.component("widget").render() == "<span>w</span>"

    # Import succeeds but attribute is not a Component subclass → keep searching
    (pkg / "plain.py").write_text("class Plain: pass\n", encoding="utf-8")
    with pytest.raises(KeyError):
        Conduit.registry().resolve("plain")


def test_features_nest() -> None:
    parent = Conduit.component("html")
    html = nest(parent, "html", count=3)
    assert "wire:id=" in html
    assert len(parent._Component__children) == 1  # type: ignore[attr-defined]

    class Bare:
        pass

    nested = nest(Bare(), "html")  # type: ignore[arg-type]
    assert "wire:id=" in nested


def test_uploads_all_shapes(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("almasix.conduit.uploads._cfg", lambda key, default=None: str(tmp_path))

    class Readable:
        def read(self) -> bytes:
            return b"via-read"

    class Named:
        filename = "a.txt"
        file = type("F", (), {"read": staticmethod(lambda: b"via-file")})()

    assert "a.txt" in store_upload(Named())
    read_path = store_upload(Readable())
    assert (tmp_path / read_path).read_bytes() == b"via-read"
    raw_path = store_upload(b"raw-bytes")
    assert (tmp_path / raw_path).read_bytes() == b"raw-bytes"
    empty_path = store_upload(object())
    assert (tmp_path / empty_path).read_bytes() == b""

    # relative_to ValueError when dest is outside base → return absolute path
    from pathlib import Path as RealPath

    def boom(self: RealPath, *_args: Any, **_kwargs: Any) -> RealPath:
        raise ValueError("outside")

    monkeypatch.setattr(RealPath, "relative_to", boom)
    abs_path = store_upload(b"abs")
    assert "conduit-uploads" in abs_path


def test_uploads_cfg_without_repository() -> None:
    set_repository(None)
    from almasix.conduit import uploads as up

    assert up._cfg("missing.key", "d") == "d"


def test_signing_paths_and_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    set_repository(None)
    from almasix.conduit import signing as sig

    assert sig._cfg("nope", 1) == 1

    repo = _signing_repo(endpoint="conduit/update")  # missing leading slash
    set_repository(repo)
    try:
        assert update_path() == "/conduit/update"
        signed = sign_update_url(minutes=5)
        assert "signature=" in signed
        assert verify_update_request_url(signed)
        assert verify_update_request_url(f"http://example.test{signed}")
        public = public_signed_update_url(minutes=5)
        assert public.startswith("/conduit/update?")
        assert urlunsplit_path_query("/x", "") == "/x"
        assert urlunsplit_path_query("", "") == "/"
        assert urlunsplit_path_query("/x", "a=1") == "/x?a=1"
        monkeypatch.setattr(sig, "sign_update_url", lambda minutes=None: "/conduit/update")
        assert public_signed_update_url() == "/conduit/update"
    finally:
        set_repository(None)


def test_uploads_cfg_none_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.conduit import uploads as up

    repo = ConfigRepository()
    repo.set("filesystem.disks.local.root", None)
    set_repository(repo)
    try:
        assert up._cfg("filesystem.disks.local.root", "fallback") == "fallback"
    finally:
        set_repository(None)


def test_locked_property_via_marker_and_classmethod() -> None:
    class Marked(Component):
        secret = Locked(0)
        count = 0

        @classmethod
        def factory(cls) -> str:
            return "x"

        def render(self) -> str:
            return "<div></div>"

    Conduit.register("marked", Marked)
    c = Conduit.component("marked")
    assert "secret" in locked_property_names(Marked)
    with pytest.raises(AttributeError, match="locked"):
        c.set_property("secret", 1)
    assert "factory" not in Marked._public_property_names()
    c.dispatch("x")
    assert c.take_dispatches()[0]["event"] == "x"


def test_mechanism_lazy_wrap_and_hydrate(monkeypatch: pytest.MonkeyPatch) -> None:
    class Lazy(_Html):
        lazy = True
        lazy_placeholder = None

    class Defer(_Html):
        defer = True

    Conduit.register("lazy", Lazy)
    Conduit.register("defer", Defer)
    assert "wire:lazy" in embed_component(Conduit.component("lazy"))
    assert "wire:defer" in embed_component(Conduit.component("defer"))

    class LazyView(_Html):
        lazy = True
        lazy_placeholder = "conduit.ph"

    Conduit.register("lazyview", LazyView)
    monkeypatch.setattr("almasix.conduit.mechanism.render", lambda view, ctx: f"<p>{view}</p>")
    assert "conduit.ph" in embed_component(Conduit.component("lazyview"))

    c = Conduit.component("html")
    c.conduit_id = "id1"
    c.conduit_name = "html"
    assert "/>" in wrap_root(c, "<br/>", snapshot(c)) or "br" in wrap_root(c, "<br/>", snapshot(c))
    plain = wrap_root(c, "plain text", snapshot(c))
    assert plain.startswith("<div") and "plain text" in plain

    empty = Conduit.component("html")
    empty.skip_render()
    assert render_html(empty) == ""

    class Island(_Html):
        island_views = {"stats": "<b>stats</b>"}

        def render_island(self, name: str) -> str | None:
            return self.island_views.get(name)

    Conduit.register("island", Island)
    inst = Conduit.component("island")
    inst.conduit_id = "i1"
    html = render_html(inst, island="stats")
    assert "stats" in html

    memo = {"data": {"count": 5}, "errors": {"x": ["e"]}, "checksum": ""}
    hydrated = hydrate_from_snapshot("html", memo, {"id": "h1"})
    assert hydrated.count == 5
    assert hydrated.get_error_bag()["x"] == ["e"]


async def test_handle_update_branches() -> None:
    import json

    def body(resp: Any) -> dict:
        return json.loads(resp.body)

    repo = _signing_repo()
    set_repository(repo)
    try:
        bad = await handle_update(_Req(["not-a-dict"], post=["also-bad"]))  # type: ignore[arg-type]
        assert bad.status_code == 400

        bad2 = await handle_update(_Req(None, post=["x"]))  # type: ignore[arg-type]
        assert bad2.status_code == 400

        bad3 = await handle_update(_Req({"components": "nope"}))  # type: ignore[arg-type]
        assert bad3.status_code == 400

        missing = await handle_update(_Req({"fingerprint": {}, "serverMemo": {}}))
        assert b"missing" in missing.body

        # Fresh mount (empty checksum + empty data)
        fresh = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "html", "id": "f1"},
                    "serverMemo": {"data": {}, "checksum": ""},
                    "calls": [{"method": "increment"}],
                }
            )
        )
        assert fresh.status_code == 200
        assert fresh.body  # has JSON

        c = Conduit.component("html")
        c.conduit_id = "u1"
        c.conduit_name = "html"
        snap = snapshot(c)
        assert verify_checksum(c, snap["serverMemo"])
        assert verify_checksum(c, {**snap["serverMemo"], "checksum": ""}) is False

        mismatch = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "html", "id": "u1"},
                    "serverMemo": {**snap["serverMemo"], "checksum": "deadbeef" * 8},
                }
            )
        )
        assert b"checksum" in mismatch.body

        class Boom(_Html):
            def boom(self) -> None:
                raise ValidationException({"label": ["bad"]})

        Conduit.register("boomc", Boom)
        bc = Conduit.component("boomc")
        bc.conduit_id = "b1"
        bc.conduit_name = "boomc"
        bsnap = snapshot(bc)

        ok = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "boomc", "id": "b1", "path": "/old"},
                    "serverMemo": bsnap["serverMemo"],
                    "updates": [
                        ["count", 9],
                        {"name": "label", "value": "z"},
                        {"payload": {"name": "flag", "value": True}},
                        "skip-me",
                    ],
                    "calls": [
                        "skip",
                        {"method": "$set", "params": ["count", 10]},
                        {"method": "$set", "params": ["not_a_prop", 1]},
                        {"method": "$refresh"},
                        {"method": "$commit"},
                        {"method": "$load"},
                        {"method": "increment", "meta": {"renderless": True}},
                        {"path": "increment", "renderless": True},
                        {"method": None},
                        {"method": "boom"},
                        {"method": "increment", "island": "stats"},
                    ],
                    "island": "stats",
                },
                query={"page": "2"},
                path="/conduit/update",
            )
        )
        data = body(ok)
        assert "effects" in data
        assert data["effects"].get("endpoint")
        assert "label" in data["effects"].get("errors", {}) or "label" in data["serverMemo"].get(
            "errors", {}
        )

        # Batch components list
        batch = await handle_update(
            _Req(
                {
                    "components": [
                        {
                            "fingerprint": {"name": "html", "id": "b1"},
                            "serverMemo": {"data": {}, "checksum": ""},
                            "calls": [{"method": "increment"}],
                        }
                    ]
                }
            )
        )
        assert "components" in body(batch)

        # Island with dedicated view
        class IslandComp(_Html):
            def render_island(self, name: str) -> str | None:
                return f"<section>{name}</section>" if name else None

        Conduit.register("isle", IslandComp)
        ic = Conduit.component("isle")
        ic.conduit_id = "isle1"
        ic.conduit_name = "isle"
        isnap = snapshot(ic)
        island_resp = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "isle", "id": "isle1"},
                    "serverMemo": isnap["serverMemo"],
                    "islandTarget": "stats",
                    "calls": [],
                }
            )
        )
        assert "islands" in body(island_resp)["effects"] or "html" in body(island_resp)["effects"]

        # Island without dedicated view → wrap full html
        island_full = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "html", "id": "u2"},
                    "serverMemo": {"data": {}, "checksum": ""},
                    "island": "missing",
                    "calls": [],
                }
            )
        )
        effects = body(island_full)["effects"]
        assert effects.get("island") == "missing" or "html" in effects

        # Query-string sync effect
        class QS(_Html):
            query_string = ["page"]

        Conduit.register("qs", QS)
        q = Conduit.component("qs")
        q.conduit_id = "q1"
        q.conduit_name = "qs"
        qsnap = snapshot(q)
        qs_resp = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "qs", "id": "q1"},
                    "serverMemo": qsnap["serverMemo"],
                    "calls": [],
                },
                query={"page": "3"},
            )
        )
        assert body(qs_resp)["effects"].get("queryString", {}).get("page") == 3

        # Renderless skip html
        rl = await handle_update(
            _Req(
                {
                    "fingerprint": {"name": "html", "id": "rl1"},
                    "serverMemo": {"data": {}, "checksum": ""},
                    "calls": [{"method": "increment", "meta": {"renderless": True}}],
                }
            )
        )
        assert "html" not in body(rl)["effects"] or body(rl)["effects"].get("html") in (None, "")

        # Hydrate ignores unknown memo keys; embed with pre-set id
        hydrate_from_snapshot(
            "html",
            {"data": {"count": 1, "not_public": 9}, "errors": {"x": "one"}, "checksum": ""},
            {"id": "pre"},
        )
        preset = Conduit.component("html")
        preset.conduit_id = "already"
        assert "already" in embed_component(preset)
    finally:
        set_repository(None)


def test_render_html_view_name(monkeypatch: pytest.MonkeyPatch) -> None:
    class Named(_Html):
        def render(self) -> str:
            return "conduit.named"

    Conduit.register("named", Named)
    monkeypatch.setattr("almasix.conduit.mechanism.render", lambda view, ctx: f"<p>{view}</p>")
    html = render_html(Conduit.component("named"))
    assert "conduit.named" in html


def test_csp_safe_assets_script() -> None:
    repo = _signing_repo(csp_safe=True, coalesce_ms=32)
    set_repository(repo)
    try:
        html = conduit_assets_script()
        assert "alpinejs/csp" in html or "@alpinejs/csp" in html
        assert 'coalesceMs":32' in html.replace(" ", "")
    finally:
        set_repository(None)


def test_routing_resolve_component() -> None:
    assert resolve_component(_Html) is _Html
    assert resolve_component("html") is _Html
    imported = resolve_component("almasix.conduit.demo.counter.Counter")
    assert imported is DemoCounter
    with pytest.raises(KeyError):
        resolve_component("missingwidgetxyz")


async def test_mount_full_page_shell_and_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _signing_repo()
    set_repository(repo)
    try:

        class Dash(Component):
            title = "Dash"
            layout = "layouts.missing"
            count = 0

            def render(self) -> str:
                return "<main>dash</main>"

        action = mount_full_page(Dash, layout="layouts.nope")
        resp = await action()
        body = resp.body.decode() if hasattr(resp, "body") else str(resp)
        assert "dash" in body.lower() or "Dash" in body or "main" in body

        # Already registered class
        Conduit.register("dash", Dash)
        action2 = mount_full_page("dash")
        resp2 = await action2(count=2)
        assert resp2.status_code == 200

        monkeypatch.setattr(DemoCounter, "render", lambda self: "<div>demo-counter</div>")
        action3 = mount_full_page("almasix.conduit.demo.counter.Counter")
        resp3 = await action3()
        assert resp3.status_code == 200
        body3 = resp3.body.decode() if hasattr(resp3, "body") else str(resp3)
        # Full-page shell embeds the component (inline HTML or Prism view output).
        assert "demo-counter" in body3 or "wire:id=" in body3 or "<div" in body3

        # Exception during name discovery → falls back to class name
        real_registry = Conduit.registry
        calls = {"n": 0}

        def flaky_registry() -> Any:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return real_registry()

        Conduit.register("Dash", Dash)
        monkeypatch.setattr(Conduit, "registry", flaky_registry)
        action4 = mount_full_page(Dash)
        resp4 = await action4()
        assert resp4.status_code == 200
    finally:
        set_repository(None)


def test_make_conduit_command(tmp_path: Any) -> None:
    from almasix.framework.application import Application

    app = Application(tmp_path)
    cmd = MakeConduitCommand(app)
    cmd._arguments = {"name": ""}
    assert cmd.handle() == 1

    cmd._arguments = {"name": "Counter"}
    cmd._options = {"force": False}
    assert cmd.handle() == 0
    assert (tmp_path / "app" / "conduit" / "counter.py").is_file()
    assert (tmp_path / "resources" / "views" / "conduit" / "counter.prism.html").is_file()

    assert cmd.handle() == 1  # exists without force
    cmd._options = {"force": True}
    assert cmd.handle() == 0

    cmd._arguments = {"name": "Forms/Profile"}
    cmd._options = {"force": False}
    assert cmd.handle() == 0
    assert (tmp_path / "app" / "conduit" / "forms" / "profile.py").is_file()

    cmd._arguments = {"name": "forms.my-widget"}
    assert cmd.handle() == 0


def test_provider_register_merge_and_boot(tmp_path: Any) -> None:
    from almasix.framework.application import Application
    from almasix.prism.engine import Engine

    app = Application(tmp_path)
    provider = ConduitServiceProvider(app)
    provider.register()  # no prior conduit config
    assert app.config.has("conduit")

    app2 = Application(tmp_path / "b")
    app2.config.set("conduit", "not-a-dict")
    ConduitServiceProvider(app2).register()

    app3 = Application(tmp_path / "c")
    app3.config.set("conduit", {"endpoint": "/custom", "inject_assets": False})
    provider3 = ConduitServiceProvider(app3)
    provider3.register()
    assert app3.config.get("conduit")["endpoint"] == "/custom"
    assert "asset_url" in app3.config.get("conduit")
    provider3.register()  # Conduit already bound

    # Boot without Engine → soft return
    provider3.boot()

    engine = Engine()
    app3.container.instance(Engine, engine)
    provider4 = ConduitServiceProvider(app3)
    provider4.register()
    provider4.boot()
    assert "conduit" in engine._directives
    compiled = engine._directives["conduit"]("'counter'")
    assert "__conduit_render" in compiled
    scripts = engine._directives["conduitScripts"]("")
    assert "__conduit_scripts" in scripts
    assert "flux" in engine._directives
    ctx: dict[str, Any] = {}
    for _patterns, callback in engine._composers:
        callback(ctx)
    assert "__conduit_render" in ctx
    assert "conduit_scripts" not in ctx  # inject_assets False

    app3.config.set("conduit", {**app3.config.get("conduit"), "inject_assets": True})
    provider4._register_directives()
    ctx2: dict[str, Any] = {}
    for _patterns, callback in engine._composers[-1:]:
        callback(ctx2)
    assert "conduit_scripts" in ctx2 or "__conduit_scripts" in ctx2
