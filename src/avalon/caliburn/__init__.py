"""Caliburn — featherweight Blade-familiar view engine (M6).

Templates use the ``.cal.html`` extension. Inline code uses
``@python`` / ``@endpython`` only — no freeform Python embedding.
"""

from __future__ import annotations

from avalon.caliburn.attributes import AttributeBag
from avalon.caliburn.component import Component
from avalon.caliburn.engine import Engine, ViewNotFoundError
from avalon.caliburn.escape import HtmlString, e
from avalon.caliburn.helpers import (
    ViewFactory,
    csrf_field,
    method_field,
    render,
    set_engine,
    view,
)
from avalon.caliburn.loop import Loop
from avalon.caliburn.provider import CaliburnServiceProvider

__all__ = [
    "AttributeBag",
    "CaliburnServiceProvider",
    "Component",
    "Engine",
    "HtmlString",
    "Loop",
    "ViewFactory",
    "ViewNotFoundError",
    "csrf_field",
    "e",
    "method_field",
    "render",
    "set_engine",
    "view",
]
