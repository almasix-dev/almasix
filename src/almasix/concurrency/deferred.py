"""Deferred tasks — fire and forget, with a handle for tests."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from almasix.concurrency.tasks import Results, Tasks

if TYPE_CHECKING:
    from almasix.concurrency.drivers.base import Driver


class DeferredTasks:
    """Tasks running in the background.

    Laravel defers until after the response is sent. Almasix has no
    post-response hook yet, so the tasks run on a background thread and this
    handle exists for the caller — usually a test — that needs to wait.
    """

    def __init__(self, driver: Driver, tasks: Tasks) -> None:
        self._driver = driver
        self._tasks = tasks
        self._results: Results | None = None
        self._failure: BaseException | None = None
        self._thread = threading.Thread(target=self._work, daemon=True)

    def start(self) -> DeferredTasks:
        self._thread.start()
        return self

    def _work(self) -> None:
        try:
            self._results = self._driver.run(self._tasks)
        except BaseException as exception:
            self._failure = exception

    def finished(self) -> bool:
        return not self._thread.is_alive() and self._thread.ident is not None

    def wait(self, timeout: float | None = None) -> Results:
        """Block for the results, re-raising whatever the tasks raised."""
        self._thread.join(timeout)
        if self._failure is not None:
            raise self._failure
        if self._results is None:
            raise TimeoutError("Deferred tasks did not finish in time.")
        return self._results

    def results(self) -> Results | None:
        return self._results

    def __repr__(self) -> str:
        state = "finished" if self.finished() else "running"
        return f"<DeferredTasks {state}>"

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - defensive
        raise AttributeError(name)
