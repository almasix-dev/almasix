"""Health controller — API routes return JSON."""

from __future__ import annotations

from almasix.config import config
from almasix.http import Controller


class HealthController(Controller):
    """Health check — JSON status for API routes."""

    async def index(self) -> dict[str, str]:
        return {
            "status": "ok",
            "app": str(config("app.name", "Almasix")),
            "env": str(config("app.env", "local")),
        }
