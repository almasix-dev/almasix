"""Author model."""

from __future__ import annotations

from almasix.orm import HasFactory, Model


class Author(HasFactory, Model):
    """Author model."""

    guarded: tuple[str, ...] = ("id")
