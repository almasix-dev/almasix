"""Post resources — conditional attributes, relationships, and collection meta."""

from __future__ import annotations

from typing import Any

from almasix.http.resources import JsonResource, ResourceCollection


class AuthorResource(JsonResource):
    """The slice of a user an API client is allowed to see."""

    def to_dict(self, request: Any = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
        }


class PostResource(JsonResource):
    """One post, shaped for the API."""

    def to_dict(self, request: Any = None) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "published": self.published,
            # Only present when the caller eager loaded the relation, so a
            # resource can never cause an N+1.
            "author": self.when_loaded("author", lambda author: AuthorResource(author)),
            "comments_count": self.when_counted("comments"),
            # Only present for posts anybody actually read.
            "views": self.when(self.views > 0, lambda: self.views),
            "admin": self.merge_when(
                bool(request and request.query("admin")),
                {"user_id": self.user_id, "trashed": self.trashed()},
            ),
        }


class PostCollection(ResourceCollection):
    """Many posts, plus metadata about the set."""

    collects = PostResource

    def with_(self, request: Any = None) -> dict[str, Any]:
        return {"meta_extra": {"published_only": True}}
