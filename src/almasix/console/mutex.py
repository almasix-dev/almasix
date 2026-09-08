"""Filesystem mutex for overlapping scheduled events."""

from __future__ import annotations

import os
import time
from pathlib import Path


class Mutex:
    """Exclusive file lock under ``storage/framework/schedule``."""

    def __init__(self, base_path: Path, name: str) -> None:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
        self.path = Path(base_path) / "storage" / "framework" / "schedule" / f"{safe}.lock"
        self._fd: int | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR)
        try:
            if os.name == "nt":  # pragma: no cover - windows
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return False
        self._fd = fd
        os.write(fd, str(os.getpid()).encode("ascii"))
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if os.name != "nt":
                import fcntl

                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


def sleep_until(seconds: float) -> None:
    time.sleep(max(0.0, seconds))
