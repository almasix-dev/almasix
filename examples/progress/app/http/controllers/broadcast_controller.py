"""Broadcasting tour — M26: channels, authorization, sockets over HTTP."""

from __future__ import annotations

from app.events.post_published import PostPublished
from app.models.post import Post
from app.models.user import User
from app.support.demo_db import ensure_demo_database

from almasix.broadcasting import Broadcast, PresenceChannel, PrivateChannel, get_hub
from almasix.broadcasting.signing import encode_channel_data, sign
from almasix.http import Controller


class Recorder:
    """A connected client, minus the browser."""

    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def __call__(self, frame: dict) -> None:
        self.frames.append(frame)


class BroadcastController(Controller):
    async def index(self) -> dict:
        await ensure_demo_database()
        hub = get_hub()
        hub.flush()

        broadcaster = Broadcast.connection("websocket")
        key, secret = broadcaster.auth_key(), broadcaster.auth_secret()

        ada = await User.query().where("email", "=", "ada@almasix.dev").first()
        post = await Post.query().where("user_id", "=", ada.id).first()

        client = Recorder()
        connection = hub.connect(client)
        await hub.subscribe(connection, "announcements")

        author = PrivateChannel(f"authors.{ada.name}").full_name
        room = PresenceChannel("rooms.lobby").full_name
        member = await Broadcast.authorize(ada, room)
        channel_data = encode_channel_data(ada.get_key(), member)
        await hub.subscribe(connection, author)
        await hub.subscribe(connection, room, member if isinstance(member, dict) else None)

        event = PostPublished(post.get_key(), post.title, ada.name)
        await Broadcast.send(event)

        payload = {
            "connection": {
                "driver": broadcaster.driver,
                "socket_id": connection.id,
                "channels": sorted(connection.channels),
                "hub": hub.channels(),
            },
            "channels": [
                {"pattern": route.pattern, "guards": route.guards} for route in Broadcast.channels()
            ],
            "authorization": {
                "allowed": bool(await Broadcast.authorize(ada, author)),
                "refused": bool(
                    await Broadcast.authorize(ada, PrivateChannel("posts.999999").full_name)
                ),
                "auth": sign(key, secret, connection.id, author),
                "presence": {"members": hub.members(room), "channel_data": channel_data},
            },
            "broadcast": {
                "event": event.broadcast_as(),
                "on": [str(channel) for channel in event.broadcast_on()],
                "frames": [
                    {"event": frame["event"], "channel": frame["channel"]}
                    for frame in client.frames
                ],
            },
            "endpoints": {
                "auth": "/broadcasting/auth",
                "user_auth": "/broadcasting/user-auth",
                "socket": "/broadcasting/socket",
            },
        }
        await hub.disconnect(connection)
        return payload
