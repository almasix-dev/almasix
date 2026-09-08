"""Job base — handle, dispatch, retries, middleware."""

from __future__ import annotations

import inspect
from typing import Any, ClassVar


class ShouldQueue:
    """Marker — job is pushed to the configured queue connection."""


class JobMiddleware:
    """Pipeline middleware for jobs."""

    async def handle(self, job: Job, nxt: Any) -> Any:
        return await nxt(job)


class Job:
    """Laravel-shaped queue job base."""

    tries: ClassVar[int] = 1
    timeout: ClassVar[int | None] = None
    backoff: ClassVar[int | list[int] | None] = None
    delay: ClassVar[int | float] = 0
    queue: ClassVar[str | bool] = False
    connection: ClassVar[str | None] = None
    middleware: ClassVar[list[type[JobMiddleware]]] = []
    unique_for: ClassVar[int | None] = None

    def handle(self) -> Any:
        raise NotImplementedError(f"{type(self).__name__}.handle() is not implemented")

    async def failed(self, exc: BaseException) -> None:
        """Hook when the job has exhausted retries."""

    def unique_id(self) -> str | None:
        """Optional dedupe key for database queue inserts."""
        return None

    def queue_name(self) -> str:
        if isinstance(self.queue, str) and self.queue:
            return self.queue
        return "default"

    def connection_name(self) -> str | None:
        return self.connection

    def should_queue(self) -> bool:
        if isinstance(self, ShouldQueue):
            return True
        return self.queue is True or (isinstance(self.queue, str) and bool(self.queue))

    def serialize(self) -> dict[str, Any]:
        return {
            "class": f"{self.__class__.__module__}.{self.__class__.__qualname__}",
            "data": {k: v for k, v in self.__dict__.items() if not k.startswith("_")},
        }

    @classmethod
    def deserialize(cls, payload: dict[str, Any]) -> Job:
        class_path = str(payload.get("class") or "")
        if not class_path:
            raise ValueError("Job payload missing class reference")
        job_cls = _import_job_class(class_path)
        # Bypass __init__ so keyword-only / required ctor args still round-trip
        # via serialize() → __dict__.update().
        job = job_cls.__new__(job_cls)
        data = payload.get("data") or {}
        if isinstance(data, dict):
            job.__dict__.update(data)
        return job

    @classmethod
    async def dispatch(cls, **kwargs: Any) -> Any:
        job = cls(**kwargs) if kwargs else cls()
        from almasix.queue.helpers import dispatch as queue_dispatch

        return await queue_dispatch(job)

    async def dispatch_sync(self) -> Any:
        from almasix.queue.helpers import dispatch_sync

        return await dispatch_sync(self)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


def _import_job_class(path: str) -> type[Job]:
    module_name, _, qualname = path.rpartition(".")
    if not module_name:
        raise ValueError(f"Invalid job class path: {path!r}")
    import importlib

    module = importlib.import_module(module_name)
    obj: Any = module
    for part in qualname.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, type) or not issubclass(obj, Job):
        raise TypeError(f"{path!r} is not a Job subclass")
    return obj


async def call_handle(job: Job) -> Any:
    result = job.handle()
    if inspect.isawaitable(result):
        return await result
    return result


async def run_through_middleware(job: Job, final: Any) -> Any:
    stack = list(reversed(getattr(job, "middleware", None) or job.__class__.middleware or []))

    async def invoke(index: int, current: Job) -> Any:
        if index >= len(stack):
            return await final(current)
        middleware_cls = stack[index]
        middleware = middleware_cls()
        return await middleware.handle(current, lambda nxt: invoke(index + 1, nxt))

    return await invoke(0, job)
