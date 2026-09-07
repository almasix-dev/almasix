"""Recorded outgoing HTTP request (for fakes / assertions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit


@dataclass
class RecordedRequest:
    """A request the HTTP client sent (or would send)."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    data: Any = None
    body: bytes | str | None = None
    files: dict[str, Any] | None = None
    cookies: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> str:
        return urlsplit(self.url).path or "/"

    def header(self, key: str, default: str | None = None) -> str | None:
        lower = key.lower()
        for name, value in self.headers.items():
            if name.lower() == lower:
                return value
        return default

    def has_header(self, key: str, value: str | None = None) -> bool:
        found = self.header(key)
        if found is None:
            return False
        return value is None or found == value

    def data_get(self, key: str, default: Any = None) -> Any:
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

    def __contains__(self, key: object) -> bool:
        return isinstance(self.data, dict) and key in self.data

    def __getitem__(self, key: str) -> Any:
        if isinstance(self.data, dict):
            return self.data[key]
        raise KeyError(key)

    def query(self, key: str | None = None, default: Any = None) -> Any:
        qs = parse_qs(urlsplit(self.url).query, keep_blank_values=True)
        if key is None:
            return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
        if key not in qs:
            return default
        values = qs[key]
        return values[0] if len(values) == 1 else values

    def is_json(self) -> bool:
        return "json" in self._content_type()

    def is_form(self) -> bool:
        return "application/x-www-form-urlencoded" in self._content_type()

    def is_multipart(self) -> bool:
        return "multipart/form-data" in self._content_type() or bool(self.files)

    def has_file(self, name: str | None = None) -> bool:
        if not self.files:
            return False
        return name is None or name in self.files

    def _content_type(self) -> str:
        return (self.header("Content-Type") or "").lower()
