"""UUID and ULID primary keys — Laravel's `HasUuids` / `HasUlids`.

Both mixins turn off auto-increment and fill their key on insert. Mix them in
**before** ``Model``::

    class Post(HasUuids, Model):
        ...
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any, ClassVar

#: Crockford's base32 alphabet — no I, L, O, or U.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ordered_uuid() -> uuid.UUID:
    """A time-ordered UUID (version 7), like Laravel's ``Str::orderedUuid``.

    Random UUIDs scatter across an index; ordered ones keep inserts local,
    which is the whole reason Laravel defaults to them for keys.
    """
    milliseconds = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    value = (
        (milliseconds << 80)
        | (0x7 << 76)  # version 7
        | (secrets.randbits(12) << 64)
        | (0b10 << 62)  # RFC 4122 variant
        | secrets.randbits(62)
    )
    return uuid.UUID(int=value)


def ulid() -> str:
    """A 26-character ULID: 48 bits of timestamp, 80 bits of randomness."""
    value = (int(time.time() * 1000) << 80) | secrets.randbits(80)
    characters = []
    for _ in range(26):
        characters.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(characters))


class HasUniqueStringIds:
    """Shared behavior for string-keyed models."""

    incrementing: ClassVar[bool] = False
    key_type: ClassVar[str] = "string"

    def new_unique_id(self) -> str:
        raise NotImplementedError

    def unique_ids(self) -> tuple[str, ...]:
        """Columns that should be filled with a generated id on insert."""
        return (type(self).primary_key,)


class HasUuids(HasUniqueStringIds):
    """Fill the primary key with a time-ordered UUID on insert."""

    def new_unique_id(self) -> str:
        return str(ordered_uuid())


class HasUlids(HasUniqueStringIds):
    """Fill the primary key with a ULID on insert."""

    def new_unique_id(self) -> str:
        return ulid()


def fill_unique_ids(model: Any) -> None:
    """Fill any empty unique-id columns before an insert."""
    generator = getattr(model, "new_unique_id", None)
    if not callable(generator):
        return
    for column in model.unique_ids():
        if model.get_raw_attribute(column) is None:
            model._write_attribute(column, generator())
