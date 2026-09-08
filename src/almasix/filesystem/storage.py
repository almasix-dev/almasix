"""Disk wrapper — Laravel ``Storage::disk()`` surface."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, BinaryIO

from almasix.filesystem.adapter import FilesystemAdapter, Visibility


class Disk:
    """Named disk over a ``FilesystemAdapter``."""

    def __init__(self, name: str, adapter: FilesystemAdapter) -> None:
        self.name = name
        self.adapter = adapter

    def put(
        self,
        path: str,
        contents: bytes | str | BinaryIO,
        *,
        visibility: Visibility | None = None,
    ) -> str:
        return self.adapter.put(path, contents, visibility=visibility)

    def put_file(self, path: str, file: Any, *, visibility: Visibility | None = None) -> str:
        """Store an ``UploadedFile`` / path / file-like under ``path`` (directory or full key)."""
        filename = getattr(file, "filename", None) or getattr(file, "name", None) or "upload"
        if isinstance(filename, Path):
            filename = filename.name
        target = path.rstrip("/")
        if not target.endswith(str(filename)):
            target = f"{target}/{filename}" if target else str(filename)

        if hasattr(file, "read"):
            # Sync read preferred; async UploadedFile is handled by put_file_async.
            import inspect

            result = file.read()
            if inspect.isawaitable(result):
                raise TypeError("Use put_file_async() for async UploadedFile objects")
            contents = result
            if isinstance(contents, str):
                contents = contents.encode("utf-8")
            return self.put(target, contents, visibility=visibility)

        if isinstance(file, (str, Path)):
            return self.put(target, Path(file).read_bytes(), visibility=visibility)
        raise TypeError(f"Unsupported upload type: {type(file)!r}")

    async def put_file_async(
        self,
        path: str,
        file: Any,
        *,
        visibility: Visibility | None = None,
    ) -> str:
        """Async variant for Starlette/Almasix ``UploadedFile``."""
        filename = getattr(file, "filename", None) or getattr(file, "name", None) or "upload"
        target = path.rstrip("/")
        if not target.endswith(str(filename)):
            target = f"{target}/{filename}" if target else str(filename)
        data = await file.read()
        return self.put(target, data, visibility=visibility)

    def get(self, path: str) -> bytes:
        return self.adapter.get(path)

    def get_string(self, path: str, *, encoding: str = "utf-8") -> str:
        return self.get(path).decode(encoding)

    def read_stream(self, path: str) -> BinaryIO:
        return self.adapter.read_stream(path)

    def write_stream(
        self,
        path: str,
        stream: BinaryIO,
        *,
        visibility: Visibility | None = None,
        chunk_size: int = 1024 * 1024,
    ) -> str:
        writer = getattr(self.adapter, "write_stream", None)
        if callable(writer):
            return writer(path, stream, visibility=visibility, chunk_size=chunk_size)
        return self.put(path, stream, visibility=visibility)

    def exists(self, path: str) -> bool:
        return self.adapter.exists(path)

    def missing(self, path: str) -> bool:
        return not self.exists(path)

    def delete(self, *paths: str) -> bool:
        ok = True
        for path in paths:
            ok = self.adapter.delete(path) and ok
        return ok

    def copy(self, source: str, destination: str) -> bool:
        return self.adapter.copy(source, destination)

    def move(self, source: str, destination: str) -> bool:
        return self.adapter.move(source, destination)

    def size(self, path: str) -> int:
        return self.adapter.size(path)

    def files(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        return self.adapter.files(directory, recursive=recursive)

    def all_files(self, directory: str = "") -> list[str]:
        return self.files(directory, recursive=True)

    def directories(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        return self.adapter.directories(directory, recursive=recursive)

    def make_directory(self, path: str) -> bool:
        return self.adapter.make_directory(path)

    def delete_directory(self, path: str) -> bool:
        return self.adapter.delete_directory(path)

    def url(self, path: str) -> str:
        return self.adapter.url(path)

    def temporary_url(
        self,
        path: str,
        expiration: timedelta | int | Any,
        **options: Any,
    ) -> str:
        return self.adapter.temporary_url(path, expiration, **options)

    def set_visibility(self, path: str, visibility: Visibility) -> bool:
        return self.adapter.set_visibility(path, visibility)

    def get_visibility(self, path: str) -> Visibility:
        return self.adapter.get_visibility(path)

    def path(self, path: str = "") -> str:
        path_fn = getattr(self.adapter, "path", None)
        if callable(path_fn):
            return str(path_fn(path))
        raise RuntimeError(f"Disk {self.name!r} does not expose local paths")
