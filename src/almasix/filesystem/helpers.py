"""``storage()`` helper."""

from __future__ import annotations

from typing import Any

from almasix.filesystem.manager import Storage
from almasix.filesystem.storage import Disk


def storage(disk: str | None = None) -> Disk:
    """Resolve a filesystem disk (default disk when ``disk`` is omitted)."""
    return Storage.disk(disk)


def default_filesystems_config(base_path: str | Any = ".") -> dict[str, Any]:
    """Default ``config/filesystems.py`` shape."""
    root = str(base_path)
    return {
        "default": "local",
        "cloud": "s3",
        "disks": {
            "local": {
                "driver": "local",
                "root": f"{root}/storage/app" if root != "." else "storage/app",
                "visibility": "private",
            },
            "public": {
                "driver": "local",
                "root": f"{root}/storage/app/public"
                if root != "."
                else "storage/app/public",
                "url": "/storage",
                "visibility": "public",
            },
            "memory": {
                "driver": "memory",
                "visibility": "private",
            },
            "s3": {
                "driver": "s3",
                "key": None,
                "secret": None,
                "region": None,
                "bucket": None,
                "url": None,
                "endpoint": None,
                "visibility": "private",
            },
        },
        "links": {
            "public/storage": "storage/app/public",
        },
    }
