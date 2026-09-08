"""Grail — Avalon's in-app CLI (Artisan equivalent). Prefer ``python grail …``.

``app`` is resolved on attribute access rather than imported here. Importing
it eagerly would build the CLI — and with it discover every command module —
the moment anything under ``avalon.grail`` is touched, including from a
command module that is itself still being imported.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from avalon.grail.cli import app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from avalon.grail.cli import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
