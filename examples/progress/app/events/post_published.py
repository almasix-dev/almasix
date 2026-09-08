"""PostPublished — M26: an event that leaves the server."""

from __future__ import annotations

from almasix.broadcasting import Channel, InteractsWithSockets, PrivateChannel, ShouldBroadcast
from almasix.broadcasting.events import InteractsWithBroadcasting


class PostPublished(ShouldBroadcast, InteractsWithSockets, InteractsWithBroadcasting):
    """A post went live.

    Two channels: everyone hears the announcement, and the author's own
    private channel hears it too. `to_others()` on the pending broadcast is
    what keeps the author's own browser from being told what it just did.
    """

    def __init__(self, post_id: int, title: str, author: str) -> None:
        self.post_id = post_id
        self.title = title
        self.author = author

    def broadcast_on(self) -> list[Channel]:
        return [Channel("announcements"), PrivateChannel(f"authors.{self.author}")]

    def broadcast_as(self) -> str:
        return "post.published"

    def broadcast_with(self) -> dict[str, object]:
        return {"id": self.post_id, "title": self.title}
