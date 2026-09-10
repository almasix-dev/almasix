"""M52 — Sonar driver alias and socket registration."""

from __future__ import annotations

from typing import Any

from almasix.broadcasting.broadcasters.websocket import WebsocketBroadcaster
from almasix.broadcasting.helpers import default_broadcasting_config
from almasix.broadcasting.manager import BroadcastManager
from almasix.broadcasting.provider import _SONAR_DRIVERS, BroadcastServiceProvider
from almasix.framework.application import Application


def test_sonar_drivers_frozenset_covers_aliases() -> None:
    assert _SONAR_DRIVERS == frozenset({"websocket", "sonar"})


def test_default_config_includes_sonar_connection() -> None:
    config = default_broadcasting_config()
    assert "sonar" in config["connections"]
    assert config["connections"]["sonar"]["driver"] == "sonar"
    assert config["connections"]["websocket"]["driver"] == "websocket"
    assert config["connections"]["sonar"]["path"] == config["connections"]["websocket"]["path"]


def test_provider_registers_socket_for_sonar_default(tmp_path: Any) -> None:
    app = Application(base_path=tmp_path)
    app.config.set(
        "broadcasting",
        {
            "default": "sonar",
            "connections": {
                "sonar": {
                    "driver": "sonar",
                    "key": "k",
                    "secret": "s",
                    "path": "/broadcasting/socket",
                }
            },
            "middleware": ["web"],
        },
    )
    provider = BroadcastServiceProvider(app)
    provider.register()
    provider.boot()
    assert [route.uri for route in app.router.websocket_routes] == ["/broadcasting/socket"]
    manager = app.make(BroadcastManager)
    assert isinstance(manager.connection(), WebsocketBroadcaster)


def test_provider_skips_socket_for_log_default(tmp_path: Any) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("broadcasting", default_broadcasting_config())
    provider = BroadcastServiceProvider(app)
    provider.register()
    provider.boot()
    assert app.router.websocket_routes == []
