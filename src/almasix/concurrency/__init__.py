"""Concurrency — ``Concurrency.run`` across threads, forks, or processes."""

from __future__ import annotations

from almasix.concurrency.deferred import DeferredTasks
from almasix.concurrency.drivers import (
    Driver,
    ForkDriver,
    ProcessDriver,
    SyncDriver,
    ThreadDriver,
)
from almasix.concurrency.exceptions import (
    ConcurrencyException,
    TaskFailedException,
    UnsupportedDriverException,
)
from almasix.concurrency.facade import Concurrency, get_manager, set_manager
from almasix.concurrency.manager import BUILT_IN, DEFAULT_DRIVER, ConcurrencyManager
from almasix.concurrency.provider import (
    ConcurrencyServiceProvider,
    default_concurrency_config,
)
from almasix.concurrency.tasks import TaskSet, normalize

__all__ = [
    "BUILT_IN",
    "DEFAULT_DRIVER",
    "Concurrency",
    "ConcurrencyException",
    "ConcurrencyManager",
    "ConcurrencyServiceProvider",
    "DeferredTasks",
    "Driver",
    "ForkDriver",
    "ProcessDriver",
    "SyncDriver",
    "TaskFailedException",
    "TaskSet",
    "ThreadDriver",
    "UnsupportedDriverException",
    "default_concurrency_config",
    "get_manager",
    "normalize",
    "set_manager",
]
