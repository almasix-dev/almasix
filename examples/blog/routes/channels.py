"""Broadcast channels — who may listen to what."""

from almasix.broadcasting import Broadcast


@Broadcast.channel("users.{user_id}")
def user_channel(user, user_id):
    """A user may listen to their own channel, and nobody else's."""
    return str(user.get_key()) == str(user_id)
