"""M26 smoke — broadcasting docs, the generators, the routes, the board."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
runner = CliRunner()


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m26_docs_and_sidebar_exist() -> None:
    page = ROOT / "website" / "src" / "content" / "docs" / "broadcasting.md"
    assert page.is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "broadcasting" in sidebar


def test_m26_a_scaffolded_app_can_broadcast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m26_scaffold", destination=tmp_path / "m26_scaffold")
    monkeypatch.chdir(root)
    config = (root / "config" / "broadcasting.py").read_text(encoding="utf-8")
    assert '"driver": "websocket"' in config
    assert '"driver": "pusher"' in config
    channels = (root / "routes" / "channels.py").read_text(encoding="utf-8")
    assert "Broadcast.channel" in channels


def test_m26_make_channel_writes_a_channel_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m26_make", destination=tmp_path / "m26_make")
    monkeypatch.chdir(root)

    result = runner.invoke(smith_app, ["make:channel", "OrderChannel"])
    assert result.exit_code == 0, result.stdout + result.stderr
    written = (root / "app" / "broadcasting" / "order_channel.py").read_text(encoding="utf-8")
    assert "class OrderChannel:" in written
    assert "def join(self, user" in written


def test_m26_channel_list_shows_the_registered_channels(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["channel:list"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "broadcasting via [websocket]" in output
    assert "posts.{post} -> PostChannel" in output
    assert "rooms.{room}" in output


def test_m26_progress_broadcast_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:broadcast"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "broadcasting demo ok" in output
    assert "driver -> websocket [websocket]" in output
    assert "authorize -> Ada on private-authors.Ada: True" in output
    assert "event -> post.published" in output
    assert "model -> CommentCreated" in output


def test_m26_route_returns_a_broadcasting_tour(progress_client: TestClient) -> None:
    response = progress_client.get("/api/broadcast")
    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"]["driver"] == "websocket"
    assert payload["authorization"]["allowed"] is True
    assert payload["authorization"]["refused"] is False
    assert payload["authorization"]["presence"]["members"]
    assert payload["broadcast"]["event"] == "post.published"
    assert {frame["event"] for frame in payload["broadcast"]["frames"]} == {"post.published"}
    assert payload["endpoints"]["auth"] == "/broadcasting/auth"


def test_m26_the_authorization_endpoint_is_registered(progress_client: TestClient) -> None:
    paths = {route.path for route in progress_client.app.routes}
    assert "/broadcasting/auth" in paths
    assert "/broadcasting/user-auth" in paths
    assert "/broadcasting/socket" in paths


def test_m26_a_browser_can_talk_to_the_socket(progress_client: TestClient) -> None:
    from almasix.broadcasting import Broadcast, get_hub

    with progress_client.websocket_connect("/broadcasting/socket") as socket:
        opened = socket.receive_json()
        assert opened["event"] == "almasix:connection_established"

        socket.send_json({"event": "subscribe", "data": {"channel": "announcements"}})
        assert socket.receive_json()["event"] == "almasix:subscription_succeeded"

        # The endpoint and the broadcaster reach the same hub.
        assert Broadcast.connection("websocket").hub is get_hub()

        socket.send_json({"event": "ping"})
        assert socket.receive_json()["event"] == "almasix:pong"

        socket.send_json({"event": "subscribe", "data": {"channel": "private-authors.Ada"}})
        refused = socket.receive_json()
        assert refused["event"] == "almasix:error"


def test_m26_board_marks_broadcasting_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m26 = next(m for m in _milestones() if m["id"] == "M26")
    assert m26["status"] == "complete"
    assert any("progress:broadcast" in proof for proof in m26["proof"])
