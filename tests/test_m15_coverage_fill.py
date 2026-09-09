"""Coverage fill for almasix.cache."""

from __future__ import annotations

import pickle
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from almasix.cache import Cache, CacheManager, cache, set_manager
from almasix.cache.drivers.array import ArrayStore
from almasix.cache.drivers.database import DatabaseStore
from almasix.cache.drivers.file import FileStore
from almasix.cache.locks import LockTimeoutError
from almasix.cache.schema import ensure_cache_table, ensure_cache_table_sync
from almasix.cache.store import Repository, normalize_ttl
from almasix.framework.application import Application


def test_normalize_ttl_variants() -> None:
    assert normalize_ttl(None) is None
    assert normalize_ttl(10) == 10
    assert normalize_ttl(-5) == 0
    future = datetime.now(UTC).replace(year=2099)
    assert normalize_ttl(future) > 0


def test_array_expiry_and_bad_increment() -> None:
    store = ArrayStore()
    store.put("x", "v", 0)
    time.sleep(0.02)
    # expired immediately if seconds=0 means expire at now
    store.put("y", "v", 1)
    assert store.get("y") == "v"
    store.put("bad", "str", None)
    assert store.increment("bad") is False
    assert store.decrement("bad") is False


def test_file_corrupt_and_expiry(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    path = store._path("k")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-pickle")
    assert store.get("k") is None
    store.put("soon", 1, 0)
    time.sleep(0.01)
    store.put("ok", 1, None)
    assert store.forget("missing") is False
    store.flush()
    # flush empty dir
    assert FileStore(tmp_path / "empty").flush() is True
    store.put("n", "x", None)
    assert store.increment("n") is False


@pytest.mark.asyncio
async def test_database_edges(memory_db) -> None:
    del memory_db
    await ensure_cache_table("sqlite")
    ensure_cache_table_sync("sqlite")
    store = DatabaseStore(connection="sqlite")
    store.put("bad", b"raw-not-used", None)
    # corrupt row
    from almasix.orm.facade import DB

    await DB.statement(
        "DELETE FROM cache WHERE key = :key",
        {"key": "bad"},
        connection="sqlite",
    )
    await DB.statement(
        "INSERT INTO cache (key, value, expiration) VALUES (:key, :value, :expiration)",
        {"key": "bad", "value": b"nope", "expiration": None},
        connection="sqlite",
    )
    assert store.get("bad") is None
    store.put("exp", 1, 0)
    time.sleep(0.01)
    # expired
    store.put("exp2", 1, 1)
    assert store.get("exp2") == 1
    store.put("s", "x", None)
    assert store.increment("s") is False
    assert store.decrement("s") is False
    # non-int increment already covered; hit decrement path via int
    store.put("n", 5, None)
    assert store.decrement("n", 2) == 3


def test_repository_many_and_tags_remember(tmp_path: Path) -> None:
    manager = CacheManager(
        config={
            "default": "array",
            "prefix": "p_",
            "stores": {
                "array": {"driver": "array"},
                "file": {"driver": "file", "path": str(tmp_path)},
            },
        }
    )
    set_manager(manager)
    repo = manager.store()
    repo.put_many({"a": 1, "b": 2}, 30)
    assert repo.many(["a", "b", "c"]) == {"a": 1, "b": 2, "c": None}
    assert repo.delete("a") is True
    assert repo.sear("s", lambda: 9) == 9
    tagged = repo.tags("t1")
    assert tagged.remember("k", 10, lambda: "v") == "v"
    assert tagged.forever("f", 1)
    assert tagged.forget("f") is True
    tagged.flush()
    # file driver via manager
    assert manager.driver("file").put("f", 1)
    set_manager(None)


def test_manager_errors_and_facade() -> None:
    with pytest.raises(RuntimeError):
        Cache.manager()
    with pytest.raises(RuntimeError):
        cache()
    manager = CacheManager(config={"default": "array", "stores": {"array": {"driver": "array"}}})
    set_manager(manager)
    assert Cache.store().put("x", 1)
    assert Cache.flush() is True
    assert Cache.add("x", 1) is True
    assert Cache.remember("r", 5, lambda: 3) == 3
    assert Cache.remember_forever("rf", lambda: 4) == 4
    assert Cache.increment("i") == 1
    assert Cache.decrement("i") == 0
    assert Cache.tags("a").put("k", 1)
    with pytest.raises(ValueError):
        manager.store("nope-driver-missing")
    # unsupported after empty resolve
    with pytest.raises(ValueError):
        CacheManager(config={"default": "weird", "stores": {"weird": {"driver": "weird"}}}).store()
    set_manager(None)


def test_lock_timeout_and_owner_mismatch() -> None:
    manager = CacheManager(config={"default": "array", "stores": {"array": {"driver": "array"}}})
    set_manager(manager)
    lock = Cache.lock("L", seconds=5, owner="owner-a")
    assert lock.get() is True
    other = Cache.lock("L", seconds=5, owner="owner-b")
    assert other.release() is False
    assert lock.force_release() is True
    with pytest.raises(LockTimeoutError):
        with Cache.lock("L2", seconds=5):
            with Cache.lock("L2", seconds=5):
                pass
    set_manager(None)


def test_provider_default_config(tmp_path: Path) -> None:
    from almasix.cache.provider import CacheServiceProvider

    app = Application(tmp_path)
    app.config.set("cache", {})
    CacheServiceProvider(app).register()
    CacheServiceProvider(app).boot()
    assert app.make(CacheManager).get_default_driver() in {"array", "file"}


def test_expiry_null_file_and_lock_block(tmp_path: Path) -> None:
    store = ArrayStore()
    store.put("gone", 1, 0)
    time.sleep(0.02)
    assert store.get("gone") is None

    fs = FileStore(tmp_path / "f")
    fs.put("e", 1, 0)
    time.sleep(0.02)
    assert fs.get("e") is None
    assert fs.forget("missing") is False
    assert FileStore(tmp_path / "missing-root").flush() is True

    manager = CacheManager(
        app=Application(tmp_path),
        config={
            "default": "file",
            "prefix": "",
            "stores": {
                "file": {"driver": "file"},
                "null": {"driver": "null"},
                "array": {"driver": "array"},
            },
        },
    )
    set_manager(manager)
    assert manager.store("file").put("via", 1)
    assert manager.store("null").forever("x", 1) is True
    assert manager.store("null").get("x") is None
    assert manager.store("null").put("y", 1, 1) is True
    assert manager.store("null").add("y", 1) is True
    assert manager.store("null").forget("y") is True
    assert manager.store("null").flush() is True
    lock = Cache.lock("blk", seconds=5)
    assert lock.get() is True
    # exercise block sleep path briefly
    start = time.monotonic()
    with pytest.raises(LockTimeoutError):
        Cache.lock("blk", seconds=5).block(1)
    assert time.monotonic() - start >= 0.05
    assert Cache.lock("blk", seconds=5, owner="other").release() is False
    lock.force_release()
    repo = manager.store("array")
    assert repo.remember_forever("zz", lambda: "ok") == "ok"
    tags = repo.tags("one")
    tags.put("a", 1, 5)
    assert tags.remember("a", 5, lambda: 2) == 1
    assert tags.forever("b", 9)
    set_manager(None)


@pytest.mark.asyncio
async def test_database_expired_value(memory_db) -> None:
    del memory_db
    await ensure_cache_table("sqlite")
    store = DatabaseStore(connection="sqlite")
    from almasix.orm.facade import DB

    await DB.statement(
        "INSERT INTO cache (key, value, expiration) VALUES (:key, :value, :expiration)",
        {"key": "old", "value": pickle.dumps("v"), "expiration": int(time.time()) - 5},
        connection="sqlite",
    )
    assert store.get("old") is None
    store.put("exists", 1, None)
    assert store.add("exists", 2) is False
    # running-loop branch of ensure_cache_table_sync
    ensure_cache_table_sync("sqlite")


def test_sync_database_and_manager_driver(tmp_path: Path) -> None:
    """Hit sync ``_run`` / ``ensure_cache_table_sync`` (no running loop) + manager database path."""
    import asyncio

    from almasix.orm import DatabaseManager
    from almasix.orm import set_manager as set_db

    async def _boot() -> DatabaseManager:
        manager = DatabaseManager(
            {
                "default": "sqlite",
                "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
            }
        )
        set_db(manager)
        return manager

    db = asyncio.run(_boot())
    try:
        ensure_cache_table_sync("sqlite")
        store = DatabaseStore(connection="sqlite")
        assert store.put("sync", 1, None) is True
        assert store.get("sync") == 1
        assert store.add("sync", 2) is False
        assert store.add("fresh", 3) is True

        cache_mgr = CacheManager(
            app=Application(tmp_path),
            config={
                "default": "database",
                "stores": {
                    "database": {
                        "driver": "database",
                        "connection": "sqlite",
                        "table": "cache",
                    }
                },
            },
        )
        repo = cache_mgr.store("database")
        assert repo.put("via-mgr", 7) is True
        assert repo.get("via-mgr") == 7
        assert repo.remember_forever("rf", lambda: "a") == "a"
        assert repo.remember_forever("rf", lambda: "b") == "a"
    finally:
        asyncio.run(db.disconnect())
        set_db(None)


def test_file_ttl_increment_and_removed_dir(tmp_path: Path) -> None:
    import shutil

    store = FileStore(tmp_path / "data")
    store.put("n", 1, 30)
    assert store.increment("n") == 2
    shutil.rmtree(tmp_path / "data")
    assert store.flush() is True


def test_array_expired_add_increment_flush_locks() -> None:
    store = ArrayStore()
    store.put("e", 1, 0)
    time.sleep(0.02)
    assert store.add("e", 2, 30) is True
    store.put("exp", 5, 0)
    time.sleep(0.02)
    assert store.increment("exp") == 1
    store.add("lock:x", "owner", 30)
    assert store.flush_locks() is True
    assert store.get("lock:x") is None


def test_file_lock_and_add_expired(tmp_path: Path) -> None:
    from almasix.cache.locks import FileLock

    store = FileStore(tmp_path / "fl")
    store.put("gone", 1, 0)
    time.sleep(0.02)
    assert store.add("gone", 2) is True
    # corrupt then add
    path = store._path("c")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"bad")
    assert store.add("c", 1) is True

    lock = store.lock("f1", seconds=5)
    assert lock.get(lambda: "ok") == "ok"
    lock2 = store.lock("f2", seconds=5)
    assert lock2.get() is True
    assert store.lock("f2", seconds=5).get() is False
    with pytest.raises(LockTimeoutError):
        store.lock("f2", seconds=5).block(0)
    assert store.lock("f2", seconds=5, owner="other").release() is False
    lock2.force_release()
    with store.lock("f3", seconds=5):
        pass
    assert store.restore_lock("f3", "nobody").release() is False
    assert store.flush_locks() is True
    # release missing path
    assert FileLock(store, "missing", seconds=5, owner="o").release() is False


@pytest.mark.asyncio
async def test_database_lock_full(memory_db) -> None:
    del memory_db
    await ensure_cache_table("sqlite")
    store = DatabaseStore(connection="sqlite")
    lock = store.lock("d1", seconds=5)
    assert lock.get(lambda: 9) == 9
    assert lock.get() is True
    with pytest.raises(LockTimeoutError):
        store.lock("d1", seconds=5).block(0)
    lock.force_release()
    with store.lock("d2", seconds=5):
        with pytest.raises(LockTimeoutError):
            with store.lock("d2", seconds=5):
                pass
    # steal expired lock
    from almasix.orm.facade import DB

    await DB.statement(
        "INSERT INTO cache_locks (key, owner, expiration) VALUES (:key, :owner, :expiration)",
        {"key": "old", "owner": "dead", "expiration": int(time.time()) - 10},
        connection="sqlite",
    )
    assert store.lock("old", seconds=5, owner="alive").get() is True
    # expired row increment path
    await DB.statement(
        "INSERT INTO cache (key, value, expiration) VALUES (:key, :value, :expiration)",
        {"key": "ie", "value": pickle.dumps(3), "expiration": int(time.time()) - 1},
        connection="sqlite",
    )
    assert store.increment("ie") == 1


def test_manager_facade_extras(tmp_path: Path) -> None:
    manager = CacheManager(
        config={
            "default": "array",
            "stores": {
                "array": {"driver": "array"},
                "file": {"driver": "file", "path": str(tmp_path)},
            },
        }
    )
    manager.set_default_driver("array")
    set_manager(manager)
    Cache.extend("from_facade", lambda app, cfg, name: ArrayStore())
    manager.config.setdefault("stores", {})["from_facade"] = {"driver": "from_facade"}
    assert manager.store("from_facade").put("z", 1)

    def as_repo(app, cfg, name):
        return Repository(ArrayStore(), prefix="ext_")

    manager.extend("repo_driver", as_repo)
    manager.config["stores"]["repo_driver"] = {"driver": "repo_driver"}
    assert manager.store("repo_driver").put("a", 1)

    Cache.put("touch-me", 1, 5)
    assert Cache.touch("touch-me", 10) is True
    assert Cache.many(["touch-me"]) == {"touch-me": 1}
    assert Cache.put_many({"p": 1}, 5) is True
    assert Cache.without_overlapping("busy", lambda: 1) == 1
    held = Cache.lock("busy2", seconds=5)
    assert held.get() is True
    assert Cache.without_overlapping("busy2", lambda: 1) is None
    # CacheLock.block sleep path
    with pytest.raises(LockTimeoutError):
        Cache.lock("busy2", seconds=5).block(1)
    held.release()
    # restore_lock via repository on file store
    file_repo = manager.store("file")
    fl = file_repo.lock("fr", seconds=5)
    assert fl.get() is True
    assert fl.owner_token()
    assert file_repo.restore_lock("fr", fl.owner_token()).release() is True

    # flush_locks fallback when store lacks the method
    class NoFlushStore:
        supports_tags = False

        def get(self, key: str) -> Any:
            return None

        def put(self, key: str, value: Any, seconds: int | None) -> bool:
            return True

        def forever(self, key: str, value: Any) -> bool:
            return True

        def forget(self, key: str) -> bool:
            return True

        def flush(self) -> bool:
            return True

        def add(self, key: str, value: Any, seconds: int | None) -> bool:
            return True

        def increment(self, key: str, amount: int = 1) -> int | bool:
            return amount

        def decrement(self, key: str, amount: int = 1) -> int | bool:
            return amount

    assert Repository(NoFlushStore()).flush_locks() is True  # type: ignore[arg-type]
    manager.forget_driver("array")
    manager.forget_driver()
    assert Cache.flush_locks() is True
    set_manager(None)


def test_file_increment_expired_and_corrupt_lock(tmp_path: Path) -> None:
    store = FileStore(tmp_path / "inc")
    store.put("e", 1, 0)
    time.sleep(0.02)
    assert store.increment("e") == 1
    path = store._path("bad")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not-pickle")
    assert store.increment("bad") == 1

    lock = store.lock("held", seconds=5)
    assert lock.get() is True
    with pytest.raises(LockTimeoutError):
        store.lock("held", seconds=5).block(1)
    with pytest.raises(LockTimeoutError):
        with store.lock("held", seconds=5):
            pass
    # corrupt lock file then release
    lock_path = store._lock_path("held")
    lock_path.write_bytes(b"nope")
    assert lock.release() is True
    # corrupt then re-acquire
    lock_path.write_bytes(b"nope")
    assert store.lock("held", seconds=5).get() is True
    assert store.flush_locks() is True
    assert store.flush_locks() is True  # no .locks dir


def test_cache_lock_sleep_and_db_block_success(tmp_path: Path) -> None:
    """Hit FileLock/DatabaseLock block success + sleep arcs."""
    import asyncio

    from almasix.orm import DatabaseManager
    from almasix.orm import set_manager as set_db

    fs = FileStore(tmp_path / "locks")
    # Success path of FileLock.block (line: return True when acquired)
    assert fs.lock("free", seconds=5).block(1) is True
    assert fs.lock("free-cb", seconds=5).block(1, lambda: "ok") == "ok"

    held = fs.lock("sleep", seconds=5)
    assert held.get() is True
    start = time.monotonic()
    with pytest.raises(LockTimeoutError):
        fs.lock("sleep", seconds=5).block(1)
    assert time.monotonic() - start >= 0.05
    # Re-acquire as same owner overwrites (branch where condition is false)
    assert fs.lock("sleep", seconds=5, owner=held.owner_token()).get() is True
    # Expired lock file → overwrite path
    path = fs._lock_path("expired")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps({"owner": "old", "expires": time.time() - 10}, protocol=4))
    assert fs.lock("expired", seconds=5).get() is True
    held.force_release()

    async def _boot() -> DatabaseManager:
        manager = DatabaseManager(
            {
                "default": "sqlite",
                "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
            }
        )
        set_db(manager)
        return manager

    db = asyncio.run(_boot())
    try:
        ensure_cache_table_sync("sqlite")
        store = DatabaseStore(connection="sqlite")
        assert store.lock("free", seconds=5).block(1) is True
        store.flush_locks()
        assert store.lock("cb", seconds=5).block(1, lambda: "ok") == "ok"
        # Sleep path while held
        held_db = store.lock("held-db", seconds=5)
        assert held_db.get() is True
        start = time.monotonic()
        with pytest.raises(LockTimeoutError):
            store.lock("held-db", seconds=5).block(1)
        assert time.monotonic() - start >= 0.05
        held_db.force_release()
    finally:
        asyncio.run(db.disconnect())
        set_db(None)


def test_tags_duplicate_key_and_provider_unbound(tmp_path: Path) -> None:
    from almasix.cache.provider import CacheServiceProvider

    manager = CacheManager(config={"default": "array", "stores": {"array": {"driver": "array"}}})
    set_manager(manager)
    tags = Cache.tags("dup")
    tags.put("k", 1, 10)
    tags.put("k", 2, 10)  # key already in meta list
    assert tags.get("k") == 2
    set_manager(None)

    app = Application(tmp_path)
    # boot with no CacheManager binding → branch where bound is false
    CacheServiceProvider(app).boot()


def test_schedule_filesystem_mutex_fallback(tmp_path: Path) -> None:
    """When Cache is not booted, without_overlapping uses filesystem Mutex."""
    from almasix.console.scheduling import Event, _try_cache_lock, run_event

    set_manager(None)
    assert _try_cache_lock("x") is None

    ran = {"n": 0}

    def cb() -> None:
        ran["n"] += 1

    event = Event(description="fs-mutex", callback=cb).without_overlapping_lock()
    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 1
    # Second overlapping run while mutex file held — acquire another Event same mutex
    # Hold by running with a long-held lock via Mutex directly
    from almasix.console.mutex import Mutex

    mutex = Mutex(tmp_path, event.mutex_name())
    assert mutex.acquire() is True
    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 1  # skipped
    mutex.release()
    assert run_event(event, base_path=tmp_path) == 0
    assert ran["n"] == 2
