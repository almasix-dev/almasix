"""Redis connection manager."""

from __future__ import annotations

from typing import Any


def require_redis() -> Any:
    """Import ``redis.asyncio`` or raise an install hint."""
    try:
        import redis.asyncio as redis_async
    except ImportError as exc:  # pragma: no cover - exercised when redis absent
        raise RuntimeError(
            "Redis support requires the redis package. Install with: pip install 'almasix[redis]'"
        ) from exc
    return redis_async


class RedisManager:
    """Resolve named Redis connections from ``config/redis``."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self.config = dict(config or {})
        self._clients: dict[str, Any] = {}

    def get_default_connection(self) -> str:
        return str(self.config.get("default") or "default")

    def set_default_connection(self, name: str) -> None:
        self.config["default"] = name

    def connection(self, name: str | None = None) -> Any:
        """Return an async Redis client for ``name``."""
        key = name or self.get_default_connection()
        if key not in self._clients:
            self._clients[key] = self._create_client(key)
        return self._clients[key]

    def set_client(self, name: str, client: Any) -> None:
        """Inject a client (tests / fakes)."""
        self._clients[name] = client

    def forget_clients(self) -> None:
        self._clients.clear()

    def _connection_config(self, name: str) -> dict[str, Any]:
        connections = self.config.get("connections") or {}
        cfg = connections.get(name)
        if cfg is None:
            raise KeyError(f"Redis connection [{name}] is not configured.")
        return dict(cfg)

    def _create_client(self, name: str) -> Any:
        cfg = self._connection_config(name)
        redis_async = require_redis()
        url = cfg.get("url")
        if url:
            return redis_async.from_url(str(url), decode_responses=False)

        host = str(cfg.get("host") or "127.0.0.1")
        port = int(cfg.get("port") or 6379)
        db = int(cfg.get("database") if cfg.get("database") is not None else cfg.get("db") or 0)
        password = cfg.get("password")
        username = cfg.get("username")
        kwargs: dict[str, Any] = {
            "host": host,
            "port": port,
            "db": db,
            "decode_responses": False,
        }
        if password:
            kwargs["password"] = password
        if username:
            kwargs["username"] = username
        return redis_async.Redis(**kwargs)
