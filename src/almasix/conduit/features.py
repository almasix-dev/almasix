"""Nested embed + event attribute helpers."""

from __future__ import annotations

from typing import Any

from almasix.conduit.component import Component
from almasix.conduit.manager import Conduit


def nest(parent: Component, child_name: str, **params: Any) -> str:
    """Embed a child Conduit component under a parent."""
    child = Conduit.component(child_name, **params)
    children = getattr(parent, "_Component__children", None)
    if isinstance(children, list):
        children.append(child)
    from almasix.conduit.mechanism import embed_component

    return embed_component(child)
