"""Concurrency manager — resolves drivers from ``config/concurrency.py``."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from typing import Any

from almasix.concurrency.deferred import DeferredTasks
from almasix.concurrency.drivers.base import Driver, first_failure
from almasix.concurrency.drivers.multiprocess import ForkDriver, ProcessDriver
from almasix.concurrency.drivers.sync import SyncDriver
from almasix.concurrency.drivers.thread import ThreadDriver
from almasix.concurrency.exceptions import UnsupportedDriverException
from almasix.concurrency.tasks import Results, Tasks, normalize

#: Drivers Almasix ships with. ``thread`` is the default; see the docs page
#: for why Laravel's ``process`` default does not translate.
BUILT_IN: dict[str, type[Driver]] = {
    "fork": ForkDriver,
    "process": ProcessDriver,
    "sync": SyncDriver,
    "thread": ThreadDriver,
}

DEFAULT_DRIVER = "thread"


class ConcurrencyManager:
    """Resolve named concurrency drivers from config."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self.config = dict(config or {})
        self._drivers: dict[str, Driver] = {}
        self._custom: dict[str, Callable[..., Driver]] = {}

    def get_default_driver(self) -> str:
        return str(self.config.get("default") or DEFAULT_DRIVER)

    def set_default_driver(self, name: str) -> None:
        self.config["default"] = name
        self._drivers.pop(name, None)

    def extend(self, driver: str, callback: Callable[..., Driver]) -> ConcurrencyManager:
        """Register a custom driver creator (Laravel ``Concurrency::extend``)."""
        self._custom[driver] = callback
        self._drivers.pop(driver, None)
        return self

    def driver(self, name: str | None = None) -> Driver:
        key = name or self.get_default_driver()
        if key not in self._drivers:
            self._drivers[key] = self._resolve(key)
        return self._drivers[key]

    def forget_driver(self, name: str | None = None) -> None:
        if name is None:
            self._drivers.clear()
        else:
            self._drivers.pop(name, None)

    def _resolve(self, name: str) -> Driver:
        settings = dict((self.config.get("drivers") or {}).get(name) or {})
        if name in self._custom:
            return self._custom[name](self.app, settings, name)
        driver = BUILT_IN.get(str(settings.get("driver") or name))
        if driver is None:
            raise UnsupportedDriverException(
                f"Concurrency driver {name!r} is not supported. "
                f"Available: {', '.join(sorted(BUILT_IN))}."
            )
        return driver(settings)

    # --- running --------------------------------------------------------

    def run(self, tasks: Tasks, driver: str | None = None) -> Results:
        """Run every task concurrently and return their results."""
        return self.driver(driver).run(tasks)

    def defer(self, tasks: Tasks, driver: str | None = None) -> DeferredTasks:
        """Run the tasks in the background without waiting for results."""
        return DeferredTasks(self.driver(driver), tasks).start()

    async def arun(self, tasks: Tasks) -> Results:
        """Await coroutines (or plain callables) concurrently.

        Almasix runs on ASGI, where the natural way to do several things at
        once is the event loop. This has no Laravel counterpart.
        """
        task_set = normalize(tasks)
        if not task_set.tasks:
            return task_set.shape([])
        outcomes = await asyncio.gather(
            *(_awaitable(task) for task in task_set.tasks), return_exceptions=True
        )
        settled = [
            (not isinstance(outcome, BaseException), outcome) for outcome in outcomes
        ]
        first_failure(settled)
        return task_set.shape(list(outcomes))


async def _awaitable(task: Callable[[], Any]) -> Any:
    result = task()
    if inspect.isawaitable(result):
        return await result
    return result
