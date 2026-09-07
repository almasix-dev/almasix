"""Request batching (Laravel ``Http::batch``) — pooled requests with callbacks."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from avalon.client.exceptions import BatchInProgressException, HttpClientException
from avalon.client.pool import PoolRequest, run_jobs
from avalon.client.response import Response

Result = Response | HttpClientException


class Batch:
    """A pool of requests plus ``before`` / ``progress`` / ``then`` / … callbacks."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._jobs: list[tuple[str | int, Callable[[], Response]]] = []
        self._index = 0
        self._concurrency: int | None = None
        self._before: list[Callable[[Batch], Any]] = []
        self._progress: list[Callable[..., Any]] = []
        self._then: list[Callable[..., Any]] = []
        self._catch: list[Callable[..., Any]] = []
        self._finally: list[Callable[..., Any]] = []
        self._results: dict[str | int, Result] = {}
        self._failures: dict[str | int, Result] = {}
        self._started = False
        self._finished = False

    # --- building --------------------------------------------------------

    def request(self) -> PoolRequest:
        return PoolRequest(self, self._factory.pending())

    def as_(self, key: str) -> PoolRequest:
        return self.request().as_(key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.request(), name)

    def enqueue(self, key: str | None, sender: Callable[[], Response]) -> Batch:
        if self._started:
            raise BatchInProgressException(
                "The batch has already been sent; new requests cannot be added."
            )
        if key is None:
            key = self._index
            self._index += 1
        self._jobs.append((key, sender))
        return self

    def concurrency(self, limit: int) -> Batch:
        self._concurrency = limit
        return self

    # --- callbacks -------------------------------------------------------

    def before(self, callback: Callable[[Batch], Any]) -> Batch:
        self._before.append(callback)
        return self

    def progress(self, callback: Callable[..., Any]) -> Batch:
        self._progress.append(callback)
        return self

    def then(self, callback: Callable[..., Any]) -> Batch:
        self._then.append(callback)
        return self

    def catch(self, callback: Callable[..., Any]) -> Batch:
        self._catch.append(callback)
        return self

    def finally_(self, callback: Callable[..., Any]) -> Batch:
        """``finally`` is a Python keyword, hence the trailing underscore."""
        self._finally.append(callback)
        return self

    # --- inspection ------------------------------------------------------

    @property
    def total_requests(self) -> int:
        return len(self._jobs)

    @property
    def pending_requests(self) -> int:
        return self.total_requests - len(self._results)

    @property
    def failed_requests(self) -> int:
        return len(self._failures)

    def processed_requests(self) -> int:
        return len(self._results)

    def finished(self) -> bool:
        return self._finished

    def has_failures(self) -> bool:
        return bool(self._failures)

    def results(self) -> dict[str | int, Result]:
        return dict(self._results)

    # --- running ---------------------------------------------------------

    def send(self) -> dict[str | int, Result]:
        self._start()
        jobs = list(self._jobs)
        if jobs:
            run_jobs(jobs, self._concurrency, self._settle)
        return self._complete(jobs)

    def defer(self) -> Batch:
        """Send the batch in the background and return immediately."""
        self._start()
        thread = threading.Thread(target=self._send_deferred, daemon=True)
        self._thread = thread
        thread.start()
        return self

    def wait(self, timeout: float | None = None) -> dict[str | int, Result]:
        """Block until a deferred batch finishes."""
        thread = getattr(self, "_thread", None)
        if thread is not None:
            thread.join(timeout)
        return self.results()

    def _send_deferred(self) -> None:
        jobs = list(self._jobs)
        if jobs:
            run_jobs(jobs, self._concurrency, self._settle)
        self._complete(jobs)

    def _start(self) -> None:
        if self._started:
            raise BatchInProgressException("The batch has already been sent.")
        self._started = True
        for callback in self._before:
            callback(self)

    def _settle(self, key: str | int, outcome: Result) -> None:
        self._results[key] = outcome
        if _is_failure(outcome):
            self._failures[key] = outcome
            for callback in self._catch:
                callback(self, key, outcome)
            return
        for callback in self._progress:
            callback(self, key, outcome)

    def _complete(self, jobs: list[tuple[str | int, Callable[[], Response]]]) -> dict:
        ordered = {key: self._results[key] for key, _fn in jobs}
        self._results = ordered
        self._finished = True
        if not self._failures:
            for callback in self._then:
                callback(self, ordered)
        for callback in self._finally:
            callback(self, ordered)
        return ordered


def _is_failure(outcome: Result) -> bool:
    if isinstance(outcome, HttpClientException):
        return True
    return outcome.failed()
