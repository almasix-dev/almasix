"""Request wrapper — Laravel-flavored façade over Starlette/FastAPI."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextvars import ContextVar, Token
from typing import Any

from starlette.datastructures import UploadFile
from starlette.requests import Request as StarletteRequest

from almasix.http.spoofing import REAL_METHOD

_current: ContextVar[Request | None] = ContextVar("almasix_request", default=None)


class UploadedFile:
    """App-facing uploaded file (hides Starlette ``UploadFile``)."""

    def __init__(self, upload: UploadFile) -> None:
        self._upload = upload

    @property
    def raw(self) -> UploadFile:
        return self._upload

    @property
    def name(self) -> str | None:
        return self._upload.filename

    @property
    def filename(self) -> str | None:
        return self._upload.filename

    @property
    def content_type(self) -> str | None:
        return self._upload.content_type

    @property
    def size(self) -> int | None:
        return getattr(self._upload, "size", None)

    async def read(self, size: int = -1) -> bytes:
        return await self._upload.read(size)

    async def seek(self, offset: int) -> None:
        await self._upload.seek(offset)

    async def store(
        self,
        path: str = "",
        *,
        disk: str | None = None,
        visibility: str | None = None,
    ) -> str:
        """Store on a filesystem disk (Laravel ``UploadedFile::store``)."""
        from almasix.filesystem import Storage

        return await Storage.disk(disk).put_file_async(path, self, visibility=visibility)

    async def store_as(
        self,
        path: str,
        name: str,
        *,
        disk: str | None = None,
        visibility: str | None = None,
    ) -> str:
        """Store under an explicit filename (Laravel ``UploadedFile::storeAs``)."""
        from almasix.filesystem import Storage

        target = f"{path.rstrip('/')}/{name}" if path else name
        data = await self.read()
        return Storage.disk(disk).put(target, data, visibility=visibility)


class Request:
    """Laravel-flavored HTTP request.

    Input bag semantics match Laravel:

    - ``all()`` / ``input()`` — query string **merged with** body (body wins)
    - ``query()`` — query string only
    - ``post()`` — body only (JSON object or form fields)
    - ``route()`` — path/route parameters (not in ``all()``)
    - files via ``file()`` / ``files()`` / ``has_file()``
    """

    def __init__(
        self,
        request: StarletteRequest,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        json_data: Any = None,
        files: Mapping[str, UploadedFile | list[UploadedFile]] | None = None,
        hydrated: bool = False,
    ) -> None:
        self._request = request
        self._query: dict[str, Any] = dict(query or {})
        self._body: dict[str, Any] = dict(body or {})
        self._json: Any = json_data
        self._files: dict[str, UploadedFile | list[UploadedFile]] = dict(files or {})
        self._input: dict[str, Any] = {**self._query, **self._body}
        self._hydrated = hydrated
        self._session: Any = None
        self._cookies: dict[str, str] | None = None
        self._auth: Any = None
        self._csrf_token: str | None = None
        self._route_polarity: str | None = None
        self._route_name: str | None = None
        self._matched_route: Any = None
        self._spoofed_method: str | None = None
        self._extra_path_params: dict[str, Any] = {}

    @classmethod
    async def create(cls, request: StarletteRequest) -> Request:
        """Build a request with query/body/files hydrated (call once per request)."""
        instance = cls(request)
        await instance._hydrate()
        return instance

    async def _hydrate(self) -> None:
        if self._hydrated:
            return

        self._query = _flatten_multi(self._request.query_params.multi_items())
        self._body = {}
        self._files = {}
        self._json = None

        content_type = (self._request.headers.get("content-type") or "").lower()
        mime = content_type.split(";")[0].strip()
        if mime == "application/json" or mime.endswith("+json"):
            try:
                payload = await self._request.json()
            except Exception:
                payload = None
            self._json = payload
            if isinstance(payload, dict):
                self._body = dict(payload)
        elif (
            "multipart/form-data" in content_type
            or "application/x-www-form-urlencoded" in content_type
        ):
            form = await self._request.form()
            body: dict[str, Any] = {}
            files: dict[str, UploadedFile | list[UploadedFile]] = {}
            for key, value in form.multi_items():
                if isinstance(value, UploadFile):
                    wrapped = UploadedFile(value)
                    existing = files.get(key)
                    if existing is None:
                        files[key] = wrapped
                    elif isinstance(existing, list):
                        existing.append(wrapped)
                    else:
                        files[key] = [existing, wrapped]
                else:
                    if key in body:
                        current = body[key]
                        if isinstance(current, list):
                            current.append(value)
                        else:
                            body[key] = [current, value]
                    else:
                        body[key] = value
            self._body = body
            self._files = files

        self._input = {**self._query, **self._body}
        self._hydrated = True

    # --- identity / meta -------------------------------------------------

    @property
    def raw(self) -> StarletteRequest:
        return self._request

    @property
    def method(self) -> str:
        """The verb the request is treated as, `_method` spoofing included.

        Spoofing happens in ASGI middleware, before routing, so by the time a
        handler asks this the scope already says PUT. The `_spoofed_method`
        override exists for a test that wants to claim a verb by hand.
        """
        return self._spoofed_method or self._request.method

    @property
    def real_method(self) -> str:
        """The verb actually on the wire, whatever `_method` claimed."""
        real = self._request.scope.get(REAL_METHOD)
        return str(real) if real else self._request.method

    @property
    def spoofed_method(self) -> str | None:
        """The verb `_method` asked for, or `None` if nothing was spoofed."""
        if self._spoofed_method:
            return self._spoofed_method
        if self._request.scope.get(REAL_METHOD):
            return self._request.method
        return None

    @spoofed_method.setter
    def spoofed_method(self, value: str | None) -> None:
        self._spoofed_method = value.upper() if value else None

    @property
    def url(self) -> str:
        return str(self._request.url)

    @property
    def path(self) -> str:
        return self._request.url.path

    @property
    def route_polarity(self) -> str | None:
        """``web`` / ``api`` from the route group — used by the exception Handler."""
        return self._route_polarity

    @route_polarity.setter
    def route_polarity(self, value: str | None) -> None:
        self._route_polarity = value

    @property
    def route_name(self) -> str | None:
        return self._route_name

    @route_name.setter
    def route_name(self, value: str | None) -> None:
        self._route_name = value

    @property
    def headers(self) -> Any:
        return self._request.headers

    @property
    def cookies(self) -> Any:
        if self._cookies is not None:
            return self._cookies
        return self._request.cookies

    @property
    def session(self) -> Any:
        """Session bag when :class:`~almasix.session.StartSession` is in the stack."""
        if self._session is None:
            raise RuntimeError(
                "Session store not started. Add StartSession to the web middleware group."
            )
        return self._session

    @property
    def query_params(self) -> Any:
        """Raw Starlette query params (prefer ``query()`` in app code)."""
        return self._request.query_params

    @property
    def path_params(self) -> dict[str, Any]:
        return {**self._request.path_params, **self._extra_path_params}

    def merge_path_params(self, values: Mapping[str, Any]) -> None:
        """Add parameters Starlette did not route on — a `{subdomain}`, say."""
        self._extra_path_params.update(dict(values))

    @property
    def matched_route(self) -> Any:
        """The `RouteDefinition` answering this request, or ``None``."""
        return self._matched_route

    @matched_route.setter
    def matched_route(self, value: Any) -> None:
        self._matched_route = value

    def route_is(self, *patterns: str) -> bool:
        """Whether the matched route's name matches (Laravel ``routeIs``)."""
        route = self._matched_route
        return bool(route is not None and route.named(*patterns))

    def route_named(self, *patterns: str) -> bool:
        """`route_is` under Laravel's `$request->route()->named()` spelling."""
        return self.route_is(*patterns)

    def is_method(self, method: str) -> bool:
        return self.method.upper() == method.upper()

    def is_json(self) -> bool:
        content_type = (self._request.headers.get("content-type") or "").lower()
        return "json" in content_type

    def ip(self) -> str | None:
        if self._request.client is not None:
            return self._request.client.host
        return None

    def user_agent(self) -> str | None:
        return self.header("user-agent")

    def header(self, key: str, default: Any = None) -> Any:
        return self._request.headers.get(key, default)

    def cookie(self, key: str, default: Any = None) -> Any:
        if self._cookies is not None:
            return self._cookies.get(key, default)
        return self._request.cookies.get(key, default)

    def bearer_token(self) -> str | None:
        auth = self._request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip() or None
        return None

    def user(self, guard: str | None = None) -> Any:
        """Laravel ``$request->user($guard)`` — authenticated user for a guard."""
        manager = self._auth
        if manager is None:
            from almasix.auth.guard import get_auth

            manager = get_auth()
        if manager is None:
            return None
        if guard is None:
            return manager.user()
        return manager.guard(guard).user()

    # --- input bag (Laravel all / input / query / post) ------------------

    def all(self) -> dict[str, Any]:
        return dict(self._input)

    def input(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return self.all()
        return self._input.get(key, default)

    def get(self, key: str, default: Any = None) -> Any:
        return self.input(key, default)

    def query(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return dict(self._query)
        return self._query.get(key, default)

    def post(self, key: str | None = None, default: Any = None) -> Any:
        if key is None:
            return dict(self._body)
        return self._body.get(key, default)

    def json(self, key: str | None = None, default: Any = None) -> Any:
        """Return parsed JSON body (dict/list/…) or a key within a JSON object."""
        if key is None:
            return self._json
        if isinstance(self._json, dict):
            return self._json.get(key, default)
        return default

    def route(self, key: str | None = None, default: Any = None) -> Any:
        params = self.path_params
        if key is None:
            return params
        return params.get(key, default)

    def only(self, *keys: str | Iterable[str]) -> dict[str, Any]:
        resolved = _normalize_keys(keys)
        return {key: self._input[key] for key in resolved if key in self._input}

    def except_(self, *keys: str | Iterable[str]) -> dict[str, Any]:
        """Laravel ``except()`` — omit keys from the input bag."""
        excluded = set(_normalize_keys(keys))
        return {key: value for key, value in self._input.items() if key not in excluded}

    def keys(self) -> list[str]:
        return list(self._input.keys())

    def has(self, *keys: str) -> bool:
        return all(key in self._input for key in keys)

    def has_any(self, *keys: str) -> bool:
        return any(key in self._input for key in keys)

    def filled(self, *keys: str) -> bool:
        return all(not _is_empty(self._input.get(key)) for key in keys)

    def missing(self, key: str) -> bool:
        return key not in self._input

    def boolean(self, key: str, default: bool = False) -> bool:
        if key not in self._input:
            return default
        value = self._input[key]
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).lower() in {"1", "true", "on", "yes"}

    def integer(self, key: str, default: int = 0) -> int:
        if key not in self._input:
            return default
        try:
            return int(self._input[key])
        except (TypeError, ValueError):
            return default

    def float(self, key: str, default: float = 0.0) -> float:
        if key not in self._input:
            return default
        try:
            return float(self._input[key])
        except (TypeError, ValueError):
            return default

    def string(self, key: str, default: str = "") -> str:
        if key not in self._input or self._input[key] is None:
            return default
        return str(self._input[key])

    def merge(self, data: Mapping[str, Any]) -> Request:
        self._input.update(dict(data))
        self._body.update({k: v for k, v in data.items()})
        return self

    def replace(self, data: Mapping[str, Any]) -> Request:
        self._input = dict(data)
        self._body = dict(data)
        self._query = {}
        return self

    # --- files -----------------------------------------------------------

    def file(self, key: str, default: Any = None) -> UploadedFile | list[UploadedFile] | Any:
        return self._files.get(key, default)

    def files(self) -> dict[str, UploadedFile | list[UploadedFile]]:
        return dict(self._files)

    def has_file(self, key: str) -> bool:
        value = self._files.get(key)
        if value is None:
            return False
        if isinstance(value, list):
            return any(item.filename for item in value)
        return bool(value.filename)

    # --- mapping sugar ---------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        if key not in self._input:
            raise KeyError(key)
        return self._input[key]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self._input

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.path}>"


def get_request() -> Request | None:
    """Return the request being handled, or ``None`` outside a request."""
    return _current.get()


def set_request(request: Request | None) -> Token[Request | None]:
    return _current.set(request)


def reset_request(token: Token[Request | None]) -> None:
    _current.reset(token)


def _normalize_keys(keys: tuple[str | Iterable[str], ...]) -> list[str]:
    if len(keys) == 1 and not isinstance(keys[0], str):
        return list(keys[0])  # type: ignore[arg-type]
    return list(keys)  # type: ignore[arg-type]


def _flatten_multi(items: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            current = result[key]
            if isinstance(current, list):
                current.append(value)
            else:
                result[key] = [current, value]
        else:
            result[key] = value
    return result


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False
