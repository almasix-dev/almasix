"""almasix-inertia — server adapter for official Inertia.js clients."""

from __future__ import annotations

from inertia.props import (
    DeferProp,
    LazyProp,
    MergeProp,
    OnceProp,
    OptionalProp,
    defer,
    lazy,
    merge,
    once,
    optional,
)
from inertia.response import Inertia, InertiaResponse

__all__ = [
    "DeferProp",
    "Inertia",
    "InertiaResponse",
    "LazyProp",
    "MergeProp",
    "OnceProp",
    "OptionalProp",
    "defer",
    "lazy",
    "merge",
    "once",
    "optional",
]
