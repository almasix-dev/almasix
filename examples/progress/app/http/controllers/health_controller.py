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

    async def me(self) -> dict:
        from almasix.auth import auth

        user = auth().user()
        if user is None:
            return {"user": None}
        if hasattr(user, "to_dict"):
            return {"user": user.to_dict()}
        if isinstance(user, dict):
            return {"user": {k: v for k, v in user.items() if k != "password"}}
        return {"user": {"id": getattr(user, "id", None)}}
