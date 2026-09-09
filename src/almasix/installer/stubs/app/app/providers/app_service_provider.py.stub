"""Application service provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from almasix.providers import ServiceProvider

if TYPE_CHECKING:
    from almasix.http.request import Request


class AppServiceProvider(ServiceProvider):
    """Application service provider."""

    def register(self) -> None:
        """Bind application services into the container."""

    def boot(self) -> None:
        """Bootstrap application services."""
        from almasix.http import Limit, RateLimiter

        RateLimiter.for_(
            "api",
            lambda request: Limit.per_minute(60).by(_throttle_key(request)),
        )


def _throttle_key(request: Request) -> str:
    user = getattr(request, "user", None)
    if callable(user):
        user = user()
    if user is not None and getattr(user, "id", None) is not None:
        return f"user:{user.id}"
    return str(request.ip() or "0.0.0.0")
