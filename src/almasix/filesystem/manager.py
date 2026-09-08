"""Storage manager — resolves named disks from config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from almasix.filesystem.drivers.local import LocalAdapter
from almasix.filesystem.drivers.memory import MemoryAdapter
from almasix.filesystem.storage import Disk


class StorageManager:
    """Laravel ``Storage`` manager."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self._config = config or {}
        self._disks: dict[str, Disk] = {}

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = config
        self._disks.clear()

    def get_default_driver(self) -> str:
        return str(self._config.get("default") or "local")

    def disk(self, name: str | None = None) -> Disk:
        key = name or self.get_default_driver()
        if key not in self._disks:
            self._disks[key] = Disk(key, self._resolve_adapter(key))
        return self._disks[key]

    def cloud(self) -> Disk:
        cloud = self._config.get("cloud") or "s3"
        return self.disk(str(cloud))

    def _disk_config(self, name: str) -> dict[str, Any]:
        disks = self._config.get("disks") or {}
        cfg = disks.get(name)
        if cfg is None:
            raise KeyError(f"Disk [{name}] is not configured.")
        return dict(cfg)

    def _resolve_adapter(self, name: str) -> Any:
        cfg = self._disk_config(name)
        driver = str(cfg.get("driver") or "local")
        if driver == "local":
            root = cfg.get("root")
            if root is None and self.app is not None:
                root = self.app.path("storage", "app")
            root = Path(root or "storage/app")
            if not root.is_absolute() and self.app is not None:
                root = Path(self.app.base_path) / root
            return LocalAdapter(
                root,
                url_prefix=str(cfg.get("url") or "/storage"),
                visibility=str(cfg.get("visibility") or "private"),
            )
        if driver == "public":
            # Alias shape: public local disk
            root = cfg.get("root")
            if root is None and self.app is not None:
                root = self.app.path("storage", "app", "public")
            root = Path(root or "storage/app/public")
            if not root.is_absolute() and self.app is not None:
                root = Path(self.app.base_path) / root
            return LocalAdapter(
                root,
                url_prefix=str(cfg.get("url") or "/storage"),
                visibility="public",
            )
        if driver in {"memory", "array"}:
            return MemoryAdapter(
                url_prefix=str(cfg.get("url") or "/memory"),
                visibility=str(cfg.get("visibility") or "private"),
            )
        if driver in {"s3", "s3-compatible", "minio"}:
            from almasix.filesystem.drivers.s3 import S3Adapter

            return S3Adapter(
                bucket=str(cfg.get("bucket") or ""),
                root=str(cfg.get("root") or ""),
                url=cfg.get("url"),
                visibility=str(cfg.get("visibility") or "private"),
                region=cfg.get("region"),
                endpoint=cfg.get("endpoint"),
                key=cfg.get("key"),
                secret=cfg.get("secret"),
                client=cfg.get("client"),
            )
        raise ValueError(f"Unsupported filesystem driver: {driver!r}")


class Storage:
    """Static-style façade: ``Storage.disk()`` / ``Storage.put()``."""

    _manager: StorageManager | None = None

    @classmethod
    def set_manager(cls, manager: StorageManager | None) -> None:
        cls._manager = manager

    @classmethod
    def manager(cls) -> StorageManager:
        if cls._manager is None:
            cls._manager = StorageManager()
        return cls._manager

    @classmethod
    def disk(cls, name: str | None = None) -> Disk:
        return cls.manager().disk(name)

    @classmethod
    def cloud(cls) -> Disk:
        return cls.manager().cloud()

    @classmethod
    def put(cls, path: str, contents: Any, **kwargs: Any) -> str:
        return cls.disk().put(path, contents, **kwargs)

    @classmethod
    def get(cls, path: str) -> bytes:
        return cls.disk().get(path)

    @classmethod
    def exists(cls, path: str) -> bool:
        return cls.disk().exists(path)

    @classmethod
    def missing(cls, path: str) -> bool:
        return cls.disk().missing(path)

    @classmethod
    def delete(cls, *paths: str) -> bool:
        return cls.disk().delete(*paths)

    @classmethod
    def copy(cls, source: str, destination: str) -> bool:
        return cls.disk().copy(source, destination)

    @classmethod
    def move(cls, source: str, destination: str) -> bool:
        return cls.disk().move(source, destination)

    @classmethod
    def url(cls, path: str) -> str:
        return cls.disk().url(path)

    @classmethod
    def temporary_url(cls, path: str, expiration: Any, **options: Any) -> str:
        return cls.disk().temporary_url(path, expiration, **options)

    @classmethod
    def path(cls, path: str = "") -> str:
        return cls.disk().path(path)
