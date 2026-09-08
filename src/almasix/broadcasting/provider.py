"""Broadcasting service provider."""

from __future__ import annotations

from typing import Any

from almasix.broadcasting.facade import Broadcast
from almasix.broadcasting.helpers import default_broadcasting_config, set_broadcast_manager
from almasix.broadcasting.manager import BroadcastManager
from almasix.providers.provider import ServiceProvider

#: Where the authorization endpoints live, as every Echo build expects them.
AUTH_ROUTE = "/broadcasting/auth"
USER_AUTH_ROUTE = "/broadcasting/user-auth"


class BroadcastServiceProvider(ServiceProvider):
    """Binds the manager and adds the routes broadcasting needs."""

    def register(self) -> None:
        app = self.app

        def factory(_container: Any) -> BroadcastManager:
            config = dict(app.config.get("broadcasting") or {})
            if not config:
                config = default_broadcasting_config()
            manager = BroadcastManager(app, config)
            set_broadcast_manager(manager)
            return manager

        app.container.singleton(BroadcastManager, factory)
        app.container.alias(BroadcastManager, "broadcast")

    def boot(self) -> None:
        if not self.app.container.bound(BroadcastManager):
            return
        manager = self.app.make(BroadcastManager)
        set_broadcast_manager(manager)
        Broadcast.set_manager(manager)
        self._load_channels(manager)
        self._register_routes(manager)

    def _load_channels(self, manager: BroadcastManager) -> None:
        """Run `routes/channels.py`, the way Laravel's provider does.

        Channels are loaded here rather than with the HTTP routes because a
        console command may want to know who can hear what — `channel:list`
        does — and because authorization is not an HTTP concern.
        """
        path = self.app.path("routes", "channels.py")
        if not path.is_file():
            return
        manager.forget_channels()
        self.app.load_route_file(path)

    def _register_routes(self, manager: BroadcastManager) -> None:
        """Add the authorization endpoints, and the socket when we host one.

        `broadcasting.routes = False` turns this off for an application that
        would rather write the endpoints itself.
        """
        config = manager.config
        if config.get("routes") is False:
            return

        from almasix.broadcasting.endpoints import BroadcastingController, BroadcastingSocket

        router = self.app.router
        existing = {route.uri for route in router.routes}
        middleware = list(config.get("middleware") or ["web"])

        if AUTH_ROUTE not in existing:
            router.post(
                AUTH_ROUTE,
                [BroadcastingController, "auth"],
                name="broadcasting.auth",
                middleware=middleware,
            )
        if USER_AUTH_ROUTE not in existing:
            router.post(
                USER_AUTH_ROUTE,
                [BroadcastingController, "user_auth"],
                name="broadcasting.user-auth",
                middleware=middleware,
            )

        path = self._socket_path(manager)
        if path and path not in {route.uri for route in router.websocket_routes}:
            router.websocket(path, BroadcastingSocket(), name="broadcasting.socket")

    def _socket_path(self, manager: BroadcastManager) -> str | None:
        """The socket path, when the active connection is one we host."""
        try:
            config = manager.connection_config(manager.get_default_driver())
        except KeyError:
            return None
        if str(config.get("driver") or "") != "websocket":
            return None
        return str(config.get("path") or "/broadcasting/socket")
