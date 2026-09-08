"""The client a test makes requests with.

Laravel's HTTP tests call `$this->get('/')`; Almasix's are coroutines, because
every request this framework serves is one. The client drives the application's
own ASGI app in-process — no socket, no server, the real middleware stack.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from almasix.testing.response import TestResponse

#: The host a test request appears to come from.
BASE_URL = "http://localhost"


class TestClient:
    """An in-process HTTP client for one application.

    Cookies persist between requests, so a login in one call is still a login
    in the next. Headers set with `with_headers` / `acting_as` persist too,
    until `flush_headers()`.
    """

    #: Named `Test*` after Laravel, so tell pytest not to collect it.
    __test__ = False

    def __init__(self, app: Any, *, base_url: str = BASE_URL) -> None:
        self.app = app
        self.base_url = base_url
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}
        self.follow_redirects = False
        #: Session data seeded into the next request (Laravel `withSession`).
        self.session: dict[str, Any] = {}
        self._asgi = app.asgi if hasattr(app, "asgi") else app

    # --- shaping the request -------------------------------------------------

    def with_headers(self, headers: Mapping[str, str]) -> TestClient:
        self.headers.update({str(key): str(value) for key, value in headers.items()})
        return self

    def with_header(self, name: str, value: str) -> TestClient:
        return self.with_headers({name: value})

    def with_token(self, token: str, kind: str = "Bearer") -> TestClient:
        return self.with_header("Authorization", f"{kind} {token}".strip())

    def with_basic_auth(self, username: str, password: str) -> TestClient:
        import base64

        raw = base64.b64encode(f"{username}:{password}".encode()).decode()
        return self.with_header("Authorization", f"Basic {raw}")

    def without_token(self) -> TestClient:
        self.headers.pop("Authorization", None)
        return self

    def flush_headers(self) -> TestClient:
        self.headers.clear()
        return self

    def with_cookie(self, name: str, value: str) -> TestClient:
        self.cookies[name] = value
        return self

    def with_cookies(self, cookies: Mapping[str, str]) -> TestClient:
        self.cookies.update({str(key): str(value) for key, value in cookies.items()})
        return self

    def with_session(self, data: Mapping[str, Any]) -> TestClient:
        """Seed the session the next request starts with."""
        self.session.update(dict(data))
        self._write_session_cookie()
        return self

    def flush_session(self) -> TestClient:
        self.session.clear()
        cookie = _session_cookie_name()
        self.cookies.pop(cookie, None)
        return self

    def acting_as(self, user: Any, guard: str = "web") -> TestClient:
        """Sign a user in for every request this client makes."""
        from almasix.auth.guard import session_payload_for

        return self.with_session({f"login_{guard}": session_payload_for(user)})

    def following_redirects(self, follow: bool = True) -> TestClient:
        self.follow_redirects = follow
        return self

    def from_(self, url: str) -> TestClient:
        """Where the request came from (Laravel `from()`), for redirect-back."""
        return self.with_header("Referer", url)

    # --- making the request ----------------------------------------------------

    async def get(self, uri: str, **kwargs: Any) -> TestResponse:
        return await self.request("GET", uri, **kwargs)

    async def post(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.request("POST", uri, data=data, **kwargs)

    async def put(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.request("PUT", uri, data=data, **kwargs)

    async def patch(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.request("PATCH", uri, data=data, **kwargs)

    async def delete(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.request("DELETE", uri, data=data, **kwargs)

    async def options(self, uri: str, **kwargs: Any) -> TestResponse:
        return await self.request("OPTIONS", uri, **kwargs)

    async def head(self, uri: str, **kwargs: Any) -> TestResponse:
        return await self.request("HEAD", uri, **kwargs)

    async def get_json(self, uri: str, **kwargs: Any) -> TestResponse:
        return await self.json("GET", uri, **kwargs)

    async def post_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.json("POST", uri, data=data, **kwargs)

    async def put_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.json("PUT", uri, data=data, **kwargs)

    async def patch_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.json("PATCH", uri, data=data, **kwargs)

    async def delete_json(self, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        return await self.json("DELETE", uri, data=data, **kwargs)

    async def json(self, method: str, uri: str, data: Any = None, **kwargs: Any) -> TestResponse:
        """A request that both sends and expects JSON."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        headers.update(dict(kwargs.pop("headers", {}) or {}))
        return await self.request(method, uri, json=data, headers=headers, **kwargs)

    async def request(
        self,
        method: str,
        uri: str,
        *,
        data: Any = None,
        json: Any = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        files: Any = None,
        follow_redirects: bool | None = None,
    ) -> TestResponse:
        from almasix.prism.engine import record_renders, stop_recording_renders
        from almasix.session.store import last_session

        sent_headers = {**self.headers, **dict(headers or {})}
        sent_cookies = {**self.cookies, **dict(cookies or {})}
        views = record_renders()
        try:
            transport = httpx.ASGITransport(app=self._asgi)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                cookies=sent_cookies,
                follow_redirects=(
                    self.follow_redirects if follow_redirects is None else follow_redirects
                ),
            ) as client:
                response = await client.request(
                    method.upper(),
                    uri,
                    data=data if json is None and not _is_body(data) else None,
                    content=data if json is None and _is_body(data) else None,
                    json=json,
                    params=dict(params or {}),
                    headers=sent_headers,
                    files=files,
                )
        finally:
            stop_recording_renders()

        self._remember_cookies(response)
        session = last_session()
        return TestResponse(
            response,
            session=session.all() if session is not None else {},
            views=views,
        )

    # --- internals -----------------------------------------------------------

    def _remember_cookies(self, response: httpx.Response) -> None:
        for name, value in response.cookies.items():
            self.cookies[name] = value

    def _write_session_cookie(self) -> None:
        """Hand the seeded session to the app the way a browser would."""
        from almasix.config import config
        from almasix.session.signing import sign_payload

        key = str(config("app.key", "") or "") or "almasix-insecure-dev-key-change-me"
        lifetime = int(config("session.lifetime", 120) or 120) * 60
        self.cookies[_session_cookie_name()] = sign_payload(
            dict(self.session), key=key, max_age=lifetime
        )

    def __repr__(self) -> str:
        return f"TestClient({self.base_url})"


def _session_cookie_name() -> str:
    from almasix.config import config

    return str(config("session.cookie", "almasix_session") or "almasix_session")


def _is_body(data: Any) -> bool:
    """Form fields go as a form; a string or bytes goes as the body."""
    return isinstance(data, (str, bytes, bytearray))
