"""Concurrent request pool (Laravel ``Http::pool``)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from avalon.client.exceptions import HttpClientException
from avalon.client.pending import PendingRequest
from avalon.client.response import Response

VERBS = ("get", "head", "post", "put", "patch", "delete", "options", "send")
DEFAULT_CONCURRENCY = 8


class PoolRequest:
    """One pooled request: ``PendingRequest`` fluency, verbs enqueue the job."""

    def __init__(self, pool: Pool, pending: PendingRequest, key: str | None = None) -> None:
        self._pool = pool
        self._pending = pending
        self._key = key

    def as_(self, key: str) -> PoolRequest:
        return PoolRequest(self._pool, self._pending, key)

    def __getattr__(self, name: str) -> Any:
        pending = self._pending
        if name in VERBS:

            def enqueue(*args: Any, **kwargs: Any) -> Any:
                return self._pool.enqueue(
                    self._key, lambda: getattr(pending, name)(*args, **kwargs)
                )

            return enqueue

        attribute = getattr(pending, name)
        if not callable(attribute):
            return attribute

        def fluent(*args: Any, **kwargs: Any) -> Any:
            result = attribute(*args, **kwargs)
            if isinstance(result, PendingRequest):
                return PoolRequest(self._pool, result, self._key)
            return result

        return fluent


class Pool:
    """Collects named / indexed requests then runs them concurrently."""

    def __init__(self, factory: Any, concurrency: int | None = None) -> None:
        self._factory = factory
        self._jobs: list[tuple[str | int, Callable[[], Response]]] = []
        self._index = 0
        self._concurrency = concurrency

    def concurrency(self, limit: int) -> Pool:
        self._concurrency = limit
        return self

    def request(self) -> PoolRequest:
        """A fresh pooled request to configure before choosing a verb."""
        return PoolRequest(self, self._factory.pending())

    def as_(self, key: str) -> PoolRequest:
        return self.request().as_(key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.request(), name)

    def enqueue(self, key: str | None, sender: Callable[[], Response]) -> Pool:
        if key is None:
            key = self._index
            self._index += 1
        self._jobs.append((key, sender))
        return self

    def jobs(self) -> list[tuple[str | int, Callable[[], Response]]]:
        return list(self._jobs)

    def run(self) -> dict[str | int, Response | HttpClientException]:
        jobs = self.jobs()
        if not jobs:
            return {}
        results = run_jobs(jobs, self._concurrency)
        return {key: results[key] for key, _fn in jobs}


def run_jobs(
    jobs: list[tuple[str | int, Callable[[], Response]]],
    concurrency: int | None = None,
    on_settled: Callable[[str | int, Response | HttpClientException], None] | None = None,
) -> dict[str | int, Response | HttpClientException]:
    """Run pooled senders on a thread pool, collecting results by key.

    Like Laravel, a client failure becomes the *value* for that key instead of
    propagating, so one bad request does not sink the whole pool.
    """
    workers = min(concurrency or DEFAULT_CONCURRENCY, len(jobs))
    results: dict[str | int, Response | HttpClientException] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fn): key for key, fn in jobs}
        for future in as_completed(futures):
            key = futures[future]
            try:
                outcome: Response | HttpClientException = future.result()
            except HttpClientException as exc:
                outcome = exc
            results[key] = outcome
            if on_settled is not None:
                on_settled(key, outcome)
    return results
