"""Prism — featherweight Blade-familiar view engine (M6).

Templates use the ``.prism.html`` extension. Inline code uses
``@python`` / ``@endpython`` only — no freeform Python embedding.
"""

from __future__ import annotations

from almasix.prism.attributes import AttributeBag
from almasix.prism.component import Component
from almasix.prism.engine import Engine, ViewNotFoundError
from almasix.prism.escape import HtmlString, e
from almasix.prism.helpers import (
    ViewFactory,
    csrf_field,
    method_field,
    render,
    set_engine,
    view,
)
from almasix.prism.loop import Loop
from almasix.prism.provider import PrismServiceProvider
from almasix.prism.vite import Vite, vite, vite_react_refresh

__all__ = [
    "AttributeBag",
    "Component",
    "Engine",
    "HtmlString",
    "Loop",
    "PrismServiceProvider",
    "ViewFactory",
    "ViewNotFoundError",
    "Vite",
    "csrf_field",
    "e",
    "method_field",
    "render",
    "set_engine",
    "view",
    "vite",
    "vite_react_refresh",
]
