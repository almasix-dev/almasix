"""Almasix filesystem — FlySystem-shaped Storage façade."""

from __future__ import annotations

from almasix.filesystem.helpers import storage
from almasix.filesystem.manager import Storage, StorageManager
from almasix.filesystem.storage import Disk

__all__ = ["Disk", "Storage", "StorageManager", "storage"]
