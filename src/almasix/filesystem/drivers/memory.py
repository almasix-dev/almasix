"""In-memory disk — ideal for tests."""

from __future__ import annotations

from io import BytesIO
from typing import Any, BinaryIO
from urllib.parse import quote

from almasix.filesystem.adapter import Visibility, coerce_bytes, normalize_path


class MemoryAdapter:
    """Dict-backed filesystem for unit tests."""

    def __init__(self, *, url_prefix: str = "/memory", visibility: Visibility = "private") -> None:
        self.url_prefix = url_prefix.rstrip("/") or "/memory"
        self.default_visibility = visibility
        self._files: dict[str, bytes] = {}
        self._dirs: set[str] = set()
        self._visibility: dict[str, Visibility] = {}

    def put(
        self,
        path: str,
        contents: bytes | str | BinaryIO,
        *,
        visibility: Visibility | None = None,
    ) -> str:
        relative = normalize_path(path)
        self._ensure_parents(relative)
        self._files[relative] = coerce_bytes(contents)
        self._visibility[relative] = visibility or self.default_visibility
        return relative

    def get(self, path: str) -> bytes:
        key = normalize_path(path)
        if key not in self._files:
            raise FileNotFoundError(path)
        return self._files[key]

    def read_stream(self, path: str) -> BinaryIO:
        return BytesIO(self.get(path))

    def exists(self, path: str) -> bool:
        key = normalize_path(path)
        return key in self._files or key in self._dirs

    def delete(self, path: str) -> bool:
        key = normalize_path(path)
        if key in self._files:
            del self._files[key]
            self._visibility.pop(key, None)
            return True
        if key in self._dirs:
            prefix = key + "/"
            for file_key in list(self._files):
                if file_key.startswith(prefix):
                    del self._files[file_key]
                    self._visibility.pop(file_key, None)
            self._dirs = {d for d in self._dirs if d != key and not d.startswith(prefix)}
            return True
        return False

    def copy(self, source: str, destination: str) -> bool:
        src = normalize_path(source)
        dst = normalize_path(destination)
        if src not in self._files:
            raise FileNotFoundError(source)
        self._ensure_parents(dst)
        self._files[dst] = self._files[src]
        self._visibility[dst] = self._visibility.get(src, self.default_visibility)
        return True

    def move(self, source: str, destination: str) -> bool:
        self.copy(source, destination)
        self.delete(source)
        return True

    def size(self, path: str) -> int:
        return len(self.get(path))

    def files(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        base = normalize_path(directory)
        prefix = f"{base}/" if base else ""
        results: list[str] = []
        for key in sorted(self._files):
            if base and not key.startswith(prefix):
                continue
            rest = key[len(prefix) :] if prefix else key
            if not recursive and "/" in rest:
                continue
            results.append(key)
        return results

    def directories(self, directory: str = "", *, recursive: bool = False) -> list[str]:
        base = normalize_path(directory)
        prefix = f"{base}/" if base else ""
        found: set[str] = set()
        for key in list(self._dirs) + list(self._files):
            if base and not (key == base or key.startswith(prefix)):
                continue
            rest = key[len(prefix) :] if prefix else key
            if not rest or rest == key and base and key == base:
                continue
            first = rest.split("/", 1)[0]
            if not first:
                continue
            found.add(f"{prefix}{first}" if prefix else first)
            if recursive:
                parts = rest.split("/")
                for i in range(1, len(parts)):
                    found.add(f"{prefix}{'/'.join(parts[:i])}" if prefix else "/".join(parts[:i]))
        return sorted(
            d for d in found if d in self._dirs or any(f.startswith(d + "/") for f in self._files)
        )

    def make_directory(self, path: str) -> bool:
        key = normalize_path(path)
        if key:
            self._dirs.add(key)
            self._ensure_parents(key + "/x")
        return True

    def delete_directory(self, path: str) -> bool:
        return self.delete(path)

    def url(self, path: str) -> str:
        return f"{self.url_prefix}/{quote(normalize_path(path), safe='/')}"

    def temporary_url(self, path: str, expiration: Any, **options: Any) -> str:
        del path, expiration, options
        raise RuntimeError(
            "This driver does not support creating temporary URLs. "
            "Use an S3-compatible disk (or generate your own signed URLs)."
        )

    def set_visibility(self, path: str, visibility: Visibility) -> bool:
        self._visibility[normalize_path(path)] = visibility
        return True

    def get_visibility(self, path: str) -> Visibility:
        return self._visibility.get(normalize_path(path), self.default_visibility)

    def _ensure_parents(self, path: str) -> None:
        parts = normalize_path(path).split("/")[:-1]
        current: list[str] = []
        for part in parts:
            current.append(part)
            self._dirs.add("/".join(current))
