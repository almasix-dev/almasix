"""Redis cache store — requires ``almasix[redis]``."""

from __future__ import annotations

import pickle
import secrets
import time
import uuid
from typing import Any

from almasix.cache.locks import LockTimeoutError


def _run(coro: Any) -> Any:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class RedisLock:
    """Lock via ``SET key owner NX EX seconds``."""

    def __init__(
        self,
        store: RedisStore,
        name: str,
        *,
        seconds: int | None = None,
        owner: str | None = None,
    ) -> None:
        self.store = store
        self.name = name
        self.seconds = 86400 if seconds is None else max(1, int(seconds))
        self.owner = owner or f"{uuid.uuid4().hex}:{secrets.token_hex(4)}"
        self._key = f"lock:{name}"

    def get(self, callback: Any | None = None) -> bool | Any:
        acquired = _run(self.store._aset_nx(self._key, self.owner, self.seconds))
        if not acquired:
            return False
        if callback is None:
            return True
        try:
            return callback()
        finally:
            self.release()

    def block(self, seconds: int, callback: Any | None = None) -> Any:
        deadline = time.monotonic() + max(0, int(seconds))
        while True:
            result = self.get(callback)
            if result is not False:
                return True if callback is None else result
            if time.monotonic() >= deadline:
                raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
            time.sleep(0.05)

    def release(self) -> bool:
        return bool(_run(self.store._arelease_lock(self._key, self.owner)))

    def force_release(self) -> bool:
        return bool(_run(self.store._aforget(self._key)))

    def owner_token(self) -> str:
        return self.owner

    def __enter__(self) -> RedisLock:
        if self.get() is False:
            raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


class RedisStore:
    """Redis-backed cache store with tags and atomic locks."""

    supports_tags = True

    def __init__(
        self,
        *,
        connection: str | None = None,
        client: Any | None = None,
        prefix: str = "",
    ) -> None:
        self.connection_name = connection
        self._client = client
        self.prefix = prefix

    def _redis(self) -> Any:
        if self._client is not None:
            return self._client
        from almasix.redis.helpers import get_manager

        return get_manager().connection(self.connection_name)

    def get(self, key: str) -> Any:
        return _run(self._aget(key))

    def put(self, key: str, value: Any, seconds: int | None) -> bool:
        return bool(_run(self._aput(key, value, seconds)))

    def forever(self, key: str, value: Any) -> bool:
        return self.put(key, value, None)

    def forget(self, key: str) -> bool:
        return bool(_run(self._aforget(key)))

    def flush(self) -> bool:
        return bool(_run(self._aflush()))

    def add(self, key: str, value: Any, seconds: int | None = None) -> bool:
        return bool(_run(self._aadd(key, value, seconds)))

    def increment(self, key: str, amount: int = 1) -> int | bool:
        return _run(self._aincrement(key, amount))

    def decrement(self, key: str, amount: int = 1) -> int | bool:
        return self.increment(key, -amount)

    def lock(self, name: str, seconds: int | None = None, owner: str | None = None) -> RedisLock:
        return RedisLock(self, name, seconds=seconds, owner=owner)

    def restore_lock(self, name: str, owner: str) -> RedisLock:
        return self.lock(name, seconds=None, owner=owner)

    def flush_locks(self) -> bool:
        return bool(_run(self._aflush_locks()))

    async def _aget(self, key: str) -> Any:
        raw = await self._redis().get(key)
        if raw is None:
            return None
        try:
            return pickle.loads(raw)
        except Exception:
            await self._aforget(key)
            return None

    async def _aput(self, key: str, value: Any, seconds: int | None) -> bool:
        payload = pickle.dumps(value, protocol=4)
        client = self._redis()
        if seconds is None:
            await client.set(key, payload)
        else:
            await client.set(key, payload, ex=max(0, int(seconds)) or None)
        return True

    async def _aforget(self, key: str) -> bool:
        return bool(await self._redis().delete(key))

    async def _aflush(self) -> bool:
        await self._redis().flushdb()
        return True

    async def _aadd(self, key: str, value: Any, seconds: int | None) -> bool:
        payload = pickle.dumps(value, protocol=4)
        client = self._redis()
        if seconds is None:
            return bool(await client.set(key, payload, nx=True))
        return bool(await client.set(key, payload, nx=True, ex=max(1, int(seconds))))

    async def _aincrement(self, key: str, amount: int) -> int | bool:
        client = self._redis()
        raw = await client.get(key)
        if raw is None:
            await client.set(key, pickle.dumps(amount, protocol=4))
            return amount
        try:
            current = int(pickle.loads(raw))
        except Exception:
            return False
        next_value = current + amount
        ttl = await client.ttl(key)
        payload = pickle.dumps(next_value, protocol=4)
        if ttl and ttl > 0:
            await client.set(key, payload, ex=ttl)
        else:
            await client.set(key, payload)
        return next_value

    async def _aset_nx(self, key: str, owner: str, seconds: int) -> bool:
        return bool(await self._redis().set(key, owner.encode("utf-8"), nx=True, ex=seconds))

    async def _arelease_lock(self, key: str, owner: str) -> bool:
        client = self._redis()
        raw = await client.get(key)
        if raw is None:
            return False
        current = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        if current != owner:
            return False
        await client.delete(key)
        return True

    async def _aflush_locks(self) -> bool:
        client = self._redis()
        cursor = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match="*lock:*", count=100)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
        return True
