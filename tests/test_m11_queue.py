"""M11 unit tests — jobs, drivers, workers, failed jobs, commands."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.framework import Application
from almasix.orm import DatabaseManager, set_manager
from almasix.queue import Job, JobMiddleware, ShouldQueue, dispatch, dispatch_sync, ensure_tables
from almasix.queue.dispatcher import Dispatcher
from almasix.queue.helpers import default_queue_config, set_dispatcher, set_manager
from almasix.queue.manager import QueueManager
from almasix.queue.provider import QueueServiceProvider
from almasix.queue.worker import Worker


class CounterJob(Job):
    value: ClassVar[int] = 0

    def __init__(self, amount: int = 1) -> None:
        self.amount = amount

    def handle(self) -> None:
        CounterJob.value += self.amount


class AsyncCounterJob(Job, ShouldQueue):
    value: ClassVar[int] = 0

    async def handle(self) -> None:
        AsyncCounterJob.value += 1


class FailingJob(Job, ShouldQueue):
    tries: ClassVar[int] = 2
    backoff: ClassVar[int] = 0

    def handle(self) -> None:
        raise RuntimeError("boom")


class HookJob(Job, ShouldQueue):
    tries: ClassVar[int] = 1
    failed_called: ClassVar[list[str]] = []

    def handle(self) -> None:
        raise ValueError("nope")

    async def failed(self, exc: BaseException) -> None:
        HookJob.failed_called.append(str(exc))


class TaggedJob(Job, ShouldQueue):
    queue: ClassVar[str] = "emails"
    unique_for: ClassVar[int] = 60

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id

    def unique_id(self) -> str:
        return f"user-{self.user_id}"

    def handle(self) -> None:
        TaggedJob.ran = True  # type: ignore[attr-defined]


TaggedJob.ran = False  # type: ignore[attr-defined]


class LogMiddleware(JobMiddleware):
    log: ClassVar[list[str]] = []

    async def handle(self, job: Job, nxt: Any) -> Any:
        LogMiddleware.log.append("before")
        result = await nxt(job)
        LogMiddleware.log.append("after")
        return result


class MiddlewareJob(Job):
    middleware: ClassVar[list[type[JobMiddleware]]] = [LogMiddleware]

    def handle(self) -> str:
        return "ok"


class ImmediateQueueJob(Job):
    queue: ClassVar[bool] = True
    value: ClassVar[int] = 0

    def handle(self) -> None:
        ImmediateQueueJob.value += 1


class DelayedJob(Job, ShouldQueue):
    delay: ClassVar[int] = 3600
    value: ClassVar[int] = 0

    def handle(self) -> None:
        DelayedJob.value += 1


@pytest.fixture(autouse=True)
def reset_job_state() -> None:
    CounterJob.value = 0
    AsyncCounterJob.value = 0
    ImmediateQueueJob.value = 0
    DelayedJob.value = 0
    HookJob.failed_called = []
    TaggedJob.ran = False
    LogMiddleware.log = []


@pytest.fixture
def sync_manager() -> QueueManager:
    config = default_queue_config()
    manager = QueueManager(config=config)
    dispatcher = Dispatcher(manager)
    set_manager(manager)
    set_dispatcher(dispatcher)
    return manager


@pytest.fixture
async def database_manager(memory_db: DatabaseManager) -> QueueManager:
    await ensure_tables()
    config = {
        "default": "database",
        "connections": {
            "sync": {"driver": "sync"},
            "database": {
                "driver": "database",
                "connection": "sqlite",
                "table": "jobs",
            },
        },
        "failed": {
            "driver": "database",
            "connection": "sqlite",
            "table": "failed_jobs",
        },
    }
    manager = QueueManager(config=config)
    dispatcher = Dispatcher(manager)
    set_manager(manager)
    set_dispatcher(dispatcher)
    return manager


@pytest.mark.asyncio
async def test_sync_dispatch_runs_immediately(sync_manager: QueueManager) -> None:
    await dispatch(CounterJob(3))
    assert CounterJob.value == 3


@pytest.mark.asyncio
async def test_non_queue_job_uses_sync_even_with_database_default(
    database_manager: QueueManager,
) -> None:
    await dispatch(CounterJob(2))
    assert CounterJob.value == 2
    connection = database_manager.connection("database")
    assert await connection.size() == 0


@pytest.mark.asyncio
async def test_should_queue_inserts_into_database(database_manager: QueueManager) -> None:
    await dispatch(AsyncCounterJob())
    assert AsyncCounterJob.value == 0
    connection = database_manager.connection("database")
    assert await connection.size() == 1


@pytest.mark.asyncio
async def test_worker_processes_database_job(database_manager: QueueManager) -> None:
    await dispatch(AsyncCounterJob())
    worker = Worker(database_manager)
    assert await worker.run_once("database") is True
    assert AsyncCounterJob.value == 1
    assert await database_manager.connection("database").size() == 0


@pytest.mark.asyncio
async def test_dispatch_sync_bypasses_queue(database_manager: QueueManager) -> None:
    job = AsyncCounterJob()
    await dispatch_sync(job)
    assert AsyncCounterJob.value == 1
    assert await database_manager.connection("database").size() == 0


@pytest.mark.asyncio
async def test_job_class_dispatch(database_manager: QueueManager) -> None:
    await AsyncCounterJob.dispatch()
    worker = Worker(database_manager)
    await worker.run_once("database")
    assert AsyncCounterJob.value == 1


@pytest.mark.asyncio
async def test_job_serialization_roundtrip() -> None:
    job = CounterJob(5)
    restored = Job.deserialize(job.serialize())
    assert isinstance(restored, CounterJob)
    assert restored.amount == 5


@pytest.mark.asyncio
async def test_failed_job_store_and_retry(database_manager: QueueManager) -> None:
    await dispatch(FailingJob())
    worker = Worker(database_manager)
    await worker.run_once("database")
    await worker.run_once("database")

    from almasix.queue.failed import FailedJobRepository

    repo = FailedJobRepository(database_manager.failed_config())
    rows = await repo.all()
    assert len(rows) == 1

    connection = database_manager.connection("database")
    assert await connection.restore_failed(int(rows[0]["id"])) is True
    assert await worker.run_once("database") is True
    await worker.run_once("database")
    rows_after = await repo.all()
    assert len(rows_after) == 1


@pytest.mark.asyncio
async def test_failed_hook(database_manager: QueueManager) -> None:
    await dispatch(HookJob())
    worker = Worker(database_manager)
    await worker.run_once("database")
    assert HookJob.failed_called == ["nope"]


@pytest.mark.asyncio
async def test_middleware_pipeline(sync_manager: QueueManager) -> None:
    result = await dispatch(MiddlewareJob())
    assert result == "ok"
    assert LogMiddleware.log == ["before", "after"]


@pytest.mark.asyncio
async def test_unique_job_dedup(database_manager: QueueManager) -> None:
    await dispatch(TaggedJob(1))
    await dispatch(TaggedJob(1))
    await dispatch(TaggedJob(2))
    connection = database_manager.connection("database")
    assert await connection.size("emails") == 2


@pytest.mark.asyncio
async def test_queue_provider_registers(tmp_path: Path) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Queue", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "database.py").write_text(
        "config = {'default': 'sqlite', 'connections': {'sqlite': {'driver': 'sqlite', 'database': ':memory:'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")

    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    QueueServiceProvider(app).register()
    QueueServiceProvider(app).boot()

    manager = app.make(QueueManager)
    assert manager.get_default_connection() == "sync"


def test_console_discovers_queue_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Queue", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "logging.py").write_text(
        "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "database.py").write_text(
        "config = {'default': 'sqlite', 'connections': {'sqlite': {'driver': 'sqlite', 'database': ':memory:'}}}\n",
        encoding="utf-8",
    )
    (tmp_path / "config" / "queue.py").write_text(
        """
config = {
    "default": "database",
    "connections": {
        "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
    },
    "failed": {"driver": "database", "connection": "sqlite", "table": "failed_jobs"},
}
""",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    (tmp_path / "bootstrap").mkdir()
    (tmp_path / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    kernel = ConsoleKernel.from_cwd(tmp_path)
    asyncio.run(ensure_tables("sqlite"))

    for name in ("queue:work", "queue:listen", "queue:failed", "queue:retry"):
        assert name in kernel.commands

    AsyncCounterJob.value = 0
    asyncio.run(dispatch(AsyncCounterJob()))
    assert (
        kernel.run_command("queue:work", arguments={}, options={"once": True, "queue": "default"})
        == 0
    )
    assert AsyncCounterJob.value == 1


class SlowJob(ShouldQueue, Job):
    tries: ClassVar[int] = 1
    timeout: ClassVar[float] = 0.05

    async def handle(self) -> None:
        await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_job_timeout_enforced(database_manager: QueueManager) -> None:
    job = SlowJob()
    worker = Worker(database_manager)
    with pytest.raises(TimeoutError, match="timed out"):
        await worker.process_job(job, connection_name="database")


@pytest.mark.asyncio
async def test_queue_true_marker(database_manager: QueueManager) -> None:
    await dispatch(ImmediateQueueJob())
    assert ImmediateQueueJob.value == 0
    assert await database_manager.connection("database").size() == 1


@pytest.mark.asyncio
async def test_delayed_job_not_immediately_available(database_manager: QueueManager) -> None:
    await dispatch(DelayedJob())
    worker = Worker(database_manager)
    assert await worker.run_once("database") is False
    assert DelayedJob.value == 0


@pytest.mark.asyncio
async def test_default_queue_config_shape() -> None:
    config = default_queue_config("sqlite")
    assert config["default"] == "sync"
    assert "sync" in config["connections"]
    assert config["connections"]["database"]["connection"] == "sqlite"
