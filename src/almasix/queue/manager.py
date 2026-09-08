"""Queue manager — resolves named connections from config."""

from __future__ import annotations

from typing import Any

from almasix.queue.connections.database import DatabaseQueue
from almasix.queue.connections.sync import SyncQueue


class QueueManager:
    """Queue connection manager."""

    def __init__(self, app: Any | None = None, config: dict[str, Any] | None = None) -> None:
        self.app = app
        self._config = config or {}
        self._connections: dict[str, Any] = {}

    def set_config(self, config: dict[str, Any]) -> None:
        self._config = config
        self._connections.clear()

    def get_default_connection(self) -> str:
        return str(self._config.get("default") or "sync")

    def connection(self, name: str | None = None) -> Any:
        key = name or self.get_default_connection()
        if key not in self._connections:
            self._connections[key] = self._resolve(key)
        return self._connections[key]

    def failed_config(self) -> dict[str, Any]:
        return dict(self._config.get("failed") or {})

    def _connection_config(self, name: str) -> dict[str, Any]:
        connections = self._config.get("connections") or {}
        cfg = connections.get(name)
        if cfg is None:
            raise KeyError(f"Queue connection [{name}] is not configured.")
        return dict(cfg)

    def _resolve(self, name: str) -> Any:
        cfg = self._connection_config(name)
        driver = str(cfg.get("driver") or "sync")
        if driver == "sync":
            return SyncQueue(self.app, cfg, manager=self)
        if driver == "database":
            return DatabaseQueue(self.app, cfg, manager=self, connection_name=name)
        if driver == "redis":
            from almasix.queue.connections.redis import RedisQueue

            return RedisQueue(self.app, cfg, manager=self, connection_name=name)
        raise ValueError(f"Unsupported queue driver: {driver!r}")
