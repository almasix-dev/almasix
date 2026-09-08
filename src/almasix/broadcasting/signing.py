"""Signing authorization responses.

A client asks the application whether it may listen on a private channel; the
application answers with a signature the socket server can check without
asking anything else. The scheme is Pusher's, so the same endpoint serves both
Almasix's own socket server and a hosted one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def signature(secret: str, socket_id: str, channel: str, channel_data: str | None = None) -> str:
    """HMAC-SHA256 over `socket_id:channel[:channel_data]`, hex encoded."""
    message = f"{socket_id}:{channel}"
    if channel_data is not None:
        message = f"{message}:{channel_data}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def sign(
    key: str,
    secret: str,
    socket_id: str,
    channel: str,
    channel_data: str | None = None,
) -> str:
    """The `auth` string a client hands back: the public key and the signature."""
    return f"{key}:{signature(secret, socket_id, channel, channel_data)}"


def verify(
    key: str,
    secret: str,
    auth: str,
    socket_id: str,
    channel: str,
    channel_data: str | None = None,
) -> bool:
    """Whether `auth` is what we would have produced, compared in constant time."""
    expected = sign(key, secret, socket_id, channel, channel_data)
    return hmac.compare_digest(expected, auth or "")


def encode_channel_data(user_id: Any, user_info: Any = None) -> str:
    """The presence payload, serialized exactly as it will be signed.

    The string matters, not the dict: signature and verification have to see
    the same bytes, so whatever is signed is what travels.
    """
    data: dict[str, Any] = {"user_id": str(user_id)}
    if user_info is not None:
        data["user_info"] = user_info
    return json.dumps(data, separators=(",", ":"), default=str)
