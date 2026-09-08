"""Filesystem adapter protocol and shared helpers."""

from __future__ import annotations

from typing import Any, BinaryIO, Protocol, runtime_checkable

Visibility = str  # "public" | "private"


@runtime_checkable
class FilesystemAdapter(Protocol):
    """Driver contract mirrored after Flysystem / Laravel disks."""

    def put(
        self,
        path: str,
        contents: bytes | str | BinaryIO,
        *,
        visibility: Visibility | None = None,
    ) -> str: ...

    def get(self, path: str) -> bytes: ...

    def read_stream(self, path: str) -> BinaryIO: ...

    def exists(self, path: str) -> bool: ...

    def delete(self, path: str) -> bool: ...

    def copy(self, source: str, destination: str) -> bool: ...

    def move(self, source: str, destination: str) -> bool: ...

    def size(self, path: str) -> int: ...

    def files(self, directory: str = "", *, recursive: bool = False) -> list[str]: ...

    def directories(self, directory: str = "", *, recursive: bool = False) -> list[str]: ...

    def make_directory(self, path: str) -> bool: ...

    def delete_directory(self, path: str) -> bool: ...

    def url(self, path: str) -> str: ...

    def temporary_url(self, path: str, expiration: Any, **options: Any) -> str: ...

    def set_visibility(self, path: str, visibility: Visibility) -> bool: ...

    def get_visibility(self, path: str) -> Visibility: ...


def normalize_path(path: str) -> str:
    """Normalize to forward-slash relative paths without leading slash."""
    cleaned = path.replace("\\", "/").strip("/")
    parts: list[str] = []
    for part in cleaned.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def coerce_bytes(contents: bytes | str | BinaryIO) -> bytes:
    if isinstance(contents, bytes):
        return contents
    if isinstance(contents, str):
        return contents.encode("utf-8")
    data = contents.read()
    if isinstance(data, str):
        return data.encode("utf-8")
    return data
