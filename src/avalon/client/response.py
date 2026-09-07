"""HTTP client response wrapper."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from avalon.client.exceptions import RequestException
from avalon.support.collection import Collection


class Response:
    """Laravel-shaped HTTP client response."""

    def __init__(
        self,
        status_code: int = 200,
        body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
        url: str = "",
        reason: str = "",
        request: Any = None,
    ) -> None:
        if body is None:
            raw = b""
        elif isinstance(body, bytes):
            raw = body
        elif isinstance(body, str):
            raw = body.encode("utf-8")
        else:
            raw = json.dumps(body).encode("utf-8")
        self._status = int(status_code)
        self._body = raw
        self._headers = {str(k): str(v) for k, v in (headers or {}).items()}
        self._cookies = dict(cookies or {})
        self._url = url
        self._reason = reason
        self._request = request
        self._json: Any = _UNSET

    @classmethod
    def make(
        cls,
        body: Any = None,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> Response:
        hdrs = dict(headers or {})
        raw: bytes | str | None
        if body is None:
            raw = b""
        elif isinstance(body, (dict, list)):
            raw = json.dumps(body)
            hdrs.setdefault("Content-Type", "application/json")
        else:
            raw = body
        return cls(status_code=status, body=raw, headers=hdrs)

    @classmethod
    def from_httpx(cls, response: Any, request: Any = None) -> Response:
        cookies: dict[str, str] = {}
        jar = getattr(response, "cookies", None)
        if jar is not None:
            try:
                cookies = dict(jar)
            except (TypeError, ValueError):
                cookies = {}
        headers = {k: v for k, v in response.headers.items()}
        return cls(
            status_code=response.status_code,
            body=response.content,
            headers=headers,
            cookies=cookies,
            url=str(response.url),
            reason=getattr(response, "reason_phrase", "") or "",
            request=request,
        )

    def with_request(self, request: Any) -> Response:
        """Copy tagged with the request that produced it (fake stubs are reused)."""
        clone = copy.copy(self)
        clone._request = request
        clone._url = self._url or getattr(request, "url", "")
        return clone

    def body(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def content(self) -> bytes:
        return self._body

    def json(self, key: str | None = None, default: Any = None) -> Any:
        if self._json is _UNSET:
            text = self.body()
            if not text.strip():
                self._json = None
            else:
                try:
                    self._json = json.loads(text)
                except json.JSONDecodeError:
                    self._json = None
        data = self._json
        if key is None:
            return data
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    def object(self) -> Any:
        data = self.json()
        if isinstance(data, dict):
            return SimpleNamespace(**data)
        if isinstance(data, list):
            return [SimpleNamespace(**item) if isinstance(item, dict) else item for item in data]
        return data

    def collect(self) -> Collection:
        data = self.json()
        if data is None:
            return Collection([])
        return Collection(data)

    def status(self) -> int:
        return self._status

    def reason(self) -> str:
        return self._reason

    def url(self) -> str:
        return self._url

    def effective_uri(self) -> str:
        return self._url

    def header(self, key: str, default: str | None = None) -> str | None:
        lower = key.lower()
        for name, value in self._headers.items():
            if name.lower() == lower:
                return value
        return default

    def headers(self) -> dict[str, str]:
        return dict(self._headers)

    def cookies(self) -> dict[str, str]:
        return dict(self._cookies)

    def ok(self) -> bool:
        return 200 <= self._status < 300

    def successful(self) -> bool:
        return self.ok()

    def redirect(self) -> bool:
        return 300 <= self._status < 400

    def failed(self) -> bool:
        return self.client_error() or self.server_error()

    def client_error(self) -> bool:
        return 400 <= self._status < 500

    def server_error(self) -> bool:
        return 500 <= self._status < 600

    def unauthorized(self) -> bool:
        return self._status == 401

    def forbidden(self) -> bool:
        return self._status == 403

    def not_found(self) -> bool:
        return self._status == 404

    def gone(self) -> bool:
        return self._status == 410

    def too_many_requests(self) -> bool:
        return self._status == 429

    def created(self) -> bool:
        return self._status == 201

    def accepted(self) -> bool:
        return self._status == 202

    def no_content(self) -> bool:
        return self._status == 204

    def on_error(self, callback: Callable[[Response], Any]) -> Response:
        if self.failed():
            callback(self)
        return self

    def throw(self, callback: Callable[[Response], Any] | None = None) -> Response:
        if self.failed():
            if callback is not None:
                callback(self)
            raise RequestException(self)
        return self

    def throw_if(self, condition: bool | Callable[[Response], bool]) -> Response:
        should = condition(self) if callable(condition) else bool(condition)
        if should:
            return self.throw()
        return self

    def throw_unless(self, condition: bool | Callable[[Response], bool]) -> Response:
        should = condition(self) if callable(condition) else bool(condition)
        if not should:
            return self.throw()
        return self

    def throw_if_status(self, status: int | Callable[[int], bool]) -> Response:
        match = status(self._status) if callable(status) else self._status == status
        if match:
            raise RequestException(self)
        return self

    def throw_unless_status(self, status: int) -> Response:
        if self._status != status:
            raise RequestException(self)
        return self

    def request(self) -> Any:
        return self._request

    def __bool__(self) -> bool:
        return self.successful()

    def __getitem__(self, key: str) -> Any:
        data = self.json()
        if isinstance(data, dict):
            return data[key]
        raise KeyError(key)

    def __contains__(self, key: object) -> bool:
        data = self.json()
        return isinstance(data, dict) and key in data

    def __repr__(self) -> str:
        return f"<Response {self._status} {self._url}>"


_UNSET = object()
