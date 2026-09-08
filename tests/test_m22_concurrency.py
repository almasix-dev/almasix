"""M22 Concurrency — drivers, task shapes, deferral, and the async path."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from almasix.concurrency import (
    BUILT_IN,
    DEFAULT_DRIVER,
    Concurrency,
    ConcurrencyManager,
    ConcurrencyServiceProvider,
    DeferredTasks,
    Driver,
    ForkDriver,
    ProcessDriver,
    SyncDriver,
    TaskFailedException,
    TaskSet,
    ThreadDriver,
    UnsupportedDriverException,
    default_concurrency_config,
    get_manager,
    normalize,
    set_manager,
)
from almasix.framework.application import Application

FORK_ONLY = pytest.mark.skipif(
    "fork" not in __import__("multiprocessing").get_all_start_methods(),
    reason="the fork start method is not available on this platform",
)


@pytest.fixture(autouse=True)
def fresh_manager() -> Iterator[ConcurrencyManager]:
    manager = ConcurrencyManager(config=default_concurrency_config())
    set_manager(manager)
    yield manager
    set_manager(None)


def boom() -> None:
    raise ValueError("boom")


# --- task shapes --------------------------------------------------------


def test_a_list_of_tasks_returns_a_list_in_order() -> None:
    assert Concurrency.run([lambda: 1, lambda: 2, lambda: 3]) == [1, 2, 3]


def test_a_mapping_of_tasks_keeps_its_keys() -> None:
    results = Concurrency.run({"users": lambda: 10, "orders": lambda: 4})
    assert results == {"users": 10, "orders": 4}


def test_a_single_callable_is_wrapped() -> None:
    assert Concurrency.run(lambda: "only") == ["only"]


def test_no_tasks_is_not_an_error() -> None:
    assert Concurrency.run([]) == []
    assert Concurrency.run({}) == {}


def test_normalize_describes_the_shape() -> None:
    task_set = normalize({"a": lambda: 1})
    assert isinstance(task_set, TaskSet)
    assert task_set.keyed is True
    assert len(task_set) == 1
    assert task_set.shape([9]) == {"a": 9}
    assert normalize([lambda: 1]).shape([9]) == [9]


# --- drivers ------------------------------------------------------------


def test_the_default_driver_is_thread() -> None:
    assert DEFAULT_DRIVER == "thread"
    assert Concurrency.get_default_driver() == "thread"
    assert isinstance(Concurrency.driver(), ThreadDriver)


def test_every_built_in_driver_runs_the_same_tasks() -> None:
    for name in ("thread", "sync"):
        assert Concurrency.run([lambda: 1, lambda: 2], name) == [1, 2]
    assert set(BUILT_IN) == {"fork", "process", "sync", "thread"}


def test_the_thread_driver_actually_overlaps() -> None:
    started = time.monotonic()
    Concurrency.run([lambda: time.sleep(0.2), lambda: time.sleep(0.2), lambda: time.sleep(0.2)])
    assert time.monotonic() - started < 0.5


def test_the_thread_pool_honours_max_workers() -> None:
    driver = ThreadDriver({"max_workers": 1})
    assert driver.run([lambda: 1, lambda: 2]) == [1, 2]


def test_the_sync_driver_runs_in_order_on_this_thread() -> None:
    order: list[int] = []
    SyncDriver().run([lambda: order.append(1), lambda: order.append(2)])
    assert order == [1, 2]


@FORK_ONLY
def test_the_fork_driver_runs_tasks_in_child_processes() -> None:
    pids = Concurrency.run([os.getpid, os.getpid], "fork")
    assert os.getpid() not in pids
    assert len(set(pids)) == 2


@FORK_ONLY
def test_the_fork_driver_accepts_closures() -> None:
    answer = 42
    assert Concurrency.run([lambda: answer * 2], "fork") == [84]


def test_the_process_driver_runs_picklable_tasks() -> None:
    pids = Concurrency.run([os.getpid], "process")
    assert pids[0] != os.getpid()


def test_the_process_driver_rejects_unpicklable_tasks() -> None:
    with pytest.raises(UnsupportedDriverException, match="must be picklable"):
        Concurrency.run([lambda: 1], "process")


def test_an_unknown_driver_is_named_in_the_error() -> None:
    with pytest.raises(UnsupportedDriverException, match="'nope' is not supported"):
        Concurrency.driver("nope")


def test_an_unavailable_start_method_is_reported() -> None:
    class ImaginaryDriver(ForkDriver):
        name = "imaginary"
        start_method = "telepathy"

    with pytest.raises(UnsupportedDriverException, match="does not support"):
        ImaginaryDriver().run([lambda: 1])


def test_drivers_describe_themselves() -> None:
    assert repr(ThreadDriver()) == "<ThreadDriver name='thread'>"
    assert ProcessDriver().name == "process"


def test_the_base_driver_is_abstract() -> None:
    with pytest.raises(NotImplementedError):
        Driver().run([lambda: 1])


# --- failures -----------------------------------------------------------


def test_a_failing_task_raises_after_the_others_settle() -> None:
    finished: list[str] = []

    def slow() -> str:
        time.sleep(0.05)
        finished.append("slow")
        return "slow"

    with pytest.raises(ValueError, match="boom"):
        Concurrency.run([boom, slow])
    assert finished == ["slow"]


def test_the_sync_driver_stops_at_the_first_failure() -> None:
    with pytest.raises(ValueError, match="boom"):
        Concurrency.run([boom, lambda: 1], "sync")


@FORK_ONLY
def test_a_failure_in_a_child_process_reaches_the_caller() -> None:
    with pytest.raises(ValueError, match="boom"):
        Concurrency.run([boom], "fork")


@FORK_ONLY
def test_a_child_that_dies_without_answering_is_reported() -> None:
    with pytest.raises(TaskFailedException, match="exited with code"):
        Concurrency.run([lambda: os._exit(7)], "fork")


# --- deferral -----------------------------------------------------------


def test_deferred_tasks_run_in_the_background() -> None:
    seen: list[str] = []
    deferred = Concurrency.defer([lambda: seen.append("ran")])
    assert isinstance(deferred, DeferredTasks)
    assert deferred.wait() == [None]
    assert seen == ["ran"]
    assert deferred.finished()
    assert deferred.results() == [None]
    assert "finished" in repr(deferred)


def test_deferred_failures_surface_on_wait() -> None:
    deferred = Concurrency.defer([boom])
    with pytest.raises(ValueError, match="boom"):
        deferred.wait()


def test_waiting_on_unfinished_deferred_tasks_times_out() -> None:
    deferred = Concurrency.defer([lambda: time.sleep(0.5)])
    assert "running" in repr(deferred)
    with pytest.raises(TimeoutError):
        deferred.wait(timeout=0.01)


# --- the async path -----------------------------------------------------


@pytest.mark.asyncio
async def test_arun_awaits_coroutines_concurrently() -> None:
    import asyncio

    async def slow(value: str) -> str:
        await asyncio.sleep(0.05)
        return value

    started = time.monotonic()
    results = await Concurrency.arun([lambda: slow("a"), lambda: slow("b")])
    assert results == ["a", "b"]
    assert time.monotonic() - started < 0.2


@pytest.mark.asyncio
async def test_arun_also_accepts_plain_callables_and_keys() -> None:
    results = await Concurrency.arun({"plain": lambda: 1})
    assert results == {"plain": 1}
    assert await Concurrency.arun([]) == []


@pytest.mark.asyncio
async def test_arun_raises_the_first_failure() -> None:
    with pytest.raises(ValueError, match="boom"):
        await Concurrency.arun([boom, lambda: 1])


# --- the manager --------------------------------------------------------


def test_drivers_are_resolved_once_and_can_be_forgotten() -> None:
    manager = get_manager()
    first = manager.driver("thread")
    assert manager.driver("thread") is first
    manager.forget_driver("thread")
    assert manager.driver("thread") is not first
    manager.forget_driver()
    assert manager.driver("thread") is not first


def test_the_default_driver_can_be_changed() -> None:
    Concurrency.set_default_driver("sync")
    assert isinstance(Concurrency.driver(), SyncDriver)


def test_a_manager_without_config_still_has_a_default() -> None:
    set_manager(ConcurrencyManager())
    assert Concurrency.get_default_driver() == "thread"
    assert Concurrency.run([lambda: 1]) == [1]


def test_extend_registers_a_custom_driver() -> None:
    class DoublingDriver(Driver):
        name = "doubling"

        def execute(self, tasks: TaskSet) -> list[Any]:
            return [task() * 2 for task in tasks.tasks]

    Concurrency.extend("doubling", lambda _app, config, _name: DoublingDriver(config))
    assert Concurrency.run([lambda: 21], "doubling") == [42]
    assert isinstance(Concurrency.driver("doubling"), DoublingDriver)


def test_a_config_entry_may_point_at_another_driver() -> None:
    set_manager(
        ConcurrencyManager(config={"default": "fast", "drivers": {"fast": {"driver": "sync"}}})
    )
    assert isinstance(Concurrency.driver(), SyncDriver)


# --- container wiring ---------------------------------------------------


def test_the_provider_binds_and_boots_the_manager() -> None:
    app = Application(base_path=Path.cwd())
    provider = ConcurrencyServiceProvider(app)
    provider.register()
    manager = app.make(ConcurrencyManager)
    assert app.make("concurrency") is manager
    provider.boot()
    assert get_manager() is manager
    assert Concurrency.manager() is manager


def test_the_provider_reads_application_config() -> None:
    app = Application(base_path=Path.cwd())
    app.config.set("concurrency", {"default": "sync"})
    ConcurrencyServiceProvider(app).register()
    assert app.make(ConcurrencyManager).get_default_driver() == "sync"


def test_boot_without_a_binding_leaves_the_manager_alone() -> None:
    app = Application(base_path=Path.cwd())
    manager = get_manager()
    ConcurrencyServiceProvider(app).boot()
    assert get_manager() is manager


def test_get_manager_creates_one_on_demand() -> None:
    set_manager(None)
    assert isinstance(get_manager(), ConcurrencyManager)
