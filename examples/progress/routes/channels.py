"""Broadcast channels — who may listen to what (M26).

Every private channel a client asks for is matched against these patterns.
A pattern nobody registered is refused, so a new channel is private until
somebody says otherwise.
"""

from app.broadcasting.post_channel import PostChannel

from almasix.broadcasting import Broadcast

# A class handles the pattern: `join()` gets the user and the bound Post.
Broadcast.channel("posts.{post}", PostChannel)


@Broadcast.channel("authors.{name}")
def author_channel(user, name):
    """An author hears about their own posts."""
    return user.name == name


@Broadcast.channel("comments.{kind}.{id}")
def comment_thread(user, kind, id):  # noqa: A002 — the channel segment is called id
    """Anyone signed in may follow a comment thread."""
    del kind, id
    return user is not None


@Broadcast.channel("rooms.{room}")
def room(user, room):
    """A presence channel: the dict becomes what other members see."""
    del room
    return {"id": user.get_key(), "name": user.name}
