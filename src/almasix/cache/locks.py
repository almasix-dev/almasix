"""Atomic cache locks (Laravel ``Cache::lock``)."""

from __future__ import annotations

import pickle
import secrets
import time
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from almasix.cache.store import Repository


class LockTimeoutError(TimeoutError):
    """Raised when ``block()`` cannot acquire a lock in time."""


class CacheLock:
    """Mutex stored via the cache store's atomic ``add`` (owner token + TTL).

    Used by array / file stores. Database store uses ``DatabaseLock`` instead.
    """

    def __init__(
        self,
        repository: Repository,
        name: str,
        *,
        seconds: int | None = None,
        owner: str | None = None,
    ) -> None:
        self.repository = repository
        self.name = name
        self.seconds = 86400 if seconds is None else max(1, int(seconds))
        self.owner = owner or f"{uuid.uuid4().hex}:{secrets.token_hex(4)}"
        self._key = f"lock:{name}"

    def get(self, callback: Any | None = None) -> bool | Any:
        """Acquire the lock. Optionally run ``callback`` and release."""
        acquired = self.repository.add(self._key, self.owner, self.seconds)
        if not acquired:
            return False
        if callback is None:
            return True
        try:
            return callback()
        finally:
            self.release()

    def block(self, seconds: int, callback: Any | None = None) -> Any:
        """Block until the lock is acquired or ``seconds`` elapses."""
        deadline = time.monotonic() + max(0, int(seconds))
        while True:
            result = self.get(callback)
            if result is not False:
                return True if callback is None else result
            if time.monotonic() >= deadline:
                raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
            time.sleep(0.05)

    def release(self) -> bool:
        current = self.repository.get(self._key)
        if current != self.owner:
            return False
        return self.repository.forget(self._key)

    def force_release(self) -> bool:
        return self.repository.forget(self._key)

    def owner_token(self) -> str:
        return self.owner

    def __enter__(self) -> CacheLock:
        if self.get() is False:
            raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()


class FileLock:
    """File-backed lock under ``storage/.../cache/data/.locks`` (flock)."""

    def __init__(
        self,
        store: Any,
        name: str,
        *,
        seconds: int | None = None,
        owner: str | None = None,
    ) -> None:
        self.store = store
        self.name = name
        self.seconds = 86400 if seconds is None else max(1, int(seconds))
        self.owner = owner or f"{uuid.uuid4().hex}:{secrets.token_hex(4)}"
        self._path = store._lock_path(name)

    def get(self, callback: Any | None = None) -> bool | Any:
        acquired = self._acquire()
        if not acquired:
            return False
        if callback is None:
            return True
        try:
            return callback()
        finally:
            self.release()

    def block(self, seconds: int, callback: Any | None = None) -> Any:
        deadline = time.monotonic() + max(0, int(seconds))
        while True:
            result = self.get(callback)
            if result is not False:
                return True if callback is None else result
            if time.monotonic() >= deadline:
                raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
            time.sleep(0.05)

    def release(self) -> bool:
        path = self._path
        if not path.is_file():
            return False
        try:
            import fcntl
        except ImportError:  # pragma: no cover
            return self._release_no_fcntl()

        with path.open("r+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            raw = handle.read()
            try:
                payload = pickle.loads(raw)
            except Exception:
                path.unlink(missing_ok=True)
                return True
            if payload.get("owner") != self.owner:
                return False
            path.unlink(missing_ok=True)
            return True

    def _release_no_fcntl(self) -> bool:  # pragma: no cover
        path = self._path
        try:
            payload = pickle.loads(path.read_bytes())
        except Exception:
            path.unlink(missing_ok=True)
            return True
        if payload.get("owner") != self.owner:
            return False
        path.unlink(missing_ok=True)
        return True

    def force_release(self) -> bool:
        self._path.unlink(missing_ok=True)
        return True

    def owner_token(self) -> str:
        return self.owner

    def __enter__(self) -> FileLock:
        if self.get() is False:
            raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()

    def _acquire(self) -> bool:
        path = self._path
        path.parent.mkdir(parents=True, exist_ok=True)
        expires = time.time() + self.seconds
        payload = pickle.dumps({"owner": self.owner, "expires": expires}, protocol=4)

        try:
            import fcntl
        except ImportError:  # pragma: no cover
            return self._acquire_no_fcntl(path, payload)

        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            raw = handle.read()
            if raw:
                try:
                    existing = pickle.loads(raw)
                    if (
                        existing.get("expires", 0) > time.time()
                        and existing.get("owner") != self.owner
                    ):
                        return False
                except Exception:
                    pass
            handle.seek(0)
            handle.truncate()
            handle.write(payload)
            handle.flush()
            return True

    def _acquire_no_fcntl(self, path: Any, payload: bytes) -> bool:  # pragma: no cover
        if path.is_file():
            try:
                existing = pickle.loads(path.read_bytes())
                if existing.get("expires", 0) > time.time() and existing.get("owner") != self.owner:
                    return False
            except Exception:
                pass
        path.write_bytes(payload)
        return True


class DatabaseLock:
    """Lock backed by the ``cache_locks`` table (Laravel ``DatabaseLock``)."""

    def __init__(
        self,
        *,
        connection: str | None,
        table: str,
        name: str,
        seconds: int | None = None,
        owner: str | None = None,
        default_timeout: int = 86400,
    ) -> None:
        from almasix.cache.drivers.database import _run

        self._run = _run
        self.connection = connection
        self.table = table
        self.name = name
        self.seconds = default_timeout if seconds is None else max(1, int(seconds))
        self.owner = owner or f"{uuid.uuid4().hex}:{secrets.token_hex(4)}"

    def get(self, callback: Any | None = None) -> bool | Any:
        acquired = bool(self._run(self._aacquire()))
        if not acquired:
            return False
        if callback is None:
            return True
        try:
            return callback()
        finally:
            self.release()

    def block(self, seconds: int, callback: Any | None = None) -> Any:
        deadline = time.monotonic() + max(0, int(seconds))
        while True:
            result = self.get(callback)
            if result is not False:
                return True if callback is None else result
            if time.monotonic() >= deadline:
                raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
            time.sleep(0.05)

    def release(self) -> bool:
        return bool(self._run(self._arelease()))

    def force_release(self) -> bool:
        return bool(self._run(self._aforce_release()))

    def owner_token(self) -> str:
        return self.owner

    def __enter__(self) -> DatabaseLock:
        if self.get() is False:
            raise LockTimeoutError(f"Unable to acquire lock [{self.name}]")
        return self

    def __exit__(self, *exc: Any) -> None:
        self.release()

    async def _aacquire(self) -> bool:
        from almasix.orm.facade import DB

        now = int(time.time())
        expiration = now + self.seconds
        # Purge expired occasionally (lottery-ish: always cheap on sqlite).
        await DB.statement(
            f"DELETE FROM {self.table} WHERE expiration <= :now",
            {"now": now},
            connection=self.connection,
        )
        dialect = DB.connection(self.connection).dialect
        params = {"key": self.name, "owner": self.owner, "expiration": expiration}

        if dialect == "sqlite":
            affected = await DB.statement(
                f"""
                INSERT OR IGNORE INTO {self.table} (key, owner, expiration)
                VALUES (:key, :owner, :expiration)
                """,
                params,
                connection=self.connection,
            )
            if affected > 0:
                return True
        elif dialect in {"mysql", "mariadb"}:  # pragma: no cover
            affected = await DB.statement(
                f"""
                INSERT IGNORE INTO {self.table} (key, owner, expiration)
                VALUES (:key, :owner, :expiration)
                """,
                params,
                connection=self.connection,
            )
            if affected > 0:
                return True
        else:  # pragma: no cover
            try:
                await DB.statement(
                    f"""
                    INSERT INTO {self.table} (key, owner, expiration)
                    VALUES (:key, :owner, :expiration)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    params,
                    connection=self.connection,
                )
                rows = await DB.select(
                    f"SELECT owner FROM {self.table} WHERE key = :key LIMIT 1",
                    {"key": self.name},
                    connection=self.connection,
                )
                if rows and rows[0].get("owner") == self.owner:
                    return True
            except Exception:
                pass

        # Steal if we own it or it expired (Laravel update path).
        updated = await DB.statement(
            f"""
            UPDATE {self.table}
            SET owner = :owner, expiration = :expiration
            WHERE key = :key
              AND (owner = :owner OR expiration <= :now)
            """,
            {
                "key": self.name,
                "owner": self.owner,
                "expiration": expiration,
                "now": now,
            },
            connection=self.connection,
        )
        return updated >= 1

    async def _arelease(self) -> bool:
        from almasix.orm.facade import DB

        affected = await DB.statement(
            f"""
            DELETE FROM {self.table}
            WHERE key = :key AND owner = :owner
            """,
            {"key": self.name, "owner": self.owner},
            connection=self.connection,
        )
        return affected >= 1

    async def _aforce_release(self) -> bool:
        from almasix.orm.facade import DB

        await DB.statement(
            f"DELETE FROM {self.table} WHERE key = :key",
            {"key": self.name},
            connection=self.connection,
        )
        return True
