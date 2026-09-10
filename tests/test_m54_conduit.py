"""Unit tests for almasix.conduit (M54)."""

from __future__ import annotations

import pytest

from almasix.conduit import Component, Conduit
from almasix.conduit.mechanism import checksum, snapshot, verify_checksum
from almasix.conduit.parity import PARITY, parity_summary
from almasix.conduit.uploads import store_upload


class _Counter(Component):
    count = 0
    label = "x"

    def increment(self) -> None:
        self.count += 1

    def render(self) -> str:
        return "conduit::counter"


@pytest.fixture(autouse=True)
def _register() -> None:
    Conduit.register("counter", _Counter)


def test_import_namespace() -> None:
    from almasix.conduit import Component as C
    from almasix.conduit import conduit

    assert C is Component
    assert callable(conduit)


def test_snapshot_checksum_roundtrip() -> None:
    c = Conduit.component("counter")
    c.conduit_id = "abc"
    c.mount()
    snap = snapshot(c)
    assert verify_checksum(c, snap["serverMemo"])
    assert snap["serverMemo"]["checksum"] == checksum(
        {"data": {"count": 0, "label": "x"}, "name": "counter", "id": "abc"}
    )


def test_method_call_and_toggle() -> None:
    c = Conduit.component("counter")
    c.call("increment")
    assert c.count == 1
    c.dispatch("ticked", count=c.count)
    assert c.take_dispatches()[0]["params"]["count"] == 1


def test_query_string_binding() -> None:
    class Q(Component):
        page = 1
        query_string = ["page"]

        def render(self) -> str:
            return "conduit::counter"

    Conduit.register("q", Q)
    c = Conduit.component("q")
    c.apply_query_string({"page": "3"})
    assert c.page == 3
    assert c.sync_query_string() == {"page": 3}


def test_parity_matrix_gate() -> None:
    assert len(PARITY) >= 35
    summary = parity_summary()
    assert summary["complete"] == len(PARITY)
    assert summary["partial"] == 0
    assert summary["planned"] == 0


def test_store_upload(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("almasix.conduit.uploads._cfg", lambda key, default=None: str(tmp_path))

    class F:
        filename = "hi.txt"

        class file:
            @staticmethod
            def read() -> bytes:
                return b"hello"

    path = store_upload(F())
    assert "hi.txt" in path


def test_public_paths_honor_app_base_path() -> None:
    """Livewire-class bug: hardcoded /conduit breaks under /my-app. We never do that."""
    from almasix.conduit.mechanism import conduit_assets_script, conduit_public_paths
    from almasix.config import ConfigRepository, set_repository
    from almasix.routing.signing import has_valid_signature

    repo = ConfigRepository()
    repo.set("app.url", "http://example.test")
    repo.set("app.key", "base64:test-conduit-signing-key")
    repo.set("app.base_path", "/my-app")
    repo.set("conduit", {"endpoint": "/conduit/update", "asset_url": "/conduit/conduit.js"})
    set_repository(repo)
    try:
        paths = conduit_public_paths()
        assert paths["base"] == "/my-app"
        assert paths["endpoint"].startswith("/my-app/conduit/update?")
        assert "signature=" in paths["endpoint"]
        assert "expires=" in paths["endpoint"]
        # Signature is relative to the internal path (mount strips /my-app).
        internal = "/conduit/update?" + paths["endpoint"].split("?", 1)[1]
        assert has_valid_signature(internal, absolute=False)
        html = conduit_assets_script()
        assert "window.__CONDUIT__=" in html
        assert "/my-app/conduit/update?" in html
        assert 'src="/my-app/conduit/conduit.js"' in html
        assert "signature=" in html
    finally:
        set_repository(None)


def test_public_paths_root_hosting() -> None:
    from almasix.conduit.mechanism import conduit_public_paths
    from almasix.config import ConfigRepository, set_repository
    from almasix.routing.signing import has_valid_signature

    repo = ConfigRepository()
    repo.set("app.url", "http://example.test")
    repo.set("app.key", "base64:test-conduit-signing-key")
    repo.set("app.base_path", "")
    set_repository(repo)
    try:
        paths = conduit_public_paths()
        assert paths["base"] == ""
        assert paths["endpoint"].startswith("/conduit/update?")
        assert has_valid_signature(paths["endpoint"], absolute=False)
    finally:
        set_repository(None)


def test_locked_property_rejects_client_set() -> None:
    class LockedComp(Component):
        count = 0
        _locked = ("count",)

        def render(self) -> str:
            return "<div></div>"

    Conduit.register("locked", LockedComp)
    c = Conduit.component("locked")
    with pytest.raises(AttributeError, match="locked"):
        c.set_property("count", 9)


def test_inline_html_render() -> None:
    class Inline(Component):
        def render(self) -> str:
            return "<div class='inline'>hi</div>"

    Conduit.register("inline", Inline)
    from almasix.conduit.mechanism import render_html

    c = Conduit.component("inline")
    assert "inline" in render_html(c)
