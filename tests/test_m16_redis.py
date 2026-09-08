"""M16 Redis — façade, cache/session/queue drivers (FakeRedis, no server)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from avalon.cache.drivers.redis import RedisStore
from avalon.cache.manager import CacheManager
from avalon.cache.store import Repository
from avalon.installer.scaffold import scaffold_app
from avalon.queue.connections.redis import RedisQueue
from avalon.queue.job import Job
from avalon.queue.manager import QueueManager
from avalon.queue.worker import Worker
from avalon.redis.facade import Redis
from avalon.redis.helpers import default_redis_config, redis, set_manager
from avalon.redis.manager import RedisManager, require_redis
from avalon.session.handlers import CookieSessionHandler, RedisSessionHandler, resolve_session_handler
from tests.support_redis import FakeRedis


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def redis_manager(fake_redis: FakeRedis) -> RedisManager:
    manager = RedisManager(
        None,
        {
            "default": "default",
            "connections": {"default": {"host": "127.0.0.1"}},
        },
    )
    manager.set_client("default", fake_redis)
    set_manager(manager)
    Redis.set_manager(manager)
    yield manager
    set_manager(None)
    Redis.set_manager(None)


def test_require_redis_imports() -> None:
    try:
        mod = require_redis()
    except RuntimeError as exc:
        assert "avalon[redis]" in str(exc)
        return
    assert hasattr(mod, "Redis")


def test_require_redis_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _import(name: str, *args: Any, **kwargs: Any):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("no redis")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    with pytest.raises(RuntimeError, match="avalon\\[redis\\]"):
        require_redis()


def test_redis_facade_get_set_delete_incr_publish(redis_manager: RedisManager, fake_redis: FakeRedis) -> None:
    del redis_manager
    assert Redis.set("greeting", b"hello", ex=60) is True
    assert Redis.get("greeting") == b"hello"
    assert Redis.incr("counter") == 1
    assert Redis.incr("counter", 4) == 5
    assert Redis.delete("greeting") == 1
    assert Redis.publish("chan", b"ping") == 1
    assert fake_redis._channels["chan"] == [b"ping"]
    pubsub = Redis.subscribe("chan")
    assert "chan" in pubsub.channels
    assert redis() is fake_redis


def test_redis_manager_missing_connection() -> None:
    manager = RedisManager(None, {"default": "default", "connections": {}})
    with pytest.raises(KeyError):
        manager.connection("missing")


def test_redis_manager_from_url(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class DummyAsync:
        @staticmethod
        def from_url(url: str, **kwargs):
            created["url"] = url
            created["kwargs"] = kwargs
            return FakeRedis()

        class Redis:  # noqa: N801
            def __init__(self, **kwargs):
                created["redis_kwargs"] = kwargs

    monkeypatch.setattr("avalon.redis.manager.require_redis", lambda: DummyAsync)
    manager = RedisManager(
        None,
        {"default": "default", "connections": {"default": {"url": "redis://example/0"}}},
    )
    client = manager.connection()
    assert isinstance(client, FakeRedis)
    assert created["url"] == "redis://example/0"


def test_redis_cache_store_crud_tags_locks(redis_manager: RedisManager, fake_redis: FakeRedis) -> None:
    del redis_manager
    store = RedisStore(client=fake_redis)
    assert store.put("a", {"n": 1}, 60)
    assert store.get("a") == {"n": 1}
    assert store.add("a", {"n": 2}, 60) is False
    assert store.add("b", 1, 60) is True
    assert store.increment("b") == 2
    assert store.decrement("b") == 1
    assert store.forever("c", "x")
    assert store.forget("c") is True
    tagged = Repository(store, prefix="").tags("users")
    tagged.put("ada", {"id": 1}, 30)
    assert tagged.get("ada") == {"id": 1}
    tagged.flush()
    assert tagged.get("ada") is None

    lock = store.lock("deploy", seconds=10)
    assert lock.get() is True
    assert store.lock("deploy", seconds=10).get() is False
    lock.release()
    with store.lock("deploy2", seconds=5):
        pass
    owner = store.lock("owned", seconds=5)
    assert owner.get() is True
    restored = store.restore_lock("owned", owner.owner_token())
    assert restored.release() is True
    assert store.flush_locks() is True
    assert store.flush() is True


def test_cache_manager_resolves_redis_driver(fake_redis: FakeRedis) -> None:
    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)
    cache = CacheManager(
        None,
        {
            "default": "redis",
            "prefix": "t_",
            "stores": {"redis": {"driver": "redis", "connection": "default"}},
        },
    )
    repo = cache.store("redis")
    assert repo.put("k", "v", 10)
    assert repo.get("k") == "v"
    set_manager(None)


@pytest.mark.asyncio
async def test_cookie_and_redis_session_handlers(fake_redis: FakeRedis) -> None:
    cookie = CookieSessionHandler()

    class Req:
        def cookie(self, name: str) -> str | None:
            return self._cookies.get(name)

        def __init__(self) -> None:
            self._cookies: dict[str, str] = {}

    class Resp:
        def __init__(self) -> None:
            self.cookies: dict[str, str] = {}

        def set_cookie(self, name: str, value: str, **kwargs) -> None:
            del kwargs
            self.cookies[name] = value

    req = Req()
    sid, data = await cookie.read(req, key="secret", cookie_name="s", lifetime=120)
    assert sid is None and data is None
    resp = Resp()
    await cookie.write(
        resp,
        session_id=None,
        data={"x": 1},
        key="secret",
        cookie_name="s",
        lifetime=120,
        path="/",
        secure=False,
        dirty=True,
        had_prior=False,
    )
    assert "s" in resp.cookies

    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)
    handler = RedisSessionHandler(connection="default")
    req2 = Req()
    resp2 = Resp()
    new_id = await handler.write(
        resp2,
        session_id=None,
        data={"locale": "en"},
        key="secret",
        cookie_name="s",
        lifetime=120,
        path="/",
        secure=False,
        dirty=True,
        had_prior=False,
    )
    assert new_id
    req2._cookies["s"] = resp2.cookies["s"]
    sid2, data2 = await handler.read(req2, key="secret", cookie_name="s", lifetime=3600)
    assert sid2 == new_id
    assert data2 == {"locale": "en"}
    await handler.destroy(new_id)
    set_manager(None)


class DemoJob(Job):
    tries = 1

    async def handle(self) -> str:
        return "ok"


class SlowJob(Job):
    delay = 5

    async def handle(self) -> None:
        return None


@pytest.mark.asyncio
async def test_redis_queue_and_worker(fake_redis: FakeRedis) -> None:
    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)

    queue_manager = QueueManager(
        None,
        {
            "default": "redis",
            "connections": {"redis": {"driver": "redis", "connection": "default", "queue": "queues"}},
            "failed": {"driver": "database", "table": "failed_jobs"},
        },
    )
    connection = RedisQueue(None, {"connection": "default", "queue": "queues"}, manager=queue_manager, client=fake_redis)
    queue_manager._connections["redis"] = connection

    job = DemoJob()
    assert await connection.push(job) is True
    assert await connection.size("default") == 1
    worker = Worker(queue_manager)
    assert await worker.run_once("redis", queue="default") is True
    assert await connection.size("default") == 0
    set_manager(None)


@pytest.mark.asyncio
async def test_redis_queue_release_and_delay(fake_redis: FakeRedis) -> None:
    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)
    connection = RedisQueue(None, {"connection": "default", "queue": "q"}, client=fake_redis)

    await connection.push(SlowJob())
    assert await connection.pop("default") is None  # still delayed
    # Force promote by zeroing score
    delayed_key = connection._delayed_key("default")
    members = await fake_redis.zrangebyscore(delayed_key, 0, 10**12)
    assert members
    await fake_redis.zrem(delayed_key, members[0])
    await fake_redis.zadd(delayed_key, {members[0]: 0})
    record = await connection.pop("default")
    assert record is not None
    await connection.release(record["id"], delay=0)
    assert await connection.size("default") == 1
    set_manager(None)


def test_scaffold_ships_redis_config(tmp_path: Path) -> None:
    root = scaffold_app("redis_app", destination=tmp_path / "redis_app")
    assert (root / "config" / "redis.py").is_file()
    env = (root / ".env").read_text(encoding="utf-8")
    assert "REDIS_HOST=" in env
    cache = (root / "config" / "cache.py").read_text(encoding="utf-8")
    assert '"redis"' in cache
    queue = (root / "config" / "queue.py").read_text(encoding="utf-8")
    assert '"redis"' in queue
    session = (root / "config" / "session.py").read_text(encoding="utf-8")
    assert "connection" in session


def test_default_redis_config_shape() -> None:
    cfg = default_redis_config()
    assert cfg["default"] == "default"
    assert "host" in cfg["connections"]["default"]


def test_resolve_session_handler_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("avalon.config.config", lambda key, default=None: {
        "session.driver": "cookie",
    }.get(key, default))
    assert isinstance(resolve_session_handler(), CookieSessionHandler)


def test_resolve_session_handler_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "avalon.config.config",
        lambda key, default=None: {
            "session.driver": "redis",
            "session.connection": "default",
            "session.prefix": "sess:",
        }.get(key, default),
    )
    handler = resolve_session_handler()
    assert isinstance(handler, RedisSessionHandler)


def test_resolve_session_handler_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("avalon.config.config", lambda key, default=None: "bogus" if key == "session.driver" else default)
    with pytest.raises(ValueError):
        resolve_session_handler()


def test_redis_manager_host_password_and_forget(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, Any] = {}

    class DummyAsync:
        @staticmethod
        def from_url(url: str, **kwargs):  # pragma: no cover
            raise AssertionError("url path not expected")

        class Redis:  # noqa: N801
            def __init__(self, **kwargs):
                created.update(kwargs)

    monkeypatch.setattr("avalon.redis.manager.require_redis", lambda: DummyAsync)
    manager = RedisManager(
        None,
        {
            "default": "default",
            "connections": {
                "default": {
                    "host": "redis.local",
                    "port": 6380,
                    "database": 2,
                    "password": "secret",
                    "username": "avalon",
                }
            },
        },
    )
    manager.set_default_connection("default")
    client = manager.connection()
    assert created["host"] == "redis.local"
    assert created["password"] == "secret"
    assert created["username"] == "avalon"
    assert created["db"] == 2
    manager.forget_clients()
    assert manager._clients == {}


def test_redis_facade_errors_and_empty_delete(redis_manager: RedisManager) -> None:
    del redis_manager
    assert Redis.delete() == 0
    set_manager(None)
    Redis.set_manager(None)
    with pytest.raises(RuntimeError):
        Redis.manager()
    with pytest.raises(RuntimeError):
        from avalon.redis.helpers import get_manager

        get_manager()


def test_redis_provider_register_boot(tmp_path: Path) -> None:
    from avalon.framework.application import Application
    from avalon.redis.provider import RedisServiceProvider

    app = Application(tmp_path)
    app.config.set(
        "redis",
        {
            "default": "default",
            "connections": {"default": {"host": "127.0.0.1", "port": 6379, "database": 0}},
        },
    )
    provider = RedisServiceProvider(app)
    provider.register()
    assert app.container.bound(RedisManager)
    provider.boot()
    assert Redis.manager() is app.make(RedisManager)
    set_manager(None)
    Redis.set_manager(None)


def test_redis_provider_default_config(tmp_path: Path) -> None:
    from avalon.framework.application import Application
    from avalon.redis.provider import RedisServiceProvider

    app = Application(tmp_path)
    provider = RedisServiceProvider(app)
    provider.register()
    manager = app.make(RedisManager)
    assert "default" in manager.config["connections"]
    set_manager(None)


def test_redis_store_corrupt_value_and_lock_block(fake_redis: FakeRedis) -> None:
    from avalon.cache.locks import LockTimeoutError

    store = RedisStore(client=fake_redis)
    # corrupt pickle
    import asyncio

    asyncio.run(fake_redis.set("bad", b"not-pickle"))
    assert store.get("bad") is None

    lock = store.lock("once", seconds=5)
    assert lock.get() is True
    with pytest.raises(LockTimeoutError):
        store.lock("once", seconds=5).block(0)
    lock.force_release()

    # wrong owner release
    a = store.lock("own", seconds=5)
    assert a.get() is True
    b = store.restore_lock("own", "not-the-owner")
    assert b.release() is False
    a.force_release()

    # increment non-int
    store.put("s", "x", None)
    assert store.increment("s") is False


def test_redis_store_uses_manager_client(redis_manager: RedisManager, fake_redis: FakeRedis) -> None:
    del redis_manager
    store = RedisStore(connection="default")
    assert store.put("via-manager", 1, 10)
    assert store.get("via-manager") == 1


@pytest.mark.asyncio
async def test_redis_session_edge_cases(fake_redis: FakeRedis) -> None:
    from avalon.session.signing import sign_payload

    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)
    handler = RedisSessionHandler(connection="default")

    class Req:
        def __init__(self, raw: str | None = None) -> None:
            self._raw = raw

        def cookie(self, name: str) -> str | None:
            del name
            return self._raw

    class Resp:
        def set_cookie(self, *a, **k) -> None:
            del a, k

    # invalid cookie
    sid, data = await handler.read(Req("nope"), key="k", cookie_name="s", lifetime=60)
    assert sid is None and data is None
    # missing id in payload
    bad = sign_payload({}, key="k", max_age=60)
    sid, data = await handler.read(Req(bad), key="k", cookie_name="s", lifetime=3600)
    assert sid is None
    # empty write short-circuit
    assert await handler.write(
        Resp(),
        session_id=None,
        data={},
        key="k",
        cookie_name="s",
        lifetime=60,
        path="/",
        secure=False,
        dirty=False,
        had_prior=False,
    ) is None
    await CookieSessionHandler().destroy(None)
    set_manager(None)


@pytest.mark.asyncio
async def test_redis_queue_via_manager_and_unique(fake_redis: FakeRedis) -> None:
    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)

    class UniqueJob(DemoJob):
        unique_id_value = "u1"

        def unique_id(self) -> str:
            return self.unique_id_value

    queue = RedisQueue(None, {"connection": "default", "queue": "queues"}, client=None)
    # uses manager client
    assert await queue.push(UniqueJob()) is True
    assert queue.new_failed_uuid()
    await queue.delete("missing")
    record = await queue.pop("default")
    assert record is not None
    await queue.release(record["id"], delay=2)
    assert await queue.size("default") == 1
    set_manager(None)


def test_queue_manager_resolves_redis(fake_redis: FakeRedis) -> None:
    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)
    qm = QueueManager(
        None,
        {
            "default": "redis",
            "connections": {"redis": {"driver": "redis", "connection": "default"}},
            "failed": {},
        },
    )
    conn = qm.connection("redis")
    assert isinstance(conn, RedisQueue)
    set_manager(None)


@pytest.mark.asyncio
async def test_redis_store_async_bridge_and_lock_callback(fake_redis: FakeRedis) -> None:
    store = RedisStore(client=fake_redis)
    # exercise _run() while a loop is already running
    assert store.put("async-key", 7, None) is True
    assert store.add("async-key2", 1, None) is True
    assert store.increment("async-key2") == 2
    # TTL refresh path on increment
    store.put("ttl", 1, 30)
    assert store.increment("ttl", 2) == 3
    called = {"n": 0}
    lock = store.lock("cb", seconds=5)
    assert lock.get(lambda: called.__setitem__("n", 1) or "done") == "done"
    assert called["n"] == 1
    # block acquires immediately
    assert store.lock("fresh", seconds=5).block(1) is True
    store.lock("fresh", seconds=5).force_release()
    # release missing lock key
    ghost = store.restore_lock("ghost", "token")
    assert ghost.release() is False
    # multi-page scan for flush_locks
    for i in range(5):
        await fake_redis.set(f"xlock:{i}", b"1")
    assert store.flush_locks() is True


@pytest.mark.asyncio
async def test_redis_facade_subscribe_empty_and_async_bridge(redis_manager: RedisManager) -> None:
    del redis_manager
    pubsub = Redis.subscribe()
    assert pubsub.channels == []
    assert Redis.set("loop", b"1") is True


@pytest.mark.asyncio
async def test_redis_queue_release_missing(fake_redis: FakeRedis) -> None:
    queue = RedisQueue(None, {"connection": "default", "queue": "queues"}, client=fake_redis)
    await queue.release("nope", delay=0)


@pytest.mark.asyncio
async def test_redis_session_corrupt_payload(fake_redis: FakeRedis) -> None:
    from avalon.session.signing import sign_payload

    manager = RedisManager(None, {"default": "default", "connections": {"default": {}}})
    manager.set_client("default", fake_redis)
    set_manager(manager)
    handler = RedisSessionHandler(connection="default")
    sid = "sid-1"
    await fake_redis.set(handler._redis_key(sid), b"{not-json")

    class Req:
        def cookie(self, name: str) -> str | None:
            del name
            return sign_payload({"id": sid}, key="k", max_age=60)

    got_id, data = await handler.read(Req(), key="k", cookie_name="s", lifetime=3600)
    assert got_id == sid and data is None
    await handler.destroy(sid)
    # cookie write no-op when clean empty
    class Resp:
        def set_cookie(self, *a, **k) -> None:
            raise AssertionError("should not set")

    await CookieSessionHandler().write(
        Resp(),
        session_id=None,
        data={},
        key="k",
        cookie_name="s",
        lifetime=60,
        path="/",
        secure=False,
        dirty=False,
        had_prior=False,
    )
    # empty id in signed cookie
    empty = sign_payload({"id": ""}, key="k", max_age=60)

    class ReqEmpty:
        def cookie(self, name: str) -> str | None:
            del name
            return empty

    sid2, data2 = await handler.read(ReqEmpty(), key="k", cookie_name="s", lifetime=3600)
    assert sid2 is None and data2 is None
    # valid id, missing redis payload
    only_id = sign_payload({"id": "orphan"}, key="k", max_age=60)

    class ReqOrphan:
        def cookie(self, name: str) -> str | None:
            del name
            return only_id

    oid, odata = await handler.read(ReqOrphan(), key="k", cookie_name="s", lifetime=3600)
    assert oid == "orphan" and odata is None
    await handler.destroy(None)
    set_manager(None)


def test_lock_block_returns_true_without_callback(fake_redis: FakeRedis) -> None:
    store = RedisStore(client=fake_redis)
    assert store.lock("nb", seconds=5).block(1, None) is True


def test_lock_block_callback_and_enter_fail(fake_redis: FakeRedis) -> None:
    from avalon.cache.locks import LockTimeoutError

    store = RedisStore(client=fake_redis)
    assert store.increment("brand-new") == 1
    held = store.lock("held", seconds=5)
    assert held.get() is True
    with pytest.raises(LockTimeoutError):
        with store.lock("held", seconds=5):
            pass
    result = store.lock("cb2", seconds=5).block(1, lambda: "yes")
    assert result == "yes"
    held.force_release()


def test_provider_boot_when_unbound(tmp_path: Path) -> None:
    from avalon.framework.application import Application
    from avalon.redis.provider import RedisServiceProvider

    app = Application(tmp_path)
    RedisServiceProvider(app).boot()  # no-op when unbound


def test_manager_optional_auth_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []

    class DummyAsync:
        class Redis:  # noqa: N801
            def __init__(self, **kwargs):
                seen.append(kwargs)

    monkeypatch.setattr("avalon.redis.manager.require_redis", lambda: DummyAsync)
    manager = RedisManager(
        None,
        {"default": "default", "connections": {"default": {"host": "h", "port": 1, "database": 0}}},
    )
    manager.connection()
    assert "password" not in seen[0]
    assert "username" not in seen[0]
