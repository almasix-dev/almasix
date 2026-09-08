"""Channels — the names a broadcast is addressed to.

A channel is a name plus a visibility. Public channels anyone may listen to;
private and presence channels have to be authorized first, and carry a prefix
so every broadcaster and every client agrees on which is which.
"""

from __future__ import annotations

from typing import Any


def model_channel_name(model: Any) -> str:
    """The channel a model names, Laravel's convention in Python spelling.

    Laravel turns `App\\Models\\User` with id 1 into `App.Models.User.1`; the
    same rule over a Python class gives `app.models.user.User.1`. A model may
    override `broadcast_channel()` when it wants something shorter.
    """
    override = getattr(model, "broadcast_channel", None)
    if callable(override):
        return str(override())
    return default_model_channel_name(model)


def default_model_channel_name(model: Any) -> str:
    """The convention itself, without asking the model what it prefers."""
    cls = type(model)
    key = model.get_key() if hasattr(model, "get_key") else getattr(model, "id", None)
    return f"{cls.__module__}.{cls.__name__}.{key}"


class Channel:
    """A public channel — anyone connected may listen."""

    prefix = ""

    def __init__(self, name: Any) -> None:
        self.name = name if isinstance(name, str) else model_channel_name(name)

    @property
    def full_name(self) -> str:
        """The name as it goes on the wire, prefix and all."""
        return f"{self.prefix}{self.name}"

    def __str__(self) -> str:
        return self.full_name

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Channel):
            return self.full_name == other.full_name
        return self.full_name == other

    def __hash__(self) -> int:
        return hash(self.full_name)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} {self.full_name!r}>"


class PrivateChannel(Channel):
    """Authorized before anyone may listen."""

    prefix = "private-"


class PresenceChannel(PrivateChannel):
    """Private, and everyone on it can see who else is there."""

    prefix = "presence-"


class EncryptedPrivateChannel(PrivateChannel):
    """Private, with the payload encrypted end to end by the broadcaster."""

    prefix = "private-encrypted-"


def to_channel(value: Any) -> Channel:
    """Whatever an event returned, as a `Channel`.

    A string is public; a model is private, on the channel it names — which is
    what makes `broadcast_on()` returning `[self, self.author]` work.
    """
    if isinstance(value, Channel):
        return value
    if isinstance(value, str):
        return Channel(value)
    return PrivateChannel(model_channel_name(value))


def to_channels(value: Any) -> list[Channel]:
    """One channel, a list of them, or a bare name — always a list."""
    if value is None:
        return []
    if isinstance(value, (Channel, str)) or not isinstance(value, (list, tuple, set)):
        return [to_channel(value)]
    return [to_channel(item) for item in value]


def channel_names(channels: Any) -> list[str]:
    """The wire names, deduplicated, in the order they were given."""
    seen: dict[str, None] = {}
    for channel in to_channels(channels):
        seen.setdefault(channel.full_name, None)
    return list(seen)


def strip_prefix(name: str) -> str:
    """`private-orders.1` → `orders.1` — what an authorization callback matches."""
    for prefix in ("private-encrypted-", "presence-", "private-"):
        if name.startswith(prefix):
            return name[len(prefix) :]
    return name


def is_private(name: str) -> bool:
    """Whether this wire name needs authorizing before anyone may listen."""
    return name.startswith(("private-", "presence-", "private-encrypted-"))


def is_presence(name: str) -> bool:
    return name.startswith("presence-")
