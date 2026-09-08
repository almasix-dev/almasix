"""CI coverage fill — close M9–M14 gaps that drag full-suite fail_under below 98%."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

from almasix.console.commands.queue_failed import QueueFailedCommand, QueueRetryCommand
from almasix.console.commands.queue_work import QueueListenCommand, QueueWorkCommand
from almasix.console.commands.storage_link import StorageLinkCommand
from almasix.console.display import describe, serialize, to_json
from almasix.console.repl import resolve_awaitable
from almasix.debug import dump, render_dd_html, render_dump_html, serialize as debug_serialize
from almasix.framework.application import Application
from almasix.notifications.jobs import (
    SendQueuedNotification,
    resolve_notifiable,
    resolve_notification,
)
from almasix.notifications.verification import (
    MustVerifyEmail,
    hash_email,
    mark_verified_from_request,
    sign_verification,
    verify_signature,
)
from almasix.queue import Job, ShouldQueue, ensure_tables
from almasix.queue.helpers import default_queue_config, set_dispatcher, set_manager
from almasix.queue.dispatcher import Dispatcher
from almasix.queue.manager import QueueManager
from almasix.support import collect
from tests.orm_support import memory_db


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


class _VerifyUser(MustVerifyEmail):
    def __init__(self, *, user_id: int = 1, email: str = "ada@example.com", verified: bool = False) -> None:
        self.id = user_id
        self.email = email
        self.email_verified_at = "yes" if verified else None
        self.saved = False

    def get_key(self) -> int:
        return self.id

    def get_attribute(self, key: str) -> Any:
        return getattr(self, key, None)

    def set_attribute(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    async def save(self) -> None:
        self.saved = True

    @classmethod
    async def find(cls, key: Any) -> _VerifyUser | None:
        if str(key) == "1":
            return cls(user_id=1, email="ada@example.com")
        if str(key) == "2":
            return cls(user_id=2, email="other@example.com")
        return None


@pytest.mark.asyncio
async def test_verification_signature_and_mark_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.notifications import verification as ver

    monkeypatch.setattr(ver, "_default_user_model", lambda: None)
    monkeypatch.setenv("APP_KEY", "test-secret-key")
    user = _VerifyUser()
    assert user.has_verified_email() is False
    await user.mark_email_as_verified()
    assert user.has_verified_email() is True
    assert user.saved is True

    plain = SimpleNamespace(email_verified_at=None)
    assert MustVerifyEmail.has_verified_email(plain) is False
    await MustVerifyEmail.mark_email_as_verified(plain)
    assert plain.email_verified_at is not None

    expires = int(time.time()) + 3600
    email_hash = hash_email("ada@example.com")
    sig = sign_verification("1", email_hash, expires)
    assert verify_signature("1", email_hash, expires, sig) is True
    assert verify_signature("1", email_hash, "not-int", sig) is False
    assert verify_signature("1", email_hash, int(time.time()) - 10, sig) is False
    assert verify_signature("1", email_hash, expires, "bad") is False

    url = user.verification_url(base_url="http://localhost", expires=30)
    assert "signature=" in url and "expires=" in url

    ok = await mark_verified_from_request(
        user_id="1",
        email_hash=email_hash,
        expires=expires,
        signature=sig,
        user_model=_VerifyUser,
    )
    assert ok is not None
    assert ok.has_verified_email()

    assert (
        await mark_verified_from_request(
            user_id="1",
            email_hash=email_hash,
            expires=expires,
            signature="nope",
            user_model=_VerifyUser,
        )
        is None
    )
    assert (
        await mark_verified_from_request(
            user_id="9",
            email_hash=email_hash,
            expires=expires,
            signature=sig,
            user_model=_VerifyUser,
        )
        is None
    )
    assert (
        await mark_verified_from_request(
            user_id="2",
            email_hash=email_hash,
            expires=expires,
            signature=sign_verification("2", email_hash, expires),
            user_model=_VerifyUser,
        )
        is None
    )

    already = _VerifyUser(verified=True)

    @classmethod
    def _find_already(cls, key: Any) -> _VerifyUser:
        del key
        return already

    monkeypatch.setattr(_VerifyUser, "find", _find_already)
    again = await mark_verified_from_request(
        user_id="1",
        email_hash=hash_email("ada@example.com"),
        expires=expires,
        signature=sign_verification("1", hash_email("ada@example.com"), expires),
        user_model=_VerifyUser,
    )
    assert again is already

    assert (
        await mark_verified_from_request(
            user_id="1",
            email_hash=email_hash,
            expires=expires,
            signature=sig,
            user_model=None,
        )
        is None
    )

    class NoFind:
        pass

    assert (
        await mark_verified_from_request(
            user_id="1",
            email_hash=email_hash,
            expires=expires,
            signature=sig,
            user_model=NoFind,
        )
        is None
    )


def test_verification_app_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    from almasix.notifications import verification as ver

    monkeypatch.setattr(
        "almasix.config.config",
        lambda key, default=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert ver._app_url() == ""
    assert ver._app_key_bytes() == b"almasix-dev-key"

    monkeypatch.setattr(
        "almasix.config.config",
        lambda key, default=None: "base64:abc" if key == "app.key" else "http://x",
    )
    assert ver._app_url() == "http://x"
    assert ver._app_key_bytes() == b"abc"


# ---------------------------------------------------------------------------
# Queue failed / retry / work commands
# ---------------------------------------------------------------------------


class _BoomJob(ShouldQueue, Job):
    tries: ClassVar[int] = 1

    def handle(self) -> None:
        raise RuntimeError("fail-me")


@pytest.mark.asyncio
async def test_queue_failed_and_retry_commands(memory_db: Any) -> None:
    del memory_db
    await ensure_tables()
    config = default_queue_config("sqlite")
    config["default"] = "database"
    config["connections"] = {
        "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
        "sync": {"driver": "sync"},
    }
    manager = QueueManager(config=config)
    set_manager(manager)
    set_dispatcher(Dispatcher(manager))

    app = Application()
    app.container.instance(QueueManager, manager)

    from almasix.queue.failed import FailedJobRepository

    repo = FailedJobRepository(manager.failed_config())
    assert await repo.all(limit=10) == []

    connection = manager.connection("database")
    await connection.push(_BoomJob())
    from almasix.queue.worker import Worker

    worker = Worker(manager)
    await worker.run_once("database")
    assert await repo.all(limit=10)

    import concurrent.futures

    def _run_failed() -> int:
        return QueueFailedCommand(app).handle()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(_run_failed).result() == 0

        def _retry_all() -> int:
            cmd = QueueRetryCommand(app)
            cmd._options = {"all": True}  # noqa: SLF001
            return cmd.handle()

        assert pool.submit(_retry_all).result() == 0

        def _retry_missing() -> int:
            cmd = QueueRetryCommand(app)
            cmd._options = {"all": False}  # noqa: SLF001
            cmd._arguments = {}  # noqa: SLF001
            return cmd.handle()

        assert pool.submit(_retry_missing).result() == 1

        def _retry_missing_id() -> int:
            cmd = QueueRetryCommand(app)
            cmd._options = {"all": False}  # noqa: SLF001
            cmd._arguments = {"id": 99999}  # noqa: SLF001
            return cmd.handle()

        assert pool.submit(_retry_missing_id).result() == 1

        def _retry_sync_only() -> int:
            app2 = Application()
            sync_only = QueueManager(
                config={
                    "default": "sync",
                    "connections": {"sync": {"driver": "sync"}},
                    "failed": config["failed"],
                }
            )
            app2.container.instance(QueueManager, sync_only)
            bad = QueueRetryCommand(app2)
            bad._options = {"all": True}  # noqa: SLF001
            return bad.handle()

        assert pool.submit(_retry_sync_only).result() == 1


def test_queue_work_once_and_listen_interrupt(memory_db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    del memory_db
    asyncio.run(ensure_tables())
    config = default_queue_config("sqlite")
    config["default"] = "database"
    config["connections"] = {
        "database": {"driver": "database", "connection": "sqlite", "table": "jobs"},
    }
    manager = QueueManager(config=config)
    set_manager(manager)
    set_dispatcher(Dispatcher(manager))
    app = Application()
    app.container.instance(QueueManager, manager)

    work = QueueWorkCommand(app)
    work._options = {"once": True, "queue": "default", "connection": "database"}  # noqa: SLF001
    assert work.handle() == 0

    def _raise_interrupt(*_a: Any, **_k: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(asyncio, "run", _raise_interrupt)
    listen = QueueListenCommand(app)
    listen._options = {"queue": "default"}  # noqa: SLF001
    assert listen.handle() == 0


def test_storage_link_command(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    app = Application(tmp_path)
    (tmp_path / "storage" / "app" / "public").mkdir(parents=True)
    (tmp_path / "public").mkdir()
    app.config.set(
        "filesystems",
        {
            "links": {
                str(tmp_path / "public" / "storage"): str(tmp_path / "storage" / "app" / "public"),
            }
        },
    )
    cmd = StorageLinkCommand(app)
    assert cmd.handle() == 0
    # second run — already linked / exists path
    assert cmd.handle() == 0


# ---------------------------------------------------------------------------
# Notification jobs + display + debug bits
# ---------------------------------------------------------------------------


class _Note:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)

    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["array"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {"id": getattr(notifiable, "id", None)}


class _NoteBadInit:
    def __init__(self, **kwargs: Any) -> None:
        if kwargs:
            raise TypeError("no kwargs")
        self.required = ""

    def via(self, notifiable: Any) -> list[str]:
        del notifiable
        return ["array"]

    def to_array(self, notifiable: Any) -> dict[str, Any]:
        return {}


class _FinderNotifiable:
    @classmethod
    async def find(cls, key: Any) -> _FinderNotifiable:
        inst = cls()
        inst.id = key  # type: ignore[attr-defined]
        return inst


class _PlainNotifiable:
    pass


@pytest.mark.asyncio
async def test_notification_job_resolve_helpers() -> None:
    from almasix.notifications.channels import ArrayChannel

    ArrayChannel.clear()
    note = resolve_notification(f"{_Note.__module__}.{_Note.__qualname__}", {"x": 1})
    assert note.x == 1
    bad = resolve_notification(f"{_NoteBadInit.__module__}.{_NoteBadInit.__qualname__}", {"x": 1})
    assert getattr(bad, "x", None) == 1

    found = await resolve_notifiable(
        f"{_FinderNotifiable.__module__}.{_FinderNotifiable.__qualname__}", 7
    )
    assert found.id == 7

    plain = await resolve_notifiable(
        f"{_PlainNotifiable.__module__}.{_PlainNotifiable.__qualname__}", 3
    )
    assert plain.id == 3

    with pytest.raises(ValueError):
        resolve_notification("NoModule", {})

    job = SendQueuedNotification(
        notifiable_type=f"{_FinderNotifiable.__module__}.{_FinderNotifiable.__qualname__}",
        notifiable_id=1,
        notification_class=f"{_Note.__module__}.{_Note.__qualname__}",
        channels=["array"],
        queue_name="notifications",
    )
    await job.handle()
    assert ArrayChannel.messages


def test_display_and_debug_helpers() -> None:
    class Modelish:
        _attributes = {"id": 1}

        def get_key(self) -> int:
            return 1

        def to_dict(self) -> dict[str, Any]:
            return {"id": 1}

    class ModelCollection(list):
        def to_dict(self) -> list[dict[str, Any]]:
            return [item.to_dict() for item in self]

        def model_keys(self) -> list[Any]:
            return [item.get_key() for item in self]

    class Page:
        items = [1]

        def to_dict(self) -> dict[str, Any]:
            return {"data": self.items}

    class BrokenToDict:
        def to_dict(self) -> Any:
            raise TypeError("nope")

    model = Modelish()
    coll = ModelCollection([model])
    assert "Modelish" in describe(model)
    assert "Collection" in describe(coll)
    assert describe(Page()).endswith("Page")
    assert "Collection" in describe(collect([1, 2]))
    assert "dict" in describe({"a": 1})
    assert "list" in describe([1, 2])
    assert describe(3) == "int"

    assert serialize(model) == {"id": 1}
    assert serialize(coll) == [{"id": 1}]
    assert serialize(Page()) == {"data": [1]}
    assert serialize(collect([1, 2]))
    assert serialize({"a": model})["a"] == {"id": 1}
    assert serialize({model})  # set
    assert serialize(BrokenToDict()) is not None
    assert to_json(model).startswith("{")

    assert debug_serialize({"x": 1}) == {"x": 1}
    dump({"hello": "world"})
    html = render_dd_html([{"a": 1}])
    assert "Dump and die" in html or "dump" in html.lower()
    assert "a" in render_dump_html([{"a": 1}])


def test_resolve_awaitable_variants() -> None:
    assert resolve_awaitable(5) == 5

    async def _coro() -> str:
        return "ok"

    assert resolve_awaitable(_coro()) == "ok"

    class Awaitable:
        def __await__(self):
            async def _inner() -> int:
                return 9

            return _inner().__await__()

    assert resolve_awaitable(Awaitable()) == 9
