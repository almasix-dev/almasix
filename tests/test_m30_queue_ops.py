"""M30 — ``queue:restart``, ``queue:clear`` and ``queue:monitor``.

The restart tests are the interesting ones: the signal is only worth anything
if a worker both sees it and refuses to act on it until the job in its hands is
done, so the job itself broadcasts the restart here.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest

from almasix.cache.helpers import get_manager as get_cache_manager
from almasix.cache.helpers import set_manager as set_cache_manager
from almasix.console.kernel import ConsoleKernel
from almasix.console.output import Output
from almasix.events.facade import Event
from almasix.queue import Job, ShouldQueue, ensure_tables
from almasix.queue.connections.redis import RedisQueue
from almasix.queue.events import QueueBusy
from almasix.queue.manager import QueueManager
from almasix.queue.restart import RESTART_KEY, broadcast_restart, last_restart
from almasix.queue.worker import Worker
from tests.support_redis import FakeRedis

Build = Callable[..., ConsoleKernel]


class QuietJob(Job, ShouldQueue):
    """A job that does nothing, for filling a queue up."""

    tries: ClassVar[int] = 1

    def handle(self) -> None:
        return None


class DelayedJob(QuietJob):
    delay: ClassVar[int] = 5


class SignallingJob(Job, ShouldQueue):
    """A deploy lands while this job is halfway through."""

    tries: ClassVar[int] = 1
    trace: ClassVar[list[str]] = []

    def handle(self) -> None:
        SignallingJob.trace.append("started")
        broadcast_restart()
        SignallingJob.trace.append("finished")


def write_app(root: Path, *, cache: str, queue: str, environment: str) -> None:
    """The smallest tree ``ConsoleKernel.from_cwd`` will boot as an application."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap").mkdir(exist_ok=True)
    (root / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    files = {
        "app.py": (
            f'config = {{"name": "M30", "env": "{environment}", "debug": False, "providers": []}}\n'
        ),
        "logging.py": "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        "database.py": (
            "config = {'default': 'sqlite', 'connections': "
            "{'sqlite': {'driver': 'sqlite', 'database': ':memory:'}}}\n"
        ),
        "queue.py": (
            f"config = {{'default': '{queue}', 'connections': {{"
            "'sync': {'driver': 'sync'}, "
            "'database': {'driver': 'database', 'connection': 'sqlite', 'table': 'jobs'}, "
            "'beanstalkd': {'driver': 'beanstalkd'}}, "
            "'failed': {'driver': 'database', 'connection': 'sqlite', 'table': 'failed_jobs'}}\n"
        ),
        "cache.py": (
            f"config = {{'default': '{cache}', 'prefix': '', 'stores': {{"
            "'array': {'driver': 'array'}, "
            f"'file': {{'driver': 'file', 'path': {str(root / 'cache-data')!r}}}}}}}\n"
        ),
    }
    for name, body in files.items():
        (root / "config" / name).write_text(body, encoding="utf-8")


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Build]:
    """Boot a disposable application and hand back its console kernel."""

    def make(
        *,
        cache: str = "file",
        queue: str = "database",
        environment: str = "local",
    ) -> ConsoleKernel:
        write_app(tmp_path, cache=cache, queue=queue, environment=environment)
        monkeypatch.chdir(tmp_path)
        kernel = ConsoleKernel.from_cwd(tmp_path)
        asyncio.run(ensure_tables("sqlite"))
        return kernel

    SignallingJob.trace.clear()
    yield make
    set_cache_manager(None)
    Event.set_dispatcher(None)


def push(kernel: ConsoleKernel, job: Job, connection: str = "database") -> None:
    asyncio.run(kernel.app.make(QueueManager).connection(connection).push(job))


def size(kernel: ConsoleKernel, queue: str = "default", connection: str = "database") -> int:
    return asyncio.run(kernel.app.make(QueueManager).connection(connection).size(queue))


def rows(output: str) -> list[str]:
    """Table lines with their column padding squeezed out."""
    return [" ".join(line.split()) for line in output.splitlines()]


# --- queue:restart ------------------------------------------------------


def test_queue_restart_writes_a_timestamp_to_the_cache(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:restart", []) == 0

    out = capsys.readouterr().out
    assert "Broadcasting queue restart signal." in out
    assert "will stop after their current job" in out
    assert isinstance(get_cache_manager().store().get(RESTART_KEY), float)


def test_a_worker_finishes_the_job_in_hand_then_stops(build: Build) -> None:
    """The restart lands mid-job: that job completes, the next one is left."""
    kernel = build()
    push(kernel, SignallingJob())
    push(kernel, QuietJob())

    worker = Worker(kernel.app.make(QueueManager))
    processed = asyncio.run(worker.run("database", queue="default", sleep=0))

    assert processed == 1
    assert worker.stopped_for_restart is True
    assert SignallingJob.trace == ["started", "finished"]
    assert size(kernel) == 1


def test_queue_work_reports_the_restart_that_stopped_it(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    push(kernel, SignallingJob())

    assert kernel.run_argv("queue:work", ["database", "--queue", "default", "--sleep", "0"]) == 0

    out = capsys.readouterr().out
    assert "Processed 1 job(s)." in out
    assert "Stopping worker: queue:restart was broadcast." in out


def test_queue_listen_reports_the_restart_that_stopped_it(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    push(kernel, SignallingJob())

    assert kernel.run_argv("queue:listen", ["database", "--queue", "default", "--sleep", "0"]) == 0

    assert "Stopping listener: queue:restart was broadcast." in capsys.readouterr().out


def test_queue_work_stops_for_a_restart_that_lands_while_it_is_idle(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The signal arrives between two empty polls, so nothing was processed.

    The broadcast is stubbed because a real one has to land *during* the run,
    which no amount of arranging beforehand can do from this thread.
    """
    kernel = build()
    signals = iter([None, 1.0])  # what the worker booted with, then the deploy
    monkeypatch.setattr("almasix.queue.worker.last_restart", lambda: next(signals))

    assert kernel.run_argv("queue:work", ["database", "--queue", "default", "--sleep", "0"]) == 0

    out = capsys.readouterr().out
    assert "No jobs available." not in out  # that line belongs to --once
    assert "Stopping worker: queue:restart was broadcast." in out


def test_a_worker_keeps_going_between_jobs_until_it_has_its_fill(build: Build) -> None:
    kernel = build()
    push(kernel, QuietJob())
    push(kernel, QuietJob())

    worker = Worker(kernel.app.make(QueueManager))
    processed = asyncio.run(worker.run("database", queue="default", max_jobs=2, sleep=0))

    assert processed == 2
    assert worker.stopped_for_restart is False


def test_a_worker_skips_a_connection_it_cannot_pop_from(build: Build) -> None:
    kernel = build()
    manager = kernel.app.make(QueueManager)
    manager._connections["paper"] = type("PaperQueue", (), {"config": {"driver": "paper"}})()

    assert asyncio.run(Worker(manager).run_once("paper")) is False


def test_a_worker_only_restarts_for_a_signal_newer_than_its_boot(build: Build) -> None:
    kernel = build()
    worker = Worker(kernel.app.make(QueueManager))

    assert worker.should_restart() is False  # nothing broadcast at all

    worker.booted_at = broadcast_restart()
    assert worker.should_restart() is False  # yesterday's deploy

    broadcast_restart(worker.booted_at + 1)
    assert worker.should_restart() is True

    worker.booted_at = None  # booted before the key existed
    assert worker.should_restart() is True


def test_a_signal_that_is_not_a_timestamp_is_ignored(build: Build) -> None:
    build()
    get_cache_manager().store().forever(RESTART_KEY, "sometime on Tuesday")

    assert last_restart() is None


def test_a_worker_without_a_cache_never_restarts(build: Build) -> None:
    build()
    set_cache_manager(None)

    assert last_restart() is None


def test_queue_restart_reports_a_missing_cache(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    set_cache_manager(None)

    assert kernel.run_argv("queue:restart", []) == 1
    assert "Cannot broadcast a restart" in capsys.readouterr().err


def test_queue_restart_warns_when_the_store_is_private_to_this_process(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(cache="array")

    assert kernel.run_argv("queue:restart", []) == 0
    assert "private to this process" in capsys.readouterr().out


# --- queue:clear --------------------------------------------------------


def test_queue_clear_deletes_the_database_queue_and_counts_it(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    push(kernel, QuietJob())
    push(kernel, QuietJob())

    assert kernel.run_argv("queue:clear", ["database", "--queue", "default", "--force"]) == 0

    assert "Cleared 2 job(s) from [database] queue [default]." in capsys.readouterr().out
    assert size(kernel) == 0


def test_queue_clear_empties_a_redis_queue_including_delayed_jobs(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    manager = kernel.app.make(QueueManager)
    manager._connections["redis"] = RedisQueue(
        None,
        {"driver": "redis", "connection": "default", "queue": "queues"},
        manager=manager,
        client=FakeRedis(),
    )
    push(kernel, QuietJob(), connection="redis")
    push(kernel, DelayedJob(), connection="redis")

    assert kernel.run_argv("queue:clear", ["redis", "--force"]) == 0

    assert "Cleared 2 job(s) from [redis] queue [default]." in capsys.readouterr().out
    assert size(kernel, connection="redis") == 0


def test_queue_clear_refuses_the_sync_driver(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:clear", ["sync", "--force"]) == 1

    assert (
        "Clearing is not supported on the [sync] queue driver — it runs every job as it "
        "is dispatched, so none is ever left waiting."
    ) in capsys.readouterr().err


def test_queue_clear_refuses_a_driver_that_stores_nothing(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    manager = kernel.app.make(QueueManager)
    manager._connections["paper"] = type("PaperQueue", (), {"config": {"driver": "paper"}})()

    assert kernel.run_argv("queue:clear", ["paper", "--force"]) == 1

    assert "[paper] queue driver — it has no way to delete jobs" in capsys.readouterr().err


def test_queue_clear_reports_a_connection_that_is_not_configured(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:clear", ["nope", "--force"]) == 1
    assert "Queue connection [nope] is not configured." in capsys.readouterr().err


def test_queue_clear_reports_a_driver_almasix_does_not_have(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:clear", ["beanstalkd", "--force"]) == 1
    assert "Unsupported queue driver: 'beanstalkd'" in capsys.readouterr().err


def test_queue_clear_asks_first_and_leaves_the_queue_alone_when_refused(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    push(kernel, QuietJob())
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: False)

    assert kernel.run_argv("queue:clear", ["database"]) == 1

    out = capsys.readouterr().out
    assert "This deletes every job waiting on [database] queue [default]." in out
    assert "Nothing was changed." in out
    assert size(kernel) == 1


def test_queue_clear_proceeds_once_the_confirmation_is_given(
    build: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel = build()
    push(kernel, QuietJob())
    monkeypatch.setattr(Output, "confirm", lambda *a, **k: True)

    assert kernel.run_argv("queue:clear", ["database"]) == 0
    assert size(kernel) == 0


def test_queue_clear_will_not_touch_production_without_force(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(environment="production")
    push(kernel, QuietJob())

    assert kernel.run_argv("queue:clear", ["database"]) == 1

    assert "Application is in production (production)." in capsys.readouterr().err
    assert size(kernel) == 1


def test_queue_clear_clears_production_when_forced(build: Build) -> None:
    kernel = build(environment="production")
    push(kernel, QuietJob())

    assert kernel.run_argv("queue:clear", ["database", "--force"]) == 0
    assert size(kernel) == 0


def test_queue_clear_falls_back_to_the_default_queue_when_called_in_process(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """``Artisan.call`` passes the options it was given, not the signature's."""
    kernel = build()
    push(kernel, QuietJob())

    code = kernel.run_command(
        "queue:clear", arguments={"connection": "database"}, options={"force": True}
    )

    assert code == 0
    assert "Cleared 1 job(s) from [database] queue [default]." in capsys.readouterr().out


def test_queue_clear_says_which_queue_name_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:clear", ["database", "--queue", "--force"]) == 2
    assert "Invalid value for '--queue'" in capsys.readouterr().err


def test_the_production_guard_assumes_the_worst_without_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.console.confirmable import current_environment

    monkeypatch.setattr("almasix.config._repository", None)

    assert current_environment() == "production"


# --- queue:monitor ------------------------------------------------------


def test_queue_monitor_sizes_each_queue_and_flags_the_busy_ones(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    for _ in range(3):
        push(kernel, QuietJob())
    Event.fake([QueueBusy])

    assert kernel.run_argv("queue:monitor", ["database:default,database:emails", "--max", "3"]) == 0

    table = rows(capsys.readouterr().out)
    assert "database default 3 BUSY" in table
    assert "database emails 0 OK" in table
    busy = Event.get_dispatcher().dispatched()
    assert [(e.connection, e.queue, e.size) for e in busy] == [("database", "default", 3)]


def test_queue_monitor_reads_a_bare_name_as_a_queue_on_the_default_connection(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    Event.fake([QueueBusy])

    assert kernel.run_argv("queue:monitor", ["default"]) == 0

    assert "database default 0 OK" in rows(capsys.readouterr().out)
    Event.assert_nothing_dispatched()


def test_queue_monitor_says_which_max_it_could_not_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:monitor", ["default", "--max", "loads"]) == 2
    assert "Invalid value for '--max': 'loads' is not a valid integer." in capsys.readouterr().err


def test_queue_monitor_needs_at_least_one_queue(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_command("queue:monitor", arguments={"queues": " , "}) == 1
    assert "Name at least one queue" in capsys.readouterr().err


def test_queue_monitor_reports_a_driver_that_cannot_be_sized(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    manager = kernel.app.make(QueueManager)

    class PaperQueue:
        config: ClassVar[dict[str, Any]] = {}

    class VagueQueue:
        config: ClassVar[dict[str, Any]] = {"driver": "vague"}

        async def size(self, queue: str = "default") -> int | None:
            del queue
            return None

    manager._connections["paper"] = PaperQueue()
    manager._connections["vague"] = VagueQueue()

    assert kernel.run_argv("queue:monitor", ["paper:default,vague:default"]) == 1

    captured = capsys.readouterr()
    assert "The [PaperQueue] queue driver cannot report a size." in captured.err
    assert "paper default - unreadable" in rows(captured.out)
    assert "vague default 0 OK" in rows(captured.out)


def test_queue_monitor_reports_a_store_it_cannot_read(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    """No jobs table is a message, not a traceback."""
    kernel = build()
    asyncio.run(_drop_jobs_table())

    assert kernel.run_argv("queue:monitor", ["database:default"]) == 1

    captured = capsys.readouterr()
    assert "Could not size [database] queue [default]: " in captured.err
    assert "database default - unreadable" in rows(captured.out)


def test_queue_clear_reports_a_store_it_cannot_empty(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()
    asyncio.run(_drop_jobs_table())

    assert kernel.run_argv("queue:clear", ["database", "--force"]) == 1
    assert "Could not clear [database] queue [default]: " in capsys.readouterr().err


async def _drop_jobs_table() -> None:
    from almasix.orm.schema import Schema

    await Schema.drop_if_exists("jobs")


def test_queue_monitor_reports_a_connection_that_is_not_configured(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("queue:monitor", ["ghost:default"]) == 1

    captured = capsys.readouterr()
    assert "Queue connection [ghost] is not configured." in captured.err
    assert "unreadable" in captured.out
