"""In-memory async Redis stand-in for unit tests (no server required)."""

from __future__ import annotations

import asyncio
import time
from typing import Any


class FakeRedis:
    """Minimal subset of ``redis.asyncio.Redis`` used by Almasix drivers."""

    def __init__(self) -> None:
        self._kv: dict[str, tuple[bytes, float | None]] = {}
        self._lists: dict[str, list[bytes]] = {}
        self._zsets: dict[str, dict[bytes, float]] = {}
        self._hashes: dict[str, dict[str, bytes]] = {}
        self._channels: dict[str, list[bytes]] = {}

    def _alive(self, key: str) -> bytes | None:
        item = self._kv.get(key)
        if item is None:
            return None
        value, expires = item
        if expires is not None and expires <= time.time():
            self._kv.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> bytes | None:
        await asyncio.sleep(0)
        return self._alive(key)

    async def set(
        self,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        nx: bool = False,
        **_kwargs: Any,
    ) -> bool | None:
        await asyncio.sleep(0)
        raw = value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
        if nx and self._alive(key) is not None:
            return False
        expires = None if ex is None else time.time() + max(0, int(ex))
        self._kv[key] = (bytes(raw), expires)
        return True

    async def delete(self, *keys: str) -> int:
        await asyncio.sleep(0)
        count = 0
        for key in keys:
            if key in self._kv:
                self._kv.pop(key, None)
                count += 1
            if key in self._lists:
                self._lists.pop(key, None)
                count += 1
            if key in self._zsets:
                self._zsets.pop(key, None)
                count += 1
            if key in self._hashes:
                self._hashes.pop(key, None)
                count += 1
        return count

    async def incr(self, key: str) -> int:
        return await self.incrby(key, 1)

    async def incrby(self, key: str, amount: int) -> int:
        await asyncio.sleep(0)
        raw = self._alive(key)
        current = int(raw.decode("utf-8")) if raw else 0
        next_value = current + amount
        expires = self._kv.get(key, (b"", None))[1] if key in self._kv else None
        self._kv[key] = (str(next_value).encode("utf-8"), expires)
        return next_value

    async def ttl(self, key: str) -> int:
        await asyncio.sleep(0)
        item = self._kv.get(key)
        if item is None:
            return -2
        _value, expires = item
        if expires is None:
            return -1
        remaining = int(expires - time.time())
        return remaining if remaining > 0 else -2

    async def flushdb(self) -> bool:
        await asyncio.sleep(0)
        self._kv.clear()
        self._lists.clear()
        self._zsets.clear()
        self._hashes.clear()
        return True

    async def scan(
        self,
        cursor: int = 0,
        *,
        match: str | None = None,
        count: int = 100,
    ) -> tuple[int, list[str]]:
        del count
        await asyncio.sleep(0)
        import fnmatch

        keys = list(self._kv.keys())
        if match:
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        # Two-page scan so callers exercise the cursor loop.
        if cursor == 0 and len(keys) > 1:
            mid = max(1, len(keys) // 2)
            return 1, keys[:mid]
        if cursor == 1:
            mid = max(1, len(keys) // 2)
            return 0, keys[mid:]
        return 0, keys

    async def rpush(self, key: str, *values: Any) -> int:
        await asyncio.sleep(0)
        bucket = self._lists.setdefault(key, [])
        for value in values:
            raw = value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
            bucket.append(bytes(raw))
        return len(bucket)

    async def lpop(self, key: str) -> bytes | None:
        await asyncio.sleep(0)
        bucket = self._lists.get(key) or []
        if not bucket:
            return None
        return bucket.pop(0)

    async def llen(self, key: str) -> int:
        await asyncio.sleep(0)
        return len(self._lists.get(key) or [])

    async def zadd(self, key: str, mapping: dict[Any, float]) -> int:
        await asyncio.sleep(0)
        bucket = self._zsets.setdefault(key, {})
        for member, score in mapping.items():
            raw = member if isinstance(member, (bytes, bytearray)) else str(member).encode("utf-8")
            bucket[bytes(raw)] = float(score)
        return len(mapping)

    async def zrangebyscore(self, key: str, min: float, max: float) -> list[bytes]:
        await asyncio.sleep(0)
        bucket = self._zsets.get(key) or {}
        return [m for m, score in bucket.items() if min <= score <= max]

    async def zrem(self, key: str, *members: Any) -> int:
        await asyncio.sleep(0)
        bucket = self._zsets.get(key) or {}
        count = 0
        for member in members:
            raw = member if isinstance(member, (bytes, bytearray)) else str(member).encode("utf-8")
            if bytes(raw) in bucket:
                bucket.pop(bytes(raw), None)
                count += 1
        return count

    async def zcard(self, key: str) -> int:
        await asyncio.sleep(0)
        return len(self._zsets.get(key) or {})

    async def hset(self, key: str, field: str, value: Any) -> int:
        await asyncio.sleep(0)
        bucket = self._hashes.setdefault(key, {})
        raw = value if isinstance(value, (bytes, bytearray)) else str(value).encode("utf-8")
        bucket[str(field)] = bytes(raw)
        return 1

    async def hget(self, key: str, field: str) -> bytes | None:
        await asyncio.sleep(0)
        return (self._hashes.get(key) or {}).get(str(field))

    async def hdel(self, key: str, *fields: str) -> int:
        await asyncio.sleep(0)
        bucket = self._hashes.get(key) or {}
        count = 0
        for field in fields:
            if str(field) in bucket:
                bucket.pop(str(field), None)
                count += 1
        return count

    async def publish(self, channel: str, message: Any) -> int:
        await asyncio.sleep(0)
        raw = message if isinstance(message, (bytes, bytearray)) else str(message).encode("utf-8")
        self._channels.setdefault(channel, []).append(bytes(raw))
        return 1

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self)


class FakePubSub:
    def __init__(self, client: FakeRedis) -> None:
        self.client = client
        self.channels: list[str] = []

    async def subscribe(self, *channels: str) -> None:
        await asyncio.sleep(0)
        self.channels.extend(channels)
