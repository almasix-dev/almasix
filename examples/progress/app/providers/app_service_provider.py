"""Application service provider."""

from __future__ import annotations

from avalon.providers import ServiceProvider


class AppServiceProvider(ServiceProvider):
    """Application service provider."""

    def register(self) -> None:
        """Bind application services into the container."""

    def boot(self) -> None:
        """Bootstrap application services."""
        from app.models.post import Post
        from app.policies.post_policy import PostPolicy

        from avalon.auth import Gate

        Gate.policy(Post, PostPolicy)
