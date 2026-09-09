"""Broadcasting through Pusher Channels (and anything speaking its REST API)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any

from almasix.broadcasting.broadcasters.base import Broadcaster

#: Pusher refuses an event addressed to more than a hundred channels.
MAX_CHANNELS_PER_REQUEST = 100


class PusherBroadcaster(Broadcaster):
    """Posts events to `/apps/{app_id}/events`, signed the way Pusher expects.

    The request goes through Almasix's HTTP client, so `Http.fake()` fakes
    broadcasting too and nothing here has to know about httpx.
    """

    driver = "pusher"

    async def broadcast(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        *,
        socket: str | None = None,
    ) -> None:
        names = list(channels)
        for start in range(0, len(names), MAX_CHANNELS_PER_REQUEST):
            await self._post(
                names[start : start + MAX_CHANNELS_PER_REQUEST], event, payload, socket
            )

    async def _post(
        self,
        channels: Sequence[str],
        event: str,
        payload: Mapping[str, Any],
        socket: str | None,
    ) -> None:
        from almasix.client.facade import Http

        body: dict[str, Any] = {
            "name": event,
            "channels": list(channels),
            "data": json.dumps(dict(payload), default=str),
        }
        if socket:
            body["socket_id"] = socket

        encoded = json.dumps(body, separators=(",", ":"), default=str)
        path = f"/apps/{self.app_id}/events"
        url = f"{self.base_url}{path}?{self._query(path, encoded)}"

        response = (
            await Http.pending()
            .with_headers({"Content-Type": "application/json"})
            .apost(
                url,
                body,
            )
        )
        if not response.successful():
            from almasix.broadcasting.exceptions import BroadcastException

            raise BroadcastException(
                f"Pusher rejected the broadcast with status {response.status()}: {response.body()}"
            )

    # ------------------------------------------------------------------
    # Request signing

    @property
    def app_id(self) -> str:
        return str(self.config.get("app_id") or "")

    @property
    def base_url(self) -> str:
        """The host to talk to — an explicit `host` wins, otherwise the cluster."""
        host = self.config.get("host")
        if host:
            scheme = str(self.config.get("scheme") or "https")
            port = self.config.get("port")
            return f"{scheme}://{host}:{port}" if port else f"{scheme}://{host}"
        cluster = str(self.config.get("cluster") or "mt1")
        return f"https://api-{cluster}.pusher.com"

    def _query(self, path: str, body: str) -> str:
        params = {
            "auth_key": self.auth_key(),
            "auth_timestamp": str(int(time.time())),
            "auth_version": "1.0",
            "body_md5": hashlib.md5(body.encode("utf-8")).hexdigest(),
        }
        query = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
        to_sign = f"POST\n{path}\n{query}"
        signature = hmac.new(
            str(self.auth_secret() or "").encode("utf-8"),
            to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{query}&auth_signature={signature}"
