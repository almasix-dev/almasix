"""The endpoints broadcasting adds to an application.

Three of them: two HTTP routes that authorize a client, and the websocket
that clients actually connect to when the application runs its own socket
server. They are registered by the service provider, not by the application's
route files — the same way Laravel adds `/broadcasting/auth`.
"""

from __future__ import annotations

import json
from typing import Any

from almasix.broadcasting.channels import is_presence, is_private
from almasix.broadcasting.exceptions import AccessDeniedException
from almasix.broadcasting.helpers import get_broadcast_manager
from almasix.broadcasting.signing import verify
from almasix.broadcasting.sockets import Connection, SocketHub, decode_frame, get_hub
from almasix.http.exceptions import ForbiddenHttpException


class BroadcastingController:
    """Answers "may this client listen?" for a socket server."""

    async def auth(self, request: Any) -> dict[str, Any]:
        """`POST /broadcasting/auth` — the channel authorization endpoint."""
        try:
            return await get_broadcast_manager().auth(request)
        except AccessDeniedException as denied:
            raise ForbiddenHttpException(str(denied)) from denied

    async def user_auth(self, request: Any) -> dict[str, Any]:
        """`POST /broadcasting/user-auth` — identifies the connection itself."""
        try:
            return get_broadcast_manager().user_auth(request)
        except AccessDeniedException as denied:
            raise ForbiddenHttpException(str(denied)) from denied


class BroadcastingSocket:
    """Almasix's websocket server, in one handler.

    The protocol is deliberately small and Pusher-shaped, so an existing
    client library — or twenty lines of `WebSocket` in a browser — can talk
    to it:

    - the server opens with `almasix:connection_established`, carrying the
      `socket_id` the client must send back on HTTP requests;
    - the client sends `subscribe` with a channel, plus the `auth` signature
      from `/broadcasting/auth` when the channel is private;
    - the server answers `almasix:subscription_succeeded` and thereafter
      forwards every broadcast on that channel.
    """

    def __init__(self, hub: SocketHub | None = None) -> None:
        self._hub = hub

    @property
    def hub(self) -> SocketHub:
        return self._hub if self._hub is not None else get_hub()

    async def __call__(self, websocket: Any) -> None:
        await self.handle(websocket)

    async def handle(self, websocket: Any) -> None:
        await websocket.accept()

        async def send(frame: dict[str, Any]) -> None:
            await websocket.send_text(json.dumps(frame, default=str))

        connection = self.hub.connect(send)
        await send(
            {
                "event": "almasix:connection_established",
                "data": {"socket_id": connection.id},
            }
        )
        try:
            while True:
                raw = await websocket.receive_text()
                await self.dispatch(connection, decode_frame(raw))
        except Exception:
            pass
        finally:
            await self.hub.disconnect(connection)

    async def dispatch(self, connection: Connection, frame: dict[str, Any]) -> None:
        """Handle one client frame."""
        event = str(frame.get("event") or "")
        data = frame.get("data") or {}
        if not isinstance(data, dict):
            data = {}

        if event == "subscribe":
            await self.subscribe(connection, data)
        elif event == "unsubscribe":
            await self.hub.unsubscribe(connection, str(data.get("channel") or ""))
        elif event == "ping":
            await connection.send({"event": "almasix:pong", "data": {}})
        elif event.startswith("client-"):
            await self.client_event(connection, event, frame)
        else:
            await self.error(connection, f"Unknown event [{event}].")

    async def subscribe(self, connection: Connection, data: dict[str, Any]) -> None:
        """Join a channel, after checking the signature on a private one."""
        channel = str(data.get("channel") or "")
        if not channel:
            await self.error(connection, "A channel name is required to subscribe.")
            return

        member: dict[str, Any] | None = None
        if is_private(channel):
            channel_data = data.get("channel_data")
            if not self.verify(connection.id, channel, str(data.get("auth") or ""), channel_data):
                await self.error(connection, f"Not authorized to join [{channel}].", channel)
                return
            if is_presence(channel):
                member = _member_from(channel_data)
                if member is None:
                    await self.error(connection, "Presence channels need channel_data.", channel)
                    return

        roster = await self.hub.subscribe(connection, channel, member)
        await connection.send(
            {
                "event": "almasix:subscription_succeeded",
                "channel": channel,
                "data": {"members": roster} if is_presence(channel) else {},
            }
        )

    async def client_event(
        self,
        connection: Connection,
        event: str,
        frame: dict[str, Any],
    ) -> None:
        """Forward a `client-*` event to the rest of a channel.

        Off unless the connection's configuration turns it on, because it
        lets one browser send data to every other one.
        """
        channel = str(frame.get("channel") or "")
        if not self.client_events_enabled():
            await self.error(connection, "Client events are disabled.", channel)
            return
        if channel not in connection.channels or not is_private(channel):
            await self.error(
                connection,
                "Client events are only allowed on private channels you have joined.",
                channel,
            )
            return
        await self.hub.publish([channel], event, frame.get("data"), socket=connection.id)

    def client_events_enabled(self) -> bool:
        manager = get_broadcast_manager()
        try:
            config = manager.connection_config(manager.get_default_driver())
        except KeyError:  # pragma: no cover - unconfigured application
            return False
        return bool(config.get("client_events"))

    def verify(
        self,
        socket_id: str,
        channel: str,
        auth: str,
        channel_data: Any = None,
    ) -> bool:
        """Whether this `auth` string came from our own `/broadcasting/auth`."""
        broadcaster = get_broadcast_manager().connection()
        secret = broadcaster.auth_secret()
        if not secret:
            return False
        data = channel_data if isinstance(channel_data, str) else None
        return verify(broadcaster.auth_key(), secret, auth, socket_id, channel, data)

    async def error(self, connection: Connection, message: str, channel: str = "") -> None:
        await connection.send(
            {
                "event": "almasix:error",
                "channel": channel,
                "data": {"message": message},
            }
        )


def _member_from(channel_data: Any) -> dict[str, Any] | None:
    """The presence member described by signed `channel_data`."""
    if not isinstance(channel_data, str):
        return None
    try:
        decoded = json.loads(channel_data)
    except ValueError:
        return None
    if not isinstance(decoded, dict) or "user_id" not in decoded:
        return None
    return decoded
