"""Class-based Prism components (Blade ``Illuminate\\View\\Component`` shape)."""

from __future__ import annotations

from typing import Any, ClassVar


class Component:
    """Base for class-based view components.

    Subclass, set public constructor attributes (or assign on ``self``), and
    return a view name from :meth:`render`. Convention::

        # app/view/components/alert.py
        class Alert(Component):
            def __init__(self, type: str = "info") -> None:
                self.type = type

            def render(self) -> str:
                return "components.alert"
    """

    template: ClassVar[str | None] = None

    def render(self) -> str:
        """Return the Prism view name to render (``components.alert``)."""
        if self.template:
            return self.template
        raise NotImplementedError(
            f"{type(self).__name__} must implement render() or set template="
        )

    def data(self) -> dict[str, Any]:
        """Public data merged into the component view context."""
        return {
            key: value
            for key, value in vars(self).items()
            if not key.startswith("_")
        }

    def with_attributes(self, attrs: dict[str, Any]) -> Component:
        """Store leftover HTML attributes for ``attributes`` in the view."""
        self._attributes = dict(attrs)
        return self

    def attribute_data(self) -> dict[str, Any]:
        return dict(getattr(self, "_attributes", {}) or {})
