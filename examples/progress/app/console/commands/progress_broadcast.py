"""Demo broadcasting — channels, authorization, sockets, models (M26)."""

from __future__ import annotations

import asyncio
import json

from almasix.broadcasting import (
    Broadcast,
    PresenceChannel,
    PrivateChannel,
    broadcast,
    flush_broadcasts,
    get_hub,
)
from almasix.broadcasting.endpoints import BroadcastingSocket
from almasix.broadcasting.signing import encode_channel_data, sign
from almasix.console.command import Command
from app.events.post_published import PostPublished
from app.models.comment import Comment
from app.models.post import Post
from app.models.user import User
from app.support.demo_db import ensure_demo_database


class FakeSocket:
    """A client that keeps its frames instead of putting them on a wire.

    The hub only ever asks a connection to deliver a frame, so this is a
    whole browser as far as broadcasting is concerned.
    """

    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def __call__(self, frame: dict) -> None:
        self.frames.append(json.loads(json.dumps(frame, default=str)))

    def last(self, event: str) -> dict | None:
        for frame in reversed(self.frames):
            if frame.get("event") == event:
                return frame
        return None


class ProgressBroadcastCommand(Command):
    signature = "progress:broadcast"
    description = "Demo broadcasting — channels, auth, sockets, models (M26)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()
        hub = get_hub()
        hub.flush()

        broadcaster = Broadcast.connection("websocket")
        self.info(f"driver -> {broadcaster.driver} [{broadcaster.name}]")

        ada = await User.query().where("email", "=", "ada@almasix.dev").first()
        post = await Post.query().where("user_id", "=", ada.id).first()

        # --- a browser connects, and subscribes to a public channel --------
        socket = FakeSocket()
        server = BroadcastingSocket(hub)
        connection = hub.connect(socket)
        await server.subscribe(connection, {"channel": "announcements"})
        self.info(f"socket -> {connection.id} joined announcements")

        # --- a private channel needs a signature from /broadcasting/auth ---
        private = PrivateChannel(f"authors.{ada.name}").full_name
        allowed = await Broadcast.authorize(ada, private)
        self.info(f"authorize -> {ada.name} on {private}: {allowed}")

        auth = sign(
            broadcaster.auth_key(),
            broadcaster.auth_secret(),
            connection.id,
            private,
        )
        await server.subscribe(connection, {"channel": private, "auth": auth})
        joined = socket.last("almasix:subscription_succeeded")
        self.info(f"subscribe -> {joined['channel']}")

        refused = await Broadcast.authorize(ada, PrivateChannel("posts.999999").full_name)
        self.info(f"refusal -> posts.999999 for {ada.name}: {bool(refused)}")

        # --- a presence channel carries who is there ------------------------
        room = PresenceChannel("rooms.lobby").full_name
        member = await Broadcast.authorize(ada, room)
        data = encode_channel_data(ada.get_key(), member)
        await server.subscribe(
            connection,
            {
                "channel": room,
                "auth": sign(
                    broadcaster.auth_key(), broadcaster.auth_secret(), connection.id, room, data
                ),
                "channel_data": data,
            },
        )
        self.info(f"presence -> members on {room}: {hub.members(room)}")

        # --- an event goes out ----------------------------------------------
        broadcast(PostPublished(post.get_key(), post.title, ada.name)).send()
        await flush_broadcasts()
        heard = socket.last("post.published")
        self.info(f"event -> {heard['event']} on {heard['channel']}: {heard['data']['title']}")

        # --- a model broadcasts its own writes --------------------------------
        thread = PrivateChannel(f"comments.Post.{post.get_key()}").full_name
        await server.subscribe(
            connection,
            {
                "channel": thread,
                "auth": sign(
                    broadcaster.auth_key(), broadcaster.auth_secret(), connection.id, thread
                ),
            },
        )
        comment = await Comment.create(
            body="Broadcast from a model write.",
            commentable_id=post.get_key(),
            commentable_type="Post",
        )
        await flush_broadcasts()
        model_frame = socket.last("CommentCreated")
        self.info(f"model -> {model_frame['event']} on {model_frame['channel']}")
        await comment.delete()
        await flush_broadcasts()

        # --- to_others leaves the sender out ---------------------------------
        before = len(socket.frames)
        skipped = PostPublished(post.get_key(), post.title, ada.name)
        skipped.socket = connection.id
        await Broadcast.send(skipped)
        self.info(f"to_others -> frames {before} before, {len(socket.frames)} after")

        self.line(f"  channels -> {[route.pattern for route in Broadcast.channels()]}")
        await hub.disconnect(connection)
        self.success("broadcasting demo ok")
        return 0
