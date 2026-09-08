"""M10–M13 coverage fill — branch and edge-case tests for ≥98% coverage."""

from __future__ import annotations

import asyncio
import builtins
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from almasix.filesystem.adapter import Visibility, coerce_bytes, normalize_path
from almasix.filesystem.drivers.local import LocalAdapter
from almasix.filesystem.drivers.memory import MemoryAdapter
from almasix.filesystem.drivers.s3 import S3Adapter
from almasix.filesystem.manager import Storage, StorageManager
from almasix.filesystem.provider import FilesystemServiceProvider
from almasix.filesystem.storage import Disk
from almasix.framework import Application
from almasix.mail import Mail, Mailable
from almasix.mail.helpers import default_mail_config
from almasix.mail.mailable import Content, Envelope
from almasix.mail.mailer import _dispatch_to_queue
from almasix.mail.markdown import render_content, render_markdown_component
from almasix.mail.message import SentMessage
from almasix.mail.provider import MailServiceProvider
from almasix.notifications.channels import ArrayChannel, MailChannel
from almasix.notifications.database import DatabaseNotificationStore, _notifiable_id
from almasix.notifications.messages import ResetPasswordNotification
from almasix.notifications.notifiable import Notifiable
from almasix.notifications.notification import Notification, ShouldQueue
from almasix.notifications.provider import NotificationServiceProvider
from almasix.notifications.sender import NotificationSender
from almasix.notifications.verification import MustVerifyEmail
from almasix.orm import DatabaseManager, set_manager
from almasix.queue.connections.database import DatabaseQueue
from almasix.queue.connections.sync import SyncQueue, _fallback_manager
from almasix.queue.dispatcher import Dispatcher
from almasix.queue.failed import FailedJobRepository, report_failure
from almasix.queue.helpers import dispatch, set_dispatcher, set_manager
from almasix.queue.job import Job, JobMiddleware, _import_job_class
from almasix.queue.manager import QueueManager
from almasix.queue.worker import Worker, _backoff_delay
from almasix.queue import ShouldQueue as JobShouldQueue, ensure_tables as ensure_queue_tables
from almasix.notifications import ensure_tables as ensure_notification_tables
from tests.orm_support import memory_db


# ---------------------------------------------------------------------------
# Filesystem — adapter, storage, manager, drivers
# ---------------------------------------------------------------------------


class _StrStream:
    def read(self) -> str:
        return "stream-text"


def test_coerce_bytes_from_str_stream() -> None:
    assert coerce_bytes(_StrStream()) == b"stream-text"


class _MinimalAdapter:
    """Adapter without write_stream — exercises Disk.write_stream fallback."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    def put(
        self,
        path: str,
        contents: bytes | str | BytesIO,
        *,
        visibility: Visibility | None = None,
    ) -> str:
        del visibility
        if isinstance(contents, BytesIO):
            data = contents.read()
        elif isinstance(contents, str):
            data = contents.encode()
        else:
            data = contents
        self.store[path] = data
        return path

    def get(self, path: str) -> bytes:
        return self.store[path]

    def read_stream(self, path: str) -> BytesIO:
        return BytesIO(self.get(path))

    def exists(self, path: str) -> bool:
        return path in self.store

    def delete(self, path: str) -> bool:
        return self.store.pop(path, None) is not None

    def copy(self, source: str, destination: str) -> bool:
        self.store[destination] = self.store[source]
        return True

    def move(self, source: str, destination: str) -> bool:
        self.copy(source, destination)
        self.delete(source)
        return True

    def size(self, path: str) -> int:
        return len(self.get(path))

    def files(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        del directory, recursive
        return list(self.store)

    def directories(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        del directory, recursive
        return []

    def make_directory(self, path: str) -> bool:
        del path
        return True

    def delete_directory(self, path: str) -> bool:
        del path
        return True

    def url(self, path: str) -> str:
        return f"/mem/{path}"

    def temporary_url(self, path: str, expiration: Any, **options: Any) -> str:
        del expiration, options
        return self.url(path)

    def set_visibility(self, path: str, visibility: Visibility) -> bool:
        del path, visibility
        return True

    def get_visibility(self, path: str) -> Visibility:
        del path
        return "private"


def test_disk_facade_methods(tmp_path: Path) -> None:
    manager = StorageManager(
        app=Application(tmp_path),
        config={
            "default": "local",
            "cloud": "memory",
            "disks": {
                "local": {"driver": "local", "root": str(tmp_path / "app")},
                "memory": {"driver": "memory"},
            },
        },
    )
    manager.set_config(
        {
            "default": "local",
            "cloud": "memory",
            "disks": {
                "local": {"driver": "local", "root": str(tmp_path / "app")},
                "memory": {"driver": "memory"},
            },
        }
    )
    disk = manager.disk()
    disk.put("a.txt", "hello")
    assert disk.get_string("a.txt") == "hello"
    assert disk.missing("nope")
    assert disk.all_files() == ["a.txt"]
    assert disk.delete("a.txt") is True
    assert disk.delete("nope") is False
    assert manager.cloud().put("c.txt", b"cloud") == "c.txt"

    Storage.set_manager(manager)
    assert Storage.cloud().exists("c.txt")
    with pytest.raises(RuntimeError, match="temporary URLs"):
        Storage.temporary_url("c.txt", 30)
    assert Storage.path("c.txt").endswith("c.txt")
    Storage.set_manager(None)


def test_disk_put_file_variants(tmp_path: Path) -> None:
    disk = Disk("local", LocalAdapter(tmp_path))

    class NamedPathFile:
        name = Path("nested.bin")

        def read(self) -> bytes:
            return b"path-name"

    stored = disk.put_file("uploads", NamedPathFile())
    assert stored.endswith("nested.bin")
    assert disk.get(stored) == b"path-name"

    source = tmp_path / "ext.dat"
    source.write_bytes(b"external")
    assert disk.put_file("uploads/ext.dat", source) == "uploads/ext.dat"

    class AwaitableRead:
        filename = "bad.txt"

        def read(self) -> Any:
            async def _inner() -> bytes:
                return b"x"

            return _inner()

    with pytest.raises(TypeError, match="put_file_async"):
        disk.put_file("dir", AwaitableRead())

    with pytest.raises(TypeError, match="Unsupported upload"):
        disk.put_file("dir", object())

    class AsyncUpload:
        filename = "async.txt"

        async def read(self) -> bytes:
            return b"async-data"

    async def _run() -> str:
        return await disk.put_file_async("async-dir", AsyncUpload())

    assert asyncio.run(_run()) == "async-dir/async.txt"


def test_disk_write_stream_fallback() -> None:
    adapter = _MinimalAdapter()
    disk = Disk("min", adapter)
    disk.write_stream("stream.bin", BytesIO(b"fallback"))
    assert adapter.store["stream.bin"] == b"fallback"


def test_disk_path_unsupported() -> None:
    disk = Disk("mem", MemoryAdapter())
    with pytest.raises(RuntimeError, match="does not expose local paths"):
        disk.path("x")


def test_storage_manager_public_and_s3_drivers(tmp_path: Path) -> None:
    mock_client = MagicMock()
    mock_client.put_object.return_value = {}
    mock_client.get_object.return_value = {"Body": BytesIO(b"s3")}
    mock_client.head_object.return_value = {"ContentLength": 2}
    mock_client.get_paginator.return_value.paginate.return_value = [{"Contents": []}]
    mock_client.list_objects_v2.return_value = {}
    mock_client.generate_presigned_url.return_value = "https://signed"
    mock_client.get_object_acl.return_value = {"Grants": []}

    app = Application(tmp_path)
    manager = StorageManager(
        app,
        {
            "default": "local",
            "cloud": "s3",
            "disks": {
                "public": {"driver": "public"},
                "s3": {"driver": "s3", "bucket": "b", "client": mock_client},
            },
        },
    )
    pub = manager.disk("public")
    pub.put("pub.txt", "visible")
    assert pub.url("pub.txt").startswith("/storage/")
    s3 = manager.disk("s3")
    assert s3.put("k.txt", b"v") == "k.txt"


def test_s3_adapter_session_creation_and_branches() -> None:
    client = MagicMock()
    client.put_object.return_value = {}
    client.get_object.return_value = {"Body": BytesIO(b"data")}
    client.head_object.side_effect = [Exception(), {"ContentLength": 4}]
    client.get_paginator.return_value.paginate.return_value = [
        {"Contents": [{"Key": "root/top.txt"}, {"Key": "root/nested/deep.txt"}]}
    ]
    client.list_objects_v2.return_value = {"CommonPrefixes": [{"Prefix": "root/sub/"}]}
    client.generate_presigned_url.return_value = "https://signed"
    client.get_object_acl.side_effect = Exception()

    mock_boto3 = MagicMock()
    session = MagicMock()
    session.client.return_value = client
    mock_boto3.session.Session.return_value = session
    import sys

    with patch.dict(sys.modules, {"boto3": mock_boto3}):
        adapter = S3Adapter(
            bucket="my-bucket",
            root="root",
            key="k",
            secret="s",
            region="us-east-1",
            endpoint="http://minio.local",
        )

    assert adapter._key("") == "root"
    assert adapter.exists("missing") is False
    assert adapter.get("top.txt") == b"data"
    assert adapter.size("top.txt") == 4
    assert "top.txt" in adapter.files("", recursive=False)
    assert "nested/deep.txt" not in adapter.files("", recursive=False)
    assert adapter.directories("") == ["sub"]
    assert adapter.url("a.txt") == "https://my-bucket.s3.amazonaws.com/root/a.txt"
    assert adapter.temporary_url("a.txt", timedelta(seconds=30)) == "https://signed"
    assert adapter.temporary_url("a.txt", datetime.now(timezone.utc) + timedelta(hours=1)) == "https://signed"
    assert adapter.temporary_url("a.txt", 120) == "https://signed"
    adapter.set_visibility("a.txt", "public")
    adapter.set_visibility("a.txt", "private")
    assert adapter.get_visibility("a.txt") == "private"


def test_memory_adapter_edge_cases() -> None:
    disk = MemoryAdapter()
    with pytest.raises(FileNotFoundError):
        disk.get("missing.txt")

    disk.make_directory("tree")
    disk.put("tree/a.txt", "a")
    disk.put("tree/b/c.txt", "bc")
    assert disk.files("tree", recursive=False) == ["tree/a.txt"]
    assert "tree/b" in disk.directories("tree", recursive=True)
    assert disk.read_stream("tree/a.txt").read() == b"a"

    disk.make_directory("empty-dir")
    assert disk.delete("empty-dir") is True

    until = datetime.now(timezone.utc) + timedelta(hours=1)
    with pytest.raises(RuntimeError, match="temporary URLs"):
        disk.temporary_url("tree/a.txt", until)
    with pytest.raises(RuntimeError, match="temporary URLs"):
        disk.temporary_url("tree/a.txt", 45)


def test_local_adapter_edge_cases(tmp_path: Path) -> None:
    root = tmp_path / "root"
    adapter = LocalAdapter(root)
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    link = root / "escape-link"
    link.symlink_to(outside)

    with pytest.raises(ValueError, match="escapes disk root"):
        adapter.get("escape-link")

    class StrChunkStream:
        def __init__(self) -> None:
            self._done = False

        def read(self, size: int = -1) -> str | bytes:
            del size
            if self._done:
                return b""
            self._done = True
            return "chunk"

    adapter.write_stream("str-chunk.txt", StrChunkStream())  # type: ignore[arg-type]
    assert adapter.get("str-chunk.txt") == b"chunk"

    assert adapter.delete("missing") is False
    adapter.make_directory("srcdir")
    adapter.put("srcdir/item.txt", "item")
    adapter.copy("srcdir", "dstdir")
    assert adapter.exists("dstdir/item.txt")
    assert adapter.files("ghost") == []
    assert adapter.directories("ghost") == []
    assert adapter.delete_directory("ghost") is False

    adapter.put("chmod.txt", b"x")
    adapter.set_visibility("chmod.txt", "public")
    with patch.object(Path, "chmod", side_effect=OSError("nope")):
        assert adapter.set_visibility("chmod.txt", "private") is True

    assert adapter.path() == str(root.resolve())
    assert adapter.path("chmod.txt").endswith("chmod.txt")

    until = datetime.now(timezone.utc) + timedelta(minutes=5)
    with pytest.raises(RuntimeError, match="temporary URLs"):
        adapter.temporary_url("chmod.txt", until)
    with pytest.raises(RuntimeError, match="temporary URLs"):
        adapter.temporary_url("chmod.txt", 90)


def test_filesystem_provider_rewrites_relative_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.filesystem import helpers as fs_helpers

    monkeypatch.setattr(
        fs_helpers,
        "default_filesystems_config",
        lambda _base: {
            "default": "local",
            "disks": {"local": {"driver": "local", "root": "storage/app"}},
        },
    )
    app = Application(tmp_path)
    app.config.set("filesystems", {})
    FilesystemServiceProvider(app).register()
    FilesystemServiceProvider(app).boot()
    manager = app.make(StorageManager)
    local_root = manager.disk("local").adapter.root
    assert str(local_root).startswith(str(tmp_path.resolve()))


# ---------------------------------------------------------------------------
# Queue — sync, worker, failed, job, dispatcher, database
# ---------------------------------------------------------------------------


class _CounterJob(Job):
    value: ClassVar[int] = 0

    def handle(self) -> None:
        _CounterJob.value += 1


class NotAJob:
    """Non-job class for ``_import_job_class`` error testing."""


class _RetryJob(Job, JobShouldQueue):
    tries: ClassVar[int] = 3
    backoff: ClassVar[list[int]] = [5, 10]

    def handle(self) -> None:
        raise RuntimeError("retry")


class _HookFailJob(Job, JobShouldQueue):
    tries: ClassVar[int] = 1

    def handle(self) -> None:
        raise ValueError("fail")

    async def failed(self, exc: BaseException) -> None:
        del exc
        raise RuntimeError("hook boom")


class _ExplicitConnJob(Job, JobShouldQueue):
    connection: ClassVar[str] = "database"
    ran: ClassVar[bool] = False

    def handle(self) -> None:
        _ExplicitConnJob.ran = True


@pytest.mark.asyncio
async def test_sync_queue_pop_size_and_fallback_manager() -> None:
    queue = SyncQueue(None, {"driver": "sync"})
    assert await queue.pop() is None
    assert await queue.size("default") == 0

    fallback = _fallback_manager(None, {"driver": "sync"})
    queue_no_mgr = SyncQueue(None, {"driver": "sync"}, manager=None)
    _CounterJob.value = 0
    await queue_no_mgr.push(_CounterJob())
    assert _CounterJob.value == 1
    assert fallback.get_default_connection() == "sync"


@pytest.mark.asyncio
async def test_queue_manager_set_config_and_errors() -> None:
    manager = QueueManager(config={"default": "sync", "connections": {"sync": {"driver": "sync"}}})
    manager.set_config({"default": "sync", "connections": {"sync": {"driver": "sync"}}})
    with pytest.raises(KeyError, match="not configured"):
        manager.connection("missing")
    with pytest.raises(ValueError, match="Unsupported queue driver"):
        QueueManager(
            config={"default": "carrier", "connections": {"carrier": {"driver": "pigeon"}}}
        ).connection("carrier")


@pytest.mark.asyncio
async def test_worker_idle_sleep_and_non_database_run_once(
    memory_db: DatabaseManager,
) -> None:
    del memory_db
    await ensure_queue_tables()
    config = {
        "default": "database",
        "connections": {
            "sync": {"driver": "sync"},
            "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        },
        "failed": {"driver": "database", "connection": "sqlite", "table": "failed_jobs"},
    }
    manager = QueueManager(config=config)
    worker = Worker(manager)

    assert await worker.run_once("sync") is False

    async def cancel_sleep(_delay: float) -> None:
        raise asyncio.CancelledError()

    with patch("asyncio.sleep", cancel_sleep):
        with pytest.raises(asyncio.CancelledError):
            await worker.run("database", once=False)

    assert await worker.run("database", once=True) == 0


@pytest.mark.asyncio
async def test_worker_backoff_and_failed_hook_exception(
    memory_db: DatabaseManager,
) -> None:
    del memory_db
    await ensure_queue_tables()

    config = {
        "default": "database",
        "connections": {
            "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        },
        "failed": {"driver": "database", "connection": "sqlite", "table": "failed_jobs"},
    }
    manager = QueueManager(config=config)
    set_manager(manager)
    set_dispatcher(Dispatcher(manager))

    await dispatch(_RetryJob())
    worker = Worker(manager)
    await worker.run_once("database")
    assert _backoff_delay(_RetryJob(), 1) == 5
    assert _backoff_delay(_RetryJob(), 5) == 10

    class IntBackoff(Job):
        backoff: ClassVar[int] = 7

    assert _backoff_delay(IntBackoff(), 1) == 7
    assert _backoff_delay(Job(), 1) == 0

    await dispatch(_HookFailJob())
    await worker.run_once("database")
    await worker.run_once("database")


@pytest.mark.asyncio
async def test_failed_repository_limit_flush_and_report(
    memory_db: DatabaseManager,
    tmp_path: Path,
) -> None:
    del memory_db
    await ensure_queue_tables()
    repo = FailedJobRepository({"connection": "sqlite", "table": "failed_jobs"})
    await repo.store(
        uuid="u1",
        connection="database",
        queue="default",
        payload={"class": "x", "data": {}},
        exception=RuntimeError("boom"),
    )
    rows = await repo.all(limit=1)
    assert len(rows) == 1
    assert await repo.flush() >= 1

    app = Application(tmp_path)
    reported: list[str] = []

    class TrackingHandler:
        def report(self, exc: BaseException) -> None:
            reported.append(str(exc))

    app.container.instance(type("HandlerMarker", (), {}), TrackingHandler())  # noqa: SLF001

    from almasix.exceptions.handler import Handler

    app.container.singleton(Handler, lambda _c: TrackingHandler())
    await report_failure(app, RuntimeError("reported"), _CounterJob())
    assert reported == ["reported"]

    def broken_report(_exc: BaseException) -> None:
        raise RuntimeError("handler broken")

    app.container.singleton(Handler, lambda _c: SimpleNamespace(report=broken_report))
    await report_failure(app, RuntimeError("ignored"), _CounterJob())


@pytest.mark.asyncio
async def test_database_queue_pop_race_and_restore(
    memory_db: DatabaseManager,
) -> None:
    del memory_db
    await ensure_queue_tables()
    config = {
        "default": "database",
        "connections": {
            "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        },
        "failed": {"driver": "database", "connection": "sqlite", "table": "failed_jobs"},
    }
    manager = QueueManager(config=config)
    connection = manager.connection("database")

    with patch("almasix.orm.facade.DB") as db:
        db.select_one = AsyncMock(
            return_value={"id": 1, "queue": "default", "payload": "{}", "attempts": 0}
        )
        db.statement = AsyncMock(return_value=0)
        assert await connection.pop() is None

    assert await connection.restore_failed(99999) is False

    repo = FailedJobRepository(manager.failed_config())
    await repo.store(
        uuid="restore-me",
        connection="database",
        queue="default",
        payload=_CounterJob().serialize(),
        exception=RuntimeError("x"),
    )
    rows = await repo.all()
    assert await connection.restore_all_failed() == len(rows)
    assert await repo.all() == []


@pytest.mark.asyncio
async def test_job_edges_and_dispatcher_explicit_connection(
    memory_db: DatabaseManager,
) -> None:
    del memory_db
    await ensure_queue_tables()

    with pytest.raises(NotImplementedError):
        Job().handle()

    with pytest.raises(ValueError, match="missing class"):
        Job.deserialize({})

    assert repr(Job()) == "Job()"
    assert _CounterJob().queue_name() == "default"

    with pytest.raises(ValueError, match="Invalid job class"):
        _import_job_class("not-a-module")

    with pytest.raises(TypeError, match="not a Job subclass"):
        _import_job_class(f"{__name__}.NotAJob")

    config = {
        "default": "sync",
        "connections": {
            "sync": {"driver": "sync"},
            "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        },
    }
    manager = QueueManager(config=config)
    set_manager(manager)
    set_dispatcher(Dispatcher(manager))

    _ExplicitConnJob.ran = False
    await _ExplicitConnJob().dispatch_sync()
    assert _ExplicitConnJob.ran is True
    _ExplicitConnJob.ran = False
    await dispatch(_ExplicitConnJob())
    worker = Worker(manager)
    await worker.run_once("database")
    assert _ExplicitConnJob.ran is True


# ---------------------------------------------------------------------------
# Mail — markdown and mailer dispatch edges
# ---------------------------------------------------------------------------


def test_markdown_h2_and_builtin_theme_fallback(tmp_path: Path) -> None:
    from almasix.prism.engine import Engine
    from almasix.prism.helpers import set_engine

    html_out = render_markdown_component("## Subtitle\n\nPlain")
    assert "<h2>" in html_out

    views = tmp_path / "views"
    views.mkdir()
    (views / "note.prism.html").write_text("# Hello\n\nWorld", encoding="utf-8")
    set_engine(Engine(paths=[views], cache_enabled=False))

    body, text = render_content(
        Content(markdown="note", with_data={"app_name": "Acme", "subject": "Hi"})
    )
    assert body is not None
    assert "Acme" in body
    assert text is not None


def test_markdown_view_and_text_alt_path(tmp_path: Path) -> None:
    from almasix.prism.engine import Engine
    from almasix.prism.helpers import set_engine

    views = tmp_path / "views"
    mail_dir = views / "mail"
    mail_dir.mkdir(parents=True)
    (mail_dir / "welcome.prism.html").write_text("# Title\n\nBody", encoding="utf-8")
    (mail_dir / "welcome.text").write_text("Plain text body", encoding="utf-8")
    set_engine(Engine(paths=[views], cache_enabled=False))

    body, text = render_content(Content(markdown="mail.welcome", with_data={"app_name": "X"}))
    assert body is not None
    assert "<h1>" in body
    assert text == "Plain text body"


def test_app_name_fallback_when_config_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.prism.engine import Engine
    from almasix.prism.helpers import set_engine

    views = tmp_path / "views"
    views.mkdir()
    (views / "note.prism.html").write_text("Hello", encoding="utf-8")
    set_engine(Engine(paths=[views], cache_enabled=False))

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("no config")

    monkeypatch.setattr("almasix.config.config", boom)
    body, _ = render_content(Content(markdown="note", with_data={}))
    assert body is not None
    assert "Almasix" in body


def test_dispatch_to_queue_import_and_exception_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "log"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()

    class TinyMail(Mailable):
        def envelope(self) -> Envelope:
            return Envelope(subject="Q")

        def content(self) -> Content:
            return Content(text="body")

    message = SentMessage(mailable=TinyMail(), to=[], subject="Q", text="body")
    mailer = Mail.manager().mailer("log")

    real_import = builtins.__import__

    def blocked_queue_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "almasix.queue.helpers":
            raise ImportError("queue unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_queue_import)
    assert _dispatch_to_queue(mailer, message) is False

    monkeypatch.undo()

    def boom_dispatch(_job: Job) -> Any:
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr("almasix.queue.helpers.dispatch", boom_dispatch)
    assert _dispatch_to_queue(mailer, message) is False


# ---------------------------------------------------------------------------
# Notifications — base classes, sender, provider, verification, database
# ---------------------------------------------------------------------------


def test_notification_base_class_branches() -> None:
    note = Notification()
    assert note.via(object()) == ["mail"]
    with pytest.raises(NotImplementedError):
        note.to_mail(object())
    assert note.to_database(object()) == {"message": str(note)}

    class BrokenDb(Notification):
        def to_database(self, notifiable: Any) -> dict[str, Any]:
            del notifiable
            raise ValueError("broken")

    assert BrokenDb().to_array(object()) == {"notification": "BrokenDb"}

    class FlagQueued(Notification):
        queue = True

    class NamedQueued(Notification):
        queue = "emails"

    assert FlagQueued().should_queue() is True
    assert NamedQueued().should_queue() is True
    assert NamedQueued().queue_name() == "emails"
    assert Notification().queue_name() == "default"


class _RouteUser(Notifiable):
    email = "route@example.com"
    id = 7
    _registry: ClassVar[dict[int, _RouteUser]] = {}

    def __init__(self, user_id: int = 7, email: str = "route@example.com") -> None:
        self.id = user_id
        self.email = email
        type(self)._registry[user_id] = self

    def get_key(self) -> int:
        return self.id

    def route_notification_for_sms(self) -> str:
        return "+15551212"

    @classmethod
    def find(cls, key: Any) -> _RouteUser | None:
        return cls._registry.get(int(key))


class QueuedNote(ShouldQueue, Notification):
    queue = "notifications"

    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["array"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"queued": True, "email": getattr(notifiable, "email", None)}


@pytest.mark.asyncio
async def test_notifiable_routes_and_store_helpers(memory_db: DatabaseManager) -> None:
    del memory_db
    await ensure_notification_tables()
    user = _RouteUser()
    assert user.route_notification_for("sms") == "+15551212"
    assert user.route_notification_for("mail") == "route@example.com"
    assert user.route_notification_for("database") is user
    assert user.route_notification_for("nope") is None
    assert user.route_notification_for_mail() == "route@example.com"

    ArrayChannel.clear()
    await user.notify_now(NotificationSubclass())
    assert ArrayChannel.messages

    await user.notify(NotificationSubclass())
    all_notes = await user.notifications()
    assert all_notes
    unread = await user.unread_notifications()
    assert unread
    assert await user.mark_notification_as_read(unread[0]["id"])


class NotificationSubclass(Notification):
    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["array", "database"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"email": getattr(notifiable, "email", None)}


@pytest.mark.asyncio
async def test_notification_sender_database_queue_path(
    memory_db: DatabaseManager,
) -> None:
    del memory_db
    await ensure_queue_tables()
    config = {
        "default": "database",
        "connections": {
            "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        },
    }
    manager = QueueManager(config=config)
    set_manager(manager)
    set_dispatcher(Dispatcher(manager))

    ArrayChannel.clear()
    user = _RouteUser()
    await NotificationSender().send(user, QueuedNote())
    connection = manager.connection("database")
    assert await connection.size("notifications") == 1
    assert ArrayChannel.messages == []

    worker = Worker(manager)
    await worker.run_once("database", queue="notifications")
    assert ArrayChannel.messages
    assert ArrayChannel.messages[-1]["payload"]["queued"] is True


@pytest.mark.asyncio
async def test_notification_sender_import_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def blocked_queue_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "almasix.queue":
            raise ImportError("no queue")
        return real_import(name, globals, locals, fromlist, level)

    ArrayChannel.clear()
    monkeypatch.setattr(builtins, "__import__", blocked_queue_import)

    class QueuedNote(ShouldQueue, Notification):
        def via(self, notifiable: Any) -> list[str]:
            del notifiable
            return ["array"]

        def to_array(self, notifiable: Any) -> dict[str, Any]:
            return {"fallback": True}

    await NotificationSender().send(_RouteUser(), QueuedNote())
    assert ArrayChannel.messages


@pytest.mark.asyncio
async def test_notification_sender_typeerror_fallback(
    memory_db: DatabaseManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del memory_db
    await ensure_queue_tables()

    class QueuedNote(ShouldQueue, Notification):
        def via(self, notifiable: Any) -> list[str]:
            del notifiable
            return ["array"]

        def to_array(self, notifiable: Any) -> dict[str, Any]:
            return {"fallback": True}

    config = {
        "default": "database",
        "connections": {
            "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        },
    }
    manager = QueueManager(config=config)
    set_manager(manager)
    set_dispatcher(Dispatcher(manager))

    async def type_error_dispatch(_job: Job) -> Any:
        raise TypeError("cannot serialize")

    monkeypatch.setattr("almasix.queue.helpers.dispatch", type_error_dispatch)
    ArrayChannel.clear()
    await NotificationSender().send(_RouteUser(), QueuedNote())
    assert ArrayChannel.messages


class PlainVerifyUser(MustVerifyEmail):
    def __init__(self) -> None:
        self.email = "plain@example.com"
        self.id = 3
        self.email_verified_at = None

    def route_notification_for(self, channel: str, notification: Any | None = None) -> Any:
        del notification
        if channel == "mail":
            return self.email
        return None


@pytest.mark.asyncio
async def test_verification_without_setters_or_notify(
    memory_db: DatabaseManager,
    tmp_path: Path,
) -> None:
    del memory_db
    user = PlainVerifyUser()
    assert await user.mark_email_as_verified() is True
    assert user.email_verified_at is not None

    app = Application(base_path=tmp_path)
    app.config.set("mail", {**default_mail_config(), "default": "array"})
    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    await user.send_email_verification_notification()
    transport = Mail.manager().array_transport()
    assert transport is not None
    assert transport.sent_messages


def test_notifiable_id_without_get_key() -> None:
    assert _notifiable_id(SimpleNamespace(id=99)) == "99"


@pytest.mark.asyncio
async def test_database_notification_bad_json(memory_db: DatabaseManager) -> None:
    del memory_db
    await ensure_notification_tables()
    from almasix.orm import DB

    user = _RouteUser()
    row_id = "00000000-0000-0000-0000-000000000099"
    await DB.table("notifications").insert(
        {
            "id": row_id,
            "type": "Test",
            "notifiable_type": f"{type(user).__module__}.{type(user).__qualname__}",
            "notifiable_id": str(user.get_key()),
            "data": "{not-json",
            "read_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )
    rows = await DatabaseNotificationStore().for_notifiable(user)
    assert rows[0]["data"] == "{not-json"


@pytest.mark.asyncio
async def test_mail_channel_invalid_payload() -> None:
    class BadMail(Notification):
        def via(self, notifiable: Any) -> list[str]:
            del notifiable
            return ["mail"]

        def to_mail(self, notifiable: Any) -> str:
            del notifiable
            return "nope"

    with pytest.raises(TypeError, match="Mailable or dict"):
        await MailChannel().send(_RouteUser(), BadMail())


def test_reset_password_to_array() -> None:
    user = _RouteUser()
    note = ResetPasswordNotification("secret-token", reset_url="/custom")
    payload = note.to_array(user)
    assert payload["token"] == "secret-token"
    assert payload["reset_url"] == "/custom"


@pytest.mark.asyncio
async def test_notification_provider_register_and_password_fallback(
    tmp_path: Path,
) -> None:
    app = Application(base_path=tmp_path)
    app.config.set("notifications", {})
    app.config.set("mail", {**default_mail_config(), "default": "array"})
    NotificationServiceProvider(app).register()
    assert app.config.get("notifications") is not None

    MailServiceProvider(app).register()
    MailServiceProvider(app).boot()
    NotificationServiceProvider(app).boot()

    from almasix.auth.passwords import PasswordBroker, get_password_manager

    class Provider:
        async def retrieve_by_credentials(self, credentials: dict[str, Any]) -> PlainVerifyUser | None:
            return PlainVerifyUser()

    class Tokens:
        async def recently_created(self, email: str) -> bool:
            del email
            return False

        async def create(self, email: str) -> str:
            del email
            return "tok"

    manager = get_password_manager()
    broker = PasswordBroker(Provider(), Tokens(), send_callback=manager._send_callback)  # noqa: SLF001
    status = await broker.send_reset_link({"email": "plain@example.com"})
    assert "sent" in status
