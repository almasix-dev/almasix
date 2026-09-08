"""Push Digging Deeper coverage toward 100% — schedule, storage:link, queue:failed."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from avalon.cache import CacheManager, set_manager
from avalon.console.commands.queue_failed import QueueFailedCommand, QueueRetryCommand
from avalon.console.commands.storage_link import StorageLinkCommand
from avalon.console.mutex import Mutex
from avalon.console.scheduling import Event, Schedule, _cron_matches, _field_matches, run_event
from avalon.framework.application import Application
from avalon.queue.helpers import default_queue_config, set_manager as set_queue_manager
from avalon.queue.manager import QueueManager


def test_schedule_frequencies_filters_and_command_runner(tmp_path: Path) -> None:
    assert Event("m").every_minute().expression == "* * * * *"
    assert Event("h").hourly().expression == "0 * * * *"
    assert Event("d").daily().expression == "0 0 * * *"
    assert Event("f").every_five_minutes().expression == "*/5 * * * *"
    assert Event("c").cron("1 2 3 4 5").expression == "1 2 3 4 5"

    monday = datetime(2026, 9, 7, 12, 0, 0)
    saturday = datetime(2026, 9, 5, 12, 0, 0)
    # A day constraint writes the cron day field, so cron() comes first now.
    assert Event("wd").cron("* * * * *").weekdays().is_due(monday)
    assert Event("we").cron("* * * * *").weekends().is_due(saturday)
    assert Event("wo").withoutOverlapping().prevents_overlapping is True

    assert _field_matches("*", 10, 0, 59)
    assert _field_matches("*/5", 10, 0, 59)
    assert _field_matches("8-12", 10, 0, 59)
    assert _field_matches("3,10,15", 10, 0, 59)
    assert not _field_matches("3,15", 10, 0, 59)
    with pytest.raises(ValueError):
        _cron_matches("* * *", monday)

    sched = Schedule()
    sched.call(lambda: None, description="named").every_minute()
    sched.command("inspire").hourly()
    assert sched.due_events(datetime(2026, 9, 5, 10, 0, 0))

    seen: list[str] = []
    code = run_event(
        Event("inspire", command="inspire"),
        base_path=tmp_path,
        runner=lambda name: seen.append(name) or 9,
    )
    assert code == 9 and seen == ["inspire"]
    assert run_event(Event("noop"), base_path=tmp_path) == 0


def test_schedule_cache_lock_busy_and_filesystem_fallback(tmp_path: Path) -> None:
    set_manager(None)
    # Filesystem fallback when cache not booted
    event = Event("fs", callback=lambda: None).without_overlapping_lock()
    assert run_event(event, base_path=tmp_path) == 0
    held = Mutex(tmp_path, event.mutex_name())
    assert held.acquire() is True
    assert run_event(event, base_path=tmp_path) == 0  # skipped
    held.release()

    # Cache lock busy → skip
    manager = CacheManager(config={"default": "array", "stores": {"array": {"driver": "array"}}})
    set_manager(manager)
    lock = manager.store().lock(f"schedule:{event.mutex_name()}", seconds=30)
    assert lock.get() is True
    assert run_event(event, base_path=tmp_path) == 0
    lock.release()
    set_manager(None)


def test_storage_link_defaults_and_force_directory(tmp_path: Path) -> None:
    app = Application(tmp_path)
    (tmp_path / "storage" / "app" / "public").mkdir(parents=True)
    (tmp_path / "public").mkdir()
    # No links config → default public/storage
    app.config.set("filesystems", {})
    cmd = StorageLinkCommand(app)
    assert cmd.handle() == 0
    # Exists without --force → warn + continue
    assert cmd.handle() == 0
    # Directory in the way with --force → error
    link = tmp_path / "public" / "storage"
    if link.is_symlink() or link.is_file():
        link.unlink()
    link.mkdir()
    cmd_force = StorageLinkCommand(app)
    cmd_force._options = {"force": True, "relative": False}  # noqa: SLF001
    assert cmd_force.handle() == 1


def test_queue_failed_empty_and_retry_non_database(tmp_path: Path) -> None:
    app = Application(tmp_path)
    config = default_queue_config()
    # Sync-only — no database connection for retry isinstance check
    config["connections"] = {"sync": {"driver": "sync"}}
    config["default"] = "sync"
    config["failed"] = {"driver": "null", "database": None, "table": "failed_jobs"}
    manager = QueueManager(config)
    set_queue_manager(manager)
    app.container.instance(QueueManager, manager)

    failed = QueueFailedCommand(app)
    # FailedJobRepository with null/missing may error — use memory sqlite failed table path
    config2 = default_queue_config()
    config2["failed"] = {"driver": "database", "database": "sqlite", "table": "failed_jobs"}
    # Ensure empty list path: mock repo.all
    from unittest.mock import AsyncMock, patch

    with patch(
        "avalon.console.commands.queue_failed.FailedJobRepository.all",
        new_callable=AsyncMock,
        return_value=[],
    ):
        # Still need a manager with failed_config
        qm = QueueManager(default_queue_config())
        set_queue_manager(qm)
        app.container.instance(QueueManager, qm)
        assert failed.handle() == 0

    retry = QueueRetryCommand(app)
    # connection("database") KeyError
    qm2 = QueueManager({"default": "sync", "connections": {"sync": {"driver": "sync"}}, "failed": {}})
    set_queue_manager(qm2)
    app.container.instance(QueueManager, qm2)
    assert retry.handle() == 1

    # database key present but not DatabaseQueue
    class FakeConn:
        pass

    qm3 = QueueManager(default_queue_config())
    set_queue_manager(qm3)
    app.container.instance(QueueManager, qm3)
    with patch.object(qm3, "connection", return_value=FakeConn()):
        assert retry.handle() == 1
    set_queue_manager(None)
