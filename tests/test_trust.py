"""Trusted proxies / hosts unit coverage."""

from __future__ import annotations

import pytest

from almasix.http.trust import (
    HEADER_X_FORWARDED_ALL,
    HEADER_X_FORWARDED_FOR,
    HEADER_X_FORWARDED_HOST,
    HEADER_X_FORWARDED_PORT,
    HEADER_X_FORWARDED_PREFIX,
    HEADER_X_FORWARDED_PROTO,
    TrustProxiesASGI,
    host_is_trusted,
    normalize_hosts,
    normalize_proxies,
    peer_is_trusted,
)


def test_normalize_proxies_and_hosts() -> None:
    assert normalize_proxies(None) == []
    assert normalize_proxies("*") == "*"
    assert normalize_proxies("0.0.0.0/0") == "*"
    assert normalize_proxies("10.0.0.1") == ["10.0.0.1"]
    assert normalize_proxies(["10.0.0.0/8", "192.168.1.1"]) == [
        "10.0.0.0/8",
        "192.168.1.1",
    ]
    assert normalize_proxies(["*", "10.0.0.1"]) == "*"
    with pytest.raises(TypeError):
        normalize_proxies(123)

    assert normalize_hosts(None) == []
    assert normalize_hosts("app.test") == ["app.test"]
    assert normalize_hosts("  ") == []
    assert normalize_hosts(["a.test", "", "b.test"]) == ["a.test", "b.test"]
    assert normalize_hosts(lambda: ["x.test"]) == ["x.test"]
    with pytest.raises(TypeError):
        normalize_hosts(3.14)


def test_peer_and_host_trust_rules() -> None:
    assert peer_is_trusted("1.2.3.4", None) is False
    assert peer_is_trusted("1.2.3.4", "*") is True
    assert peer_is_trusted(None, ["1.2.3.4"]) is False
    assert peer_is_trusted("1.2.3.4", ["1.2.3.4"]) is True
    assert peer_is_trusted("10.0.0.5", ["10.0.0.0/8"]) is True
    assert peer_is_trusted("11.0.0.5", ["10.0.0.0/8"]) is False
    assert peer_is_trusted("proxy.local", ["proxy.local"]) is True
    assert peer_is_trusted("1.2.3.4", ["not-a-cidr"]) is False

    assert host_is_trusted("app.test", []) is True
    assert host_is_trusted(None, ["app.test"]) is False
    assert host_is_trusted("app.test:443", ["app.test"]) is True
    assert host_is_trusted("demo.almasix.dev", ["*.almasix.dev"]) is True
    assert host_is_trusted("almasix.dev", ["*.almasix.dev"]) is True
    assert host_is_trusted("evil.test", ["*.almasix.dev"]) is False
    assert host_is_trusted("x.test", ["", "x.test"]) is True


@pytest.mark.asyncio
async def test_trust_proxies_asgi_rewrites_all_headers() -> None:
    seen: dict[str, object] = {}

    async def app(scope, receive, send):
        seen.update(
            {
                "client": scope.get("client"),
                "scheme": scope.get("scheme"),
                "server": scope.get("server"),
                "root_path": scope.get("root_path"),
                "host": dict(scope.get("headers", [])).get(b"host"),
            }
        )

    middleware = TrustProxiesASGI(app, proxies="*", headers=HEADER_X_FORWARDED_ALL)
    scope = {
        "type": "http",
        "client": ("127.0.0.1", 9),
        "scheme": "http",
        "server": ("127.0.0.1", 80),
        "headers": [
            (b"x-forwarded-for", b"203.0.113.9, 10.0.0.1"),
            (b"x-forwarded-proto", b"https"),
            (b"x-forwarded-host", b"app.example"),
            (b"x-forwarded-port", b"8443"),
            (b"x-forwarded-prefix", b"/almasix/"),
            (b"host", b"127.0.0.1"),
        ],
    }
    await middleware(scope, None, None)
    assert seen["client"] == ("203.0.113.9", 9)
    assert seen["scheme"] == "https"
    assert seen["server"] == ("127.0.0.1", 8443)
    assert seen["root_path"] == "/almasix"
    assert seen["host"] == b"app.example"

    # Untrusted peer — no rewrite
    seen.clear()
    guarded = TrustProxiesASGI(app, proxies=["10.0.0.1"], headers=HEADER_X_FORWARDED_FOR)
    await guarded(
        {
            "type": "http",
            "client": ("127.0.0.1", 1),
            "headers": [(b"x-forwarded-for", b"9.9.9.9")],
        },
        None,
        None,
    )
    assert seen["client"] == ("127.0.0.1", 1)

    # Non-http scope passes through
    seen.clear()

    async def mark(scope, receive, send):
        seen["ok"] = True

    await TrustProxiesASGI(mark, proxies="*", headers=HEADER_X_FORWARDED_FOR)(
        {"type": "lifespan"}, None, None
    )
    assert seen["ok"] is True


def test_header_bitmask_constants() -> None:
    assert HEADER_X_FORWARDED_FOR | HEADER_X_FORWARDED_PROTO
    assert HEADER_X_FORWARDED_HOST & HEADER_X_FORWARDED_ALL
    assert HEADER_X_FORWARDED_PORT
    assert HEADER_X_FORWARDED_PREFIX
