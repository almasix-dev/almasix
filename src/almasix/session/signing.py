"""Signed cookie helpers for session payloads."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_payload(payload: dict[str, Any], *, key: str, max_age: int | None = None) -> str:
    """Return ``payload_b64.timestamp.signature`` for a cookie value."""
    body = _b64encode(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))
    timestamp = str(int(time.time()))
    signature = _sign(f"{body}.{timestamp}", key)
    return f"{body}.{timestamp}.{signature}"


def unsign_payload(
    token: str,
    *,
    key: str,
    max_age: int | None = None,
) -> dict[str, Any] | None:
    """Decode a signed cookie; return ``None`` when invalid or expired."""
    try:
        body, timestamp, signature = token.split(".", 2)
    except ValueError:
        return None
    expected = _sign(f"{body}.{timestamp}", key)
    if not hmac.compare_digest(expected, signature):
        return None
    try:
        ts = int(timestamp)
    except ValueError:
        return None
    if max_age is not None and max_age >= 0 and (time.time() - ts) > max_age:
        return None
    try:
        data = json.loads(_b64decode(body).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _sign(message: str, key: str) -> str:
    digest = hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)
