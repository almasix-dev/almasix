"""A disk under test — write to memory, then assert on what is there."""

from __future__ import annotations

from typing import Any

from almasix.filesystem.drivers.memory import MemoryAdapter
from almasix.filesystem.storage import Disk


class FakeDisk(Disk):
    """A disk backed by memory, with Laravel's file assertions.

    Installed by `fake_disk()`. Everything a `Disk` can do still works — the
    files simply never reach the filesystem.
    """

    def assert_exists(self, *paths: str) -> None:
        missing = [path for path in paths if not self.exists(path)]
        if missing:
            raise AssertionError(
                f"[{self.name}] is missing {missing}. It holds: {self._listing()}."
            )

    def assert_missing(self, *paths: str) -> None:
        present = [path for path in paths if self.exists(path)]
        if present:
            raise AssertionError(f"[{self.name}] holds {present}, and should not.")

    def assert_count(self, directory: str = "", count: int = 0) -> None:
        found = len(self.files(directory, recursive=True))
        if found != count:
            raise AssertionError(
                f"Expected {count} file(s) in [{directory or '/'}]; found {found}."
            )

    def assert_directory_empty(self, directory: str = "") -> None:
        found = self.files(directory, recursive=True)
        if found:
            raise AssertionError(f"[{directory or '/'}] is not empty; it holds {found}.")

    def assert_has(self, path: str, contents: bytes | str) -> None:
        """The file is there, and this is what is in it."""
        self.assert_exists(path)
        wanted = contents.encode() if isinstance(contents, str) else contents
        actual = self.get(path)
        if actual != wanted:
            raise AssertionError(f"[{path}] holds {actual!r}, not {wanted!r}.")

    def _listing(self) -> str:
        return ", ".join(self.files("", recursive=True)) or "nothing"

    def __repr__(self) -> str:
        return f"FakeDisk({self.name!r})"


def fake_disk(name: str | None = None, *, manager: Any = None) -> FakeDisk:
    """Swap a disk for one in memory (Laravel `Storage::fake()`)."""
    from almasix.filesystem.manager import Storage

    store = manager or Storage.manager()
    key = name or store.get_default_driver()
    disk = FakeDisk(key, MemoryAdapter(url_prefix=f"/{key}"))
    store._disks[key] = disk
    return disk
