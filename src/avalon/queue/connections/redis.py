"""Redis queue driver — requires ``avalon[redis]``."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from avalon.queue.job import Job

if TYPE_CHECKING:
    from avalon.queue.manager import QueueManager


class RedisQueue:
    """List + delayed sorted-set queue backed by Redis."""

    def __init__(
        self,
        app: Any | None,
        config: dict[str, Any],
        *,
        manager: QueueManager | None = None,
        connection_name: str = "redis",
        client: Any | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.manager = manager
        self.connection_name = connection_name
        self._client = client
        self.redis_connection = config.get("connection")
        self.queue_prefix = str(config.get("queue") or "queues")

    def _redis(self) -> Any:
        if self._client is not None:
            return self._client
        from avalon.redis.helpers import get_manager

        name = str(self.redis_connection) if self.redis_connection else None
        return get_manager().connection(name)

    def _queue_key(self, queue: str) -> str:
        return f"{self.queue_prefix}:{queue}"

    def _delayed_key(self, queue: str) -> str:
        return f"{self.queue_prefix}:delayed:{queue}"

    def _reserved_key(self) -> str:
        return f"{self.queue_prefix}:reserved"

    def new_failed_uuid(self) -> str:
        return str(uuid4())

    async def push(self, job: Job) -> bool:
        queue = job.queue_name()
        job_id = str(uuid4())
        unique_id = job.unique_id()
        envelope = job.serialize()
        if unique_id:
            envelope["unique_id"] = unique_id
        record = {
            "id": job_id,
            "queue": queue,
            "payload": json.dumps(envelope, default=str),
            "attempts": 0,
        }
        delay = float(job.delay or 0)
        client = self._redis()
        if delay > 0:
            available_at = time.time() + delay
            await client.zadd(self._delayed_key(queue), {json.dumps(record): available_at})
        else:
            await client.rpush(self._queue_key(queue), json.dumps(record))
        return True

    async def _promote_delayed(self, queue: str) -> None:
        client = self._redis()
        delayed = self._delayed_key(queue)
        now = time.time()
        ready = await client.zrangebyscore(delayed, min=0, max=now)
        for raw in ready or []:
            await client.zrem(delayed, raw)
            await client.rpush(self._queue_key(queue), raw)

    async def pop(self, queue: str = "default") -> dict[str, Any] | None:
        await self._promote_delayed(queue)
        client = self._redis()
        raw = await client.lpop(self._queue_key(queue))
        if raw is None:
            return None
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        record = json.loads(text)
        await client.hset(self._reserved_key(), str(record["id"]), text)
        return dict(record)

    async def delete(self, job_id: Any) -> None:
        await self._redis().hdel(self._reserved_key(), str(job_id))

    async def release(self, job_id: Any, *, delay: int = 0) -> None:
        client = self._redis()
        reserved = self._reserved_key()
        raw = await client.hget(reserved, str(job_id))
        if raw is None:
            return
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        record = json.loads(text)
        record["attempts"] = int(record.get("attempts") or 0) + 1
        await client.hdel(reserved, str(job_id))
        queue = str(record.get("queue") or "default")
        payload = json.dumps(record)
        if delay > 0:
            await client.zadd(self._delayed_key(queue), {payload: time.time() + delay})
        else:
            await client.rpush(self._queue_key(queue), payload)

    async def clear(self, queue: str = "default") -> int:
        """Drop the ready list and the delayed set, returning how many jobs went.

        Reserved jobs are left alone: they are in a worker's hands, not pending.
        """
        client = self._redis()
        ready = int(await client.llen(self._queue_key(queue)) or 0)
        delayed = int(await client.zcard(self._delayed_key(queue)) or 0)
        await client.delete(self._queue_key(queue), self._delayed_key(queue))
        return ready + delayed

    async def size(self, queue: str = "default") -> int:
        await self._promote_delayed(queue)
        client = self._redis()
        ready = int(await client.llen(self._queue_key(queue)) or 0)
        delayed = int(await client.zcard(self._delayed_key(queue)) or 0)
        return ready + delayed
