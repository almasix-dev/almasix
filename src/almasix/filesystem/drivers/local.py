"""Local filesystem disk driver."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import quote

from almasix.filesystem.adapter import Visibility, coerce_bytes, normalize_path


class LocalAdapter:
    """Disk rooted at a local directory (``storage/app``, ``storage/app/public``, …)."""

    def __init__(
        self,
        root: str | Path,
        *,
        url_prefix: str = "/storage",
        visibility: Visibility = "private",
    ) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.url_prefix = url_prefix.rstrip("/") or "/storage"
        self.default_visibility = visibility
        self._visibility: dict[str, Visibility] = {}

    def _full(self, path: str) -> Path:
        relative = normalize_path(path)
        full = (self.root / relative).resolve()
        if self.root not in full.parents and full != self.root:
            raise ValueError(f"Path escapes disk root: {path!r}")
        return full

    def get(self, path: str) -> bytes:
        return self._full(path).read_bytes()

    def read_stream(self, path: str) -> BinaryIO:
        return self._full(path).open("rb")

    def write_stream(
        self,
        path: str,
        stream: BinaryIO,
        *,
        visibility: Visibility | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> str:
        relative = normalize_path(path)
        target = self._full(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                handle.write(chunk)
        self._visibility[relative] = visibility or self.default_visibility
        return relative

    def put(
        self,
        path: str,
        contents: bytes | str | BinaryIO,
        *,
        visibility: Visibility | None = None,
    ) -> str:
        if hasattr(contents, "read") and not isinstance(contents, (bytes, str)):
            return self.write_stream(path, contents, visibility=visibility)  # type: ignore[arg-type]
        relative = normalize_path(path)
        target = self._full(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = coerce_bytes(contents)
        target.write_bytes(data)
        self._visibility[relative] = visibility or self.default_visibility
        return relative

    def exists(self, path: str) -> bool:
        return self._full(path).exists()

    def delete(self, path: str) -> bool:
        target = self._full(path)
        if not target.exists():
            return False
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        self._visibility.pop(normalize_path(path), None)
        return True

    def copy(self, source: str, destination: str) -> bool:
        src = self._full(source)
        dst = self._full(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        vis = self._visibility.get(normalize_path(source), self.default_visibility)
        self._visibility[normalize_path(destination)] = vis
        return True

    def move(self, source: str, destination: str) -> bool:
        src = self._full(source)
        dst = self._full(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        src_key = normalize_path(source)
        dst_key = normalize_path(destination)
        if src_key in self._visibility:
            self._visibility[dst_key] = self._visibility.pop(src_key)
        return True

    def size(self, path: str) -> int:
        return self._full(path).stat().st_size

    def files(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        base = self._full(directory) if directory else self.root
        if not base.exists():
            return []
        pattern = "**/*" if recursive else "*"
        results: list[str] = []
        for item in sorted(base.glob(pattern)):
            if item.is_file():
                results.append(normalize_path(str(item.relative_to(self.root))))
        return results

    def directories(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        base = self._full(directory) if directory else self.root
        if not base.exists():
            return []
        pattern = "**/*" if recursive else "*"
        results: list[str] = []
        for item in sorted(base.glob(pattern)):
            if item.is_dir():
                results.append(normalize_path(str(item.relative_to(self.root))))
        return results

    def make_directory(self, path: str) -> bool:
        self._full(path).mkdir(parents=True, exist_ok=True)
        return True

    def delete_directory(self, path: str) -> bool:
        target = self._full(path)
        if not target.exists():
            return False
        shutil.rmtree(target)
        return True

    def url(self, path: str) -> str:
        relative = normalize_path(path)
        return f"{self.url_prefix}/{quote(relative, safe='/')}"

    def temporary_url(self, path: str, expiration: Any, **options: Any) -> str:
        del path, expiration, options
        raise RuntimeError(
            "This driver does not support creating temporary URLs. "
            "Use an S3-compatible disk (or generate your own signed URLs)."
        )

    def set_visibility(self, path: str, visibility: Visibility) -> bool:
        self._visibility[normalize_path(path)] = visibility
        target = self._full(path)
        if target.is_file():
            # Best-effort POSIX mode for public vs private files.
            mode = 0o644 if visibility == "public" else 0o600
            try:
                target.chmod(mode)
            except OSError:
                pass
        return True

    def get_visibility(self, path: str) -> Visibility:
        return self._visibility.get(normalize_path(path), self.default_visibility)

    def path(self, path: str = "") -> str:
        """Absolute filesystem path for integrations (mail attachments, etc.)."""
        if not path:
            return str(self.root)
        return str(self._full(path))
