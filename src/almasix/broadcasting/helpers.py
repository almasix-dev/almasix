"""`broadcast()`, the manager accessor, and the default configuration."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from almasix.broadcasting.manager import BroadcastManager

_manager: BroadcastManager | None = None


def set_broadcast_manager(manager: BroadcastManager | None) -> None:
    global _manager
    _manager = manager
    from almasix.broadcasting.facade import Broadcast

    Broadcast.set_manager(manager)


def get_broadcast_manager() -> BroadcastManager:
    """The application's manager, or a bare one so libraries still work.

    Broadcasting outside a booted application is legitimate — a unit test, a
    script — and it should behave, not raise. Without configuration the
    default connection is the log.
    """
    global _manager
    if _manager is None:
        _manager = BroadcastManager(config=default_broadcasting_config())
    return _manager


def current_socket_id() -> str | None:
    """The socket that made the current request, from the `X-Socket-ID` header.

    Echo sends this on every HTTP request once it has connected, which is how
    `to_others()` knows whom to leave out.
    """
    from almasix.http.request import get_request

    request = get_request()
    if request is None:
        return None
    return request.header("X-Socket-ID") or None


class PendingBroadcast:
    """A broadcast about to happen, and the two things you may say about it.

    Returned by `broadcast()`. It dispatches the event through the event
    dispatcher — so listeners run too — either when you call `send()`, when
    you await it, or when the expression is discarded, which is what makes
    the Laravel one-liner `broadcast(Event()).to_others()` work.
    """

    def __init__(self, event: Any) -> None:
        self.event = event
        self._sent = False

    def to_others(self) -> PendingBroadcast:
        """Everyone on the channel except the client that caused this."""
        marker = getattr(self.event, "dont_broadcast_to_current_user", None)
        if callable(marker):
            marker()
        else:
            self.event.socket = current_socket_id()
        return self

    def via(self, connection: str | Sequence[str] | None) -> PendingBroadcast:
        """Use a named broadcast connection instead of the default."""
        chooser = getattr(self.event, "broadcast_via", None)
        if callable(chooser):
            chooser(connection)
        else:
            self.event.broadcast_connections = lambda: (
                [connection] if isinstance(connection, (str, type(None))) else list(connection)
            )
        return self

    def send(self) -> Any:
        """Dispatch now; a second call does nothing."""
        if self._sent:
            return None
        self._sent = True
        from almasix.events.helpers import dispatch as dispatch_event

        return dispatch_event(self.event)

    def __await__(self) -> Any:
        async def _send() -> Any:
            return self.send()

        return _send().__await__()

    def __del__(self) -> None:
        # Laravel dispatches in __destruct so a bare `broadcast($e)` still
        # goes out; the same has to hold here, and an interpreter shutting
        # down must not turn a missed broadcast into a traceback.
        try:
            self.send()
        except Exception:  # noqa: BLE001 - nothing useful can be raised from __del__
            pass


def broadcast(event: Any) -> PendingBroadcast:
    """Broadcast an event, Laravel's `broadcast()` helper."""
    return PendingBroadcast(event)


def default_broadcasting_config() -> dict[str, Any]:
    """The shape of `config/broadcasting.py`."""
    from almasix.config import env

    return {
        "default": env("BROADCAST_CONNECTION", "log"),
        "connections": {
            "websocket": {
                "driver": "websocket",
                "key": env("BROADCAST_KEY", "almasix"),
                "secret": env("BROADCAST_SECRET"),
                "path": env("BROADCAST_PATH", "/broadcasting/socket"),
                "client_events": bool(env("BROADCAST_CLIENT_EVENTS", False)),
            },
            "pusher": {
                "driver": "pusher",
                "key": env("PUSHER_APP_KEY"),
                "secret": env("PUSHER_APP_SECRET"),
                "app_id": env("PUSHER_APP_ID"),
                "cluster": env("PUSHER_APP_CLUSTER", "mt1"),
                "host": env("PUSHER_HOST"),
                "port": env("PUSHER_PORT"),
                "scheme": env("PUSHER_SCHEME", "https"),
            },
            "redis": {
                "driver": "redis",
                "connection": env("BROADCAST_REDIS_CONNECTION", "default"),
                "prefix": env("BROADCAST_REDIS_PREFIX", ""),
            },
            "log": {"driver": "log"},
            "null": {"driver": "null"},
        },
    }
