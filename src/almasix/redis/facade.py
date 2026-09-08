"""Static ``Redis`` façade over ``RedisManager``."""

from __future__ import annotations

from typing import Any

from almasix.redis.manager import RedisManager


def _run(coro: Any) -> Any:
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class Redis:
    """App-facing Redis helpers (sync wrappers over the async client)."""

    _manager: RedisManager | None = None

    @classmethod
    def set_manager(cls, manager: RedisManager | None) -> None:
        cls._manager = manager

    @classmethod
    def manager(cls) -> RedisManager:
        if cls._manager is None:
            raise RuntimeError("Redis is not configured. Bootstrap the Application first.")
        return cls._manager

    @classmethod
    def connection(cls, name: str | None = None) -> Any:
        return cls.manager().connection(name)

    @classmethod
    def get(cls, key: str, *, connection: str | None = None) -> bytes | None:
        client = cls.connection(connection)

        async def _get() -> bytes | None:
            value = await client.get(key)
            return value

        return _run(_get())

    @classmethod
    def set(
        cls,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        connection: str | None = None,
    ) -> bool:
        client = cls.connection(connection)

        async def _set() -> bool:
            return bool(await client.set(key, value, ex=ex))

        return _run(_set())

    @classmethod
    def delete(cls, *keys: str, connection: str | None = None) -> int:
        if not keys:
            return 0
        client = cls.connection(connection)

        async def _delete() -> int:
            return int(await client.delete(*keys))

        return _run(_delete())

    @classmethod
    def incr(cls, key: str, amount: int = 1, *, connection: str | None = None) -> int:
        client = cls.connection(connection)

        async def _incr() -> int:
            if amount == 1:
                return int(await client.incr(key))
            return int(await client.incrby(key, amount))

        return _run(_incr())

    @classmethod
    def publish(cls, channel: str, message: Any, *, connection: str | None = None) -> int:
        client = cls.connection(connection)

        async def _publish() -> int:
            return int(await client.publish(channel, message))

        return _run(_publish())

    @classmethod
    def subscribe(cls, *channels: str, connection: str | None = None) -> Any:
        """Return a pubsub object subscribed to ``channels`` (async client API)."""
        client = cls.connection(connection)
        pubsub = client.pubsub()

        async def _subscribe() -> Any:
            if channels:
                await pubsub.subscribe(*channels)
            return pubsub

        return _run(_subscribe())
