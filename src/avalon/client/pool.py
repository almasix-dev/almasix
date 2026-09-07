"""Concurrent request pool (Laravel ``Http::pool``)."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from avalon.client.response import Response


class Pool:
    """Collects named / indexed requests then runs them."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._jobs: list[tuple[str | int, Callable[[], Response]]] = []
        self._next_name: str | None = None
        self._index = 0

    def as_(self, key: str) -> Pool:
        self._next_name = key
        return self

    def _pending(self) -> Any:
        return self._factory.pending()

    def _register(self, sender: Callable[[], Response]) -> Pool:
        key: str | int
        if self._next_name is not None:
            key = self._next_name
            self._next_name = None
        else:
            key = self._index
            self._index += 1
        self._jobs.append((key, sender))
        return self

    def get(self, url: str, query: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.get(url, query))

    def head(self, url: str, query: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.head(url, query))

    def post(self, url: str, data: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.post(url, data))

    def put(self, url: str, data: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.put(url, data))

    def patch(self, url: str, data: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.patch(url, data))

    def delete(self, url: str, data: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.delete(url, data))

    def options(self, url: str, data: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.options(url, data))

    def send(self, method: str, url: str, data: Any = None) -> Pool:
        pending = self._pending()
        return self._register(lambda: pending.send(method, url, data))

    def run(self) -> dict[str | int, Response]:
        jobs = list(self._jobs)
        if not jobs:
            return {}
        results: dict[str | int, Response] = {}
        workers = min(8, len(jobs))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(fn): key for key, fn in jobs}
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        ordered: dict[str | int, Response] = {}
        for key, _fn in jobs:
            ordered[key] = results[key]
        return ordered
