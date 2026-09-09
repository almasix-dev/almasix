"""API routes — stateless, JSON responses."""

from app.http.controllers.health_controller import HealthController
from almasix.routing import Route

with Route.group(prefix="/api", middleware=["api"]):
    Route.get("/health", [HealthController, "index"])
