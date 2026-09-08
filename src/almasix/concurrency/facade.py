"""``Concurrency`` façade."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from almasix.concurrency.deferred import DeferredTasks
from almasix.concurrency.drivers.base import Driver
from almasix.concurrency.manager import ConcurrencyManager
from almasix.concurrency.tasks import Results, Tasks

_manager: ConcurrencyManager | None = None


def get_manager() -> ConcurrencyManager:
    global _manager
    if _manager is None:
        _manager = ConcurrencyManager()
    return _manager


def set_manager(manager: ConcurrencyManager | None) -> None:
    global _manager
    _manager = manager


class Concurrency:
    """Static façade over the concurrency manager."""

    @classmethod
    def manager(cls) -> ConcurrencyManager:
        return get_manager()

    @classmethod
    def set_manager(cls, manager: ConcurrencyManager | None) -> None:
        set_manager(manager)

    @classmethod
    def driver(cls, name: str | None = None) -> Driver:
        return cls.manager().driver(name)

    @classmethod
    def extend(cls, driver: str, callback: Callable[..., Driver]) -> ConcurrencyManager:
        return cls.manager().extend(driver, callback)

    @classmethod
    def get_default_driver(cls) -> str:
        return cls.manager().get_default_driver()

    @classmethod
    def set_default_driver(cls, name: str) -> None:
        cls.manager().set_default_driver(name)

    @classmethod
    def run(cls, tasks: Tasks, driver: str | None = None) -> Results:
        return cls.manager().run(tasks, driver)

    @classmethod
    def defer(cls, tasks: Tasks, driver: str | None = None) -> DeferredTasks:
        return cls.manager().defer(tasks, driver)

    @classmethod
    async def arun(cls, tasks: Tasks) -> Results:
        return await cls.manager().arun(tasks)

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - defensive
        raise AttributeError(name)
