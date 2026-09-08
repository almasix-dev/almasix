"""Smith — Almasix's in-app CLI (Artisan equivalent). Prefer ``python smith …``.

``app`` is resolved on attribute access rather than imported here. Importing
it eagerly would build the CLI — and with it discover every command module —
the moment anything under ``almasix.smith`` is touched, including from a
command module that is itself still being imported.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - for type checkers only
    from almasix.smith.cli import app

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from almasix.smith.cli import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
