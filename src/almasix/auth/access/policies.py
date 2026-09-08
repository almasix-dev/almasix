"""Base policy class."""

from __future__ import annotations

from almasix.auth.access.handles import HandlesAuthorization


class Policy(HandlesAuthorization):
    """Application policy base (``smith make:policy``).

    Optional ``before(user, ability)`` short-circuits when it returns non-``None``.
    """
