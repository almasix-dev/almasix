"""Trusted proxies / hosts — Laravel TrustProxies + TrustHosts parity."""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from almasix.http.exceptions import BadRequestHttpException
from almasix.http.middleware import Middleware
from almasix.http.request import Request

# Laravel ``Request::HEADER_X_FORWARDED_*`` bitmasks.
HEADER_X_FORWARDED_FOR = 0b00001
HEADER_X_FORWARDED_HOST = 0b00010
HEADER_X_FORWARDED_PORT = 0b00100
HEADER_X_FORWARDED_PROTO = 0b01000
HEADER_X_FORWARDED_PREFIX = 0b10000
HEADER_X_FORWARDED_AWS_ELB = (
    HEADER_X_FORWARDED_FOR | HEADER_X_FORWARDED_PORT | HEADER_X_FORWARDED_PROTO
)
HEADER_X_FORWARDED_ALL = (
    HEADER_X_FORWARDED_FOR
    | HEADER_X_FORWARDED_HOST
    | HEADER_X_FORWARDED_PORT
    | HEADER_X_FORWARDED_PROTO
    | HEADER_X_FORWARDED_PREFIX
)

_TRUST_ALL = frozenset({"*", "0.0.0.0/0", "::/0"})


def normalize_proxies(at: Any) -> list[str] | str:
    """Normalize ``trust_proxies(at=…)`` into ``*`` or a list of peer specs."""
    if at is None:
        return []
    if isinstance(at, str):
        return "*" if at.strip() in _TRUST_ALL else [at.strip()]
    if isinstance(at, Sequence) and not isinstance(at, (str, bytes)):
        values = [str(item).strip() for item in at if str(item).strip()]
        if any(value in _TRUST_ALL for value in values):
            return "*"
        return values
    raise TypeError("trust_proxies(at=…) expects '*', an IP/CIDR, or a sequence of them")


def normalize_hosts(at: Any) -> list[str]:
    if at is None:
        return []
    if callable(at):
        at = at()
    if isinstance(at, str):
        return [at.strip()] if at.strip() else []
    if isinstance(at, Sequence) and not isinstance(at, (str, bytes)):
        return [str(item).strip() for item in at if str(item).strip()]
    raise TypeError("trust_hosts(at=…) expects a host, list of hosts, or callable")


def peer_is_trusted(peer: str | None, proxies: list[str] | str | None) -> bool:
    if not proxies:
        return False
    if proxies == "*":
        return True
    if not peer:
        return False
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return peer in proxies
    for spec in proxies:
        try:
            if "/" in spec:
                if address in ipaddress.ip_network(spec, strict=False):
                    return True
            elif address == ipaddress.ip_address(spec):
                return True
        except ValueError:
            if peer == spec:  # pragma: no cover — peer is a valid IP; cannot equal a failing spec
                return True
    return False


def host_is_trusted(host: str | None, patterns: Sequence[str]) -> bool:
    if not patterns:
        return True
    if not host:
        return False
    hostname = host.split(":")[0].strip().lower()
    for pattern in patterns:
        needle = pattern.strip().lower()
        if not needle:
            continue
        if needle.startswith("*."):
            suffix = needle[1:]  # ".example.com"
            if hostname.endswith(suffix) or hostname == needle[2:]:
                return True
        elif hostname == needle:
            return True
    return False


class TrustProxiesASGI:
    """ASGI middleware — rewrite client/scheme/host from X-Forwarded-* when peer is trusted."""

    def __init__(self, app: Any, *, proxies: list[str] | str, headers: int) -> None:
        self.app = app
        self.proxies = proxies
        self.headers = headers

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http" and peer_is_trusted(_scope_peer(scope), self.proxies):
            scope = dict(scope)
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            self._apply(scope, headers)
        await self.app(scope, receive, send)

    def _apply(self, scope: dict[str, Any], headers: dict[str, str]) -> None:
        if self.headers & HEADER_X_FORWARDED_FOR:
            forwarded = headers.get("x-forwarded-for")
            if forwarded:
                client = forwarded.split(",")[0].strip()
                if client:
                    port = 0
                    if scope.get("client"):
                        port = int(scope["client"][1])
                    scope["client"] = (client, port)

        if self.headers & HEADER_X_FORWARDED_PROTO:
            proto = (headers.get("x-forwarded-proto") or "").split(",")[0].strip()
            if proto in {"http", "https"}:
                scope["scheme"] = proto

        if self.headers & HEADER_X_FORWARDED_HOST:
            host = (headers.get("x-forwarded-host") or "").split(",")[0].strip()
            if host:
                _set_header(scope, b"host", host.encode("latin-1"))

        if self.headers & HEADER_X_FORWARDED_PORT:
            port = (headers.get("x-forwarded-port") or "").split(",")[0].strip()
            if port.isdigit():
                # Prefer proto+host; Starlette reads server from scope.
                server_host = scope.get("server", ("", 0))[0]
                scope["server"] = (server_host, int(port))

        if self.headers & HEADER_X_FORWARDED_PREFIX:
            prefix = (headers.get("x-forwarded-prefix") or "").split(",")[0].strip()
            if prefix:
                scope["root_path"] = prefix.rstrip("/")


class TrustHosts(Middleware):
    """Reject requests whose Host header is not in the trusted list."""

    async def handle(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        from almasix.config import config

        patterns = list(config("http.trusted_hosts", []) or [])
        host = request.header("host")
        if not host_is_trusted(host, patterns):
            raise BadRequestHttpException("Invalid Host header.")
        return await call_next(request)


def _scope_peer(scope: dict[str, Any]) -> str | None:
    client = scope.get("client")
    if client and client[0]:
        return str(client[0])
    return None


def _set_header(scope: dict[str, Any], name: bytes, value: bytes) -> None:
    headers = [(key, val) for key, val in scope.get("headers", []) if key.lower() != name.lower()]
    headers.append((name, value))
    scope["headers"] = headers
