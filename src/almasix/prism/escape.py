"""HTML escaping for Prism echo tags."""

from __future__ import annotations

import html
from typing import Any


class HtmlString:
    """Mark a string as safe HTML (Blade ``HtmlString`` / ``$slot``)."""

    __slots__ = ("_html",)

    def __init__(self, value: str) -> None:
        self._html = value if isinstance(value, str) else str(value)

    def __html__(self) -> str:
        return self._html

    def __str__(self) -> str:
        return self._html

    def __repr__(self) -> str:
        return f"HtmlString({self._html!r})"


class DeferredHtml:
    """Lazy safe HTML — used for component slots so ``@props`` / ``@aware`` run first."""

    __slots__ = ("_factory", "_html", "_done")

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._html = ""
        self._done = False

    def _render(self) -> str:
        if not self._done:
            value = self._factory()
            self._html = value if isinstance(value, str) else str(value or "")
            self._done = True
        return self._html

    def __html__(self) -> str:
        return self._render()

    def __str__(self) -> str:
        return self._render()

    def __repr__(self) -> str:
        return f"DeferredHtml({self._html!r})" if self._done else "DeferredHtml(<pending>)"


def e(value: Any) -> str:
    """Escape a value for safe HTML text content (Blade ``{{ }}``)."""
    if value is None:
        return ""
    html_method = getattr(value, "__html__", None)
    if callable(html_method):
        return str(html_method())
    return html.escape(str(value), quote=True)
