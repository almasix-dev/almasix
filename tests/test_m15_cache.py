"""M15 Cache — array / file / database stores, locks, tags, schedule mutex."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from almasix.cache import (
    Cache,
    CacheManager,
    DatabaseLock,
    FileLock,
    LockTimeoutError,
    cache,
    default_cache_config,
    ensure_cache_table,
    set_manager,
)
from almasix.cache.drivers.array import ArrayStore
from almasix.cache.drivers.database import DatabaseStore
from almasix.cache.drivers.file import FileStore
from almasix.cache.provider import CacheServiceProvider
from almasix.console.scheduling import Event, run_event
from almasix.framework.application import Application


@pytest.fixture()
def array_cache() -> CacheManager:
    manager = CacheManager(
        config={
            "default": "array",
            "prefix": "t_",
            "stores": {"array": {"driver": "array"}, "null": {"driver": "null"}},
        }
    )
    set_manager(manager)
    yield manager
    set_manager(None)


def test_array_get_put_remember_pull(array_cache: CacheManager) -> None:
    store = array_cache.store()
    assert store.missing("a")
    assert store.put("a", "almasix", 60)
    assert store.has("a")
    assert store.get("a") == "almasix"
    assert store.add("a", "nope") is False
    assert store.add("b", 1, 30) is True
    assert store.pull("a") == "almasix"
    assert store.missing("a")
    assert store.remember("c", 10, lambda: "computed") == "computed"
    assert store.remember("c", 10, lambda: "other") == "computed"
    assert store.remember_forever("d", lambda: 7) == 7
    assert store.forever("e", "forever")
    assert store.increment("n") == 1
    assert store.increment("n", 2) == 3
    assert store.decrement("n") == 2
    assert store.touch("e", 30) is True
    assert store.touch("missing", 30) is False
    assert Cache.many(["e", "n"]) == {"e": "forever", "n": 2}
    assert Cache.put_many({"m1": 1, "m2": 2}, 10) is True
    assert store.flush() is True
    assert store.missing("e")


def test_cache_facade_and_helper(array_cache: CacheManager) -> None:
    Cache.put("x", 1, 5)
    assert Cache.get("x") == 1
    assert Cache.has("x")
    assert cache("x") == 1
    assert cache({"y": 2}, 10) is True
    assert Cache.get("y") == 2
    assert cache().get("y") == 2
    Cache.forget("x")
    assert Cache.missing("x")
    Cache.forever("z", "ok")
    assert Cache.pull("z") == "ok"
    assert Cache.without_overlapping("wo", lambda: "ran") == "ran"


def test_null_store(array_cache: CacheManager) -> None:
    null = array_cache.store("null")
    assert null.put("a", 1) is True
    assert null.get("a") is None
    assert null.add("a", 1) is True
    assert null.forever("a", 1) is True
    assert null.forget("a") is True
    assert null.flush() is True
    with pytest.raises(RuntimeError, match="tags are not supported"):
        null.tags("x")


def test_file_store(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "cache")
    assert store.put("user:1", {"name": "Ada"}, 60)
    assert store.get("user:1") == {"name": "Ada"}
    assert store.add("user:1", {}) is False
    assert store.add("fresh", 1) is True
    assert store.forever("logo", "x")
    assert store.increment("hits") == 1
    assert store.decrement("hits") == 0
    assert store.forget("logo") is True
    lock = store.lock("file-job", seconds=5)
    assert isinstance(lock, FileLock)
    assert lock.get() is True
    assert store.lock("file-job", seconds=5).get() is False
    assert lock.release() is True
    assert store.flush_locks() is True
    assert store.flush() is True
    assert store.get("user:1") is None
    repo = CacheManager(
        config={
            "default": "file",
            "stores": {"file": {"driver": "file", "path": str(tmp_path / "t")}},
        }
    ).store()
    with pytest.raises(RuntimeError, match="tags are not supported"):
        repo.tags("users")


@pytest.mark.asyncio
async def test_database_store(memory_db) -> None:
    del memory_db
    await ensure_cache_table("sqlite")
    store = DatabaseStore(connection="sqlite")
    assert store.put("k", {"v": 1}, 30)
    assert store.get("k") == {"v": 1}
    assert store.add("k", 2) is False
    assert store.add("fresh", 3) is True
    assert store.forever("f", "yes")
    assert store.increment("n") == 1
    assert store.increment("n", 4) == 5
    lock = store.lock("db-job", seconds=5)
    assert isinstance(lock, DatabaseLock)
    assert lock.get() is True
    assert store.lock("db-job", seconds=5).get() is False
    owner = lock.owner_token()
    restored = store.restore_lock("db-job", owner)
    assert restored.release() is True
    assert lock.get() is True
    assert store.flush_locks() is True
    assert store.forget("f") is True
    assert store.flush() is True
    manager = CacheManager(
        config={
            "default": "database",
            "stores": {"database": {"driver": "database", "connection": "sqlite"}},
        }
    )
    with pytest.raises(RuntimeError, match="tags are not supported"):
        manager.store().tags("x")


def test_locks(array_cache: CacheManager) -> None:
    lock = Cache.lock("job", seconds=5)
    assert lock.get() is True
    assert Cache.lock("job", seconds=5).get() is False
    assert lock.release() is True
    assert Cache.lock("job", seconds=5).block(1) is True
    Cache.lock("job").force_release()

    ran = {"ok": False}

    def work() -> str:
        ran["ok"] = True
        return "done"

    assert Cache.lock("cb", seconds=5).get(work) == "done"
    assert ran["ok"] is True

    with Cache.lock("ctx", seconds=5) as held:
        assert held.owner_token()

    owner = Cache.lock("restore-me", seconds=30)
    assert owner.get() is True
    token = owner.owner_token()
    assert Cache.restore_lock("restore-me", token).release() is True
    assert Cache.flush_locks() is True

    with pytest.raises(LockTimeoutError):
        held = Cache.lock("block-me", seconds=30)
        assert held.get() is True
        Cache.lock("block-me", seconds=30).block(0)


def test_tags(array_cache: CacheManager) -> None:
    Cache.tags("users", "authors").put("ada", {"id": 1}, 60)
    assert Cache.tags("users", "authors").get("ada") == {"id": 1}
    Cache.tags("users", "authors").flush()
    assert Cache.tags("users", "authors").get("ada") is None


def test_ttl_normalization(array_cache: CacheManager) -> None:
    Cache.put("td", 1, timedelta(seconds=2))
    assert Cache.get("td") == 1


def test_extend_custom_driver(array_cache: CacheManager) -> None:
    from almasix.cache.drivers.array import ArrayStore

    array_cache.extend("custom", lambda app, cfg, name: ArrayStore())
    array_cache.config.setdefault("stores", {})["custom"] = {"driver": "custom"}
    assert array_cache.store("custom").put("k", 1)


def test_provider_registers(tmp_path: Path) -> None:
    app = Application(tmp_path)
    app.config.set("cache", default_cache_config(tmp_path))
    CacheServiceProvider(app).register()
    CacheServiceProvider(app).boot()
    manager = app.make(CacheManager)
    assert manager.store().put("p", 1)
    assert Cache.get("p") == 1


def test_schedule_prefers_cache_lock(array_cache: CacheManager, tmp_path: Path) -> None:
    ran = {"n": 0}

    def cb() -> None:
        ran["n"] += 1

    event = Event(description="demo", callback=cb).without_overlapping_lock()
    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 1
    # Hold the lock so a second overlapping run is skipped.
    lock = Cache.lock(f"schedule:{event.mutex_name()}", seconds=30)
    assert lock.get() is True
    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 1
    lock.release()


def test_array_atomic_add_under_threads(array_cache: CacheManager) -> None:
    import threading

    store = ArrayStore()
    wins = {"n": 0}
    barrier = threading.Barrier(8)

    def race() -> None:
        barrier.wait()
        if store.add("only", 1, 30):
            wins["n"] += 1

    threads = [threading.Thread(target=race) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert wins["n"] == 1
