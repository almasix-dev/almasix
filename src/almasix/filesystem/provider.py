"""Filesystem service provider."""

from __future__ import annotations

from almasix.filesystem.manager import Storage, StorageManager
from almasix.providers.provider import ServiceProvider


class FilesystemServiceProvider(ServiceProvider):
    """Binds Storage manager from ``config/filesystems``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            config = dict(app.config.get("filesystems") or {})
            if not config:
                from almasix.filesystem.helpers import default_filesystems_config

                config = default_filesystems_config(app.base_path)
                # Rewrite roots to absolute app paths.
                disks = config.get("disks") or {}
                for name, disk in disks.items():
                    if disk.get("driver") in {"local", "public"} and "root" in disk:
                        root = disk["root"]
                        if not str(root).startswith(str(app.base_path)):
                            disk = {**disk, "root": str(app.path(*str(root).split("/")))}
                            disks[name] = disk
                config["disks"] = disks
            manager = StorageManager(app, config)
            Storage.set_manager(manager)
            return manager

        app.container.singleton(StorageManager, factory)
        app.container.alias(StorageManager, "filesystem")
        app.container.alias(StorageManager, "storage")

    def boot(self) -> None:
        if self.app.container.bound(StorageManager):
            Storage.set_manager(self.app.make(StorageManager))
