"""Demo Sonar — first-party realtime branding + protocol (M52)."""

from __future__ import annotations

import asyncio
import json

from almasix.broadcasting import Broadcast, PrivateChannel, get_hub
from almasix.broadcasting.endpoints import BroadcastingSocket
from almasix.broadcasting.signing import sign
from almasix.console.command import Command
from app.models.user import User
from app.support.demo_db import ensure_demo_database

_SONAR_NPM = "https://www.npmjs.com/package/@almasix/sonar"
_SONAR_REPO = "https://github.com/almasix-dev/sonar"


class FakeSocket:
    """Collects frames the way a browser would receive them."""

    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def __call__(self, frame: dict) -> None:
        self.frames.append(json.loads(json.dumps(frame, default=str)))

    def last(self, event: str) -> dict | None:
        for frame in reversed(self.frames):
            if frame.get("event") == event:
                return frame
        return None


class ProgressSonarCommand(Command):
    signature = "progress:sonar"
    description = "Demo Sonar realtime — server alias, auth, @almasix/sonar package (M52)"

    def handle(self) -> int:
        return asyncio.run(self.demonstrate())

    async def demonstrate(self) -> int:
        await ensure_demo_database()
        hub = get_hub()
        hub.flush()

        # sonar is a product alias for the websocket driver / connection.
        broadcaster = Broadcast.connection("sonar")
        self.info(f"sonar   -> driver={broadcaster.driver} connection={broadcaster.name}")
        self.info("package -> @almasix/sonar")
        self.line(f"  npm    -> {_SONAR_NPM}")
        self.line(f"  source -> {_SONAR_REPO}")

        ada = await User.query().where("email", "=", "ada@almasix.dev").first()
        socket = FakeSocket()
        server = BroadcastingSocket(hub)
        connection = hub.connect(socket)

        # Public subscribe — same almasix:* protocol @almasix/sonar speaks.
        await server.subscribe(connection, {"channel": "announcements"})
        joined_public = socket.last("almasix:subscription_succeeded")
        self.info(f"public  -> {joined_public['channel']}")

        private = PrivateChannel(f"authors.{ada.name}").full_name
        allowed = await Broadcast.authorize(ada, private)
        auth = sign(
            broadcaster.auth_key(),
            broadcaster.auth_secret(),
            connection.id,
            private,
        )
        await server.subscribe(connection, {"channel": private, "auth": auth})
        joined = socket.last("almasix:subscription_succeeded")
        self.info(f"private -> {joined['channel']} authorized={bool(allowed)}")
        self.info(f"socket  -> {connection.id} (X-Socket-ID / toOthers)")

        await hub.disconnect(connection)
        self.success("sonar demo ok")
        return 0
