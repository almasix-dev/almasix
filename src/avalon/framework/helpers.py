"""``app()`` / ``resolve()`` — the container without an injection point."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from avalon.framework.application import Application

_application: Application | None = None


def set_application(application: Application | None) -> None:
    global _application
    _application = application


def get_application() -> Application:
    if _application is None:
        raise RuntimeError("Application is not set. Bootstrap the Application first.")
    return _application


def current_application() -> Application | None:
    """Return the booted application, or ``None`` when nothing is bootstrapped."""
    return _application


def app(abstract: type | str | None = None) -> Any:
    """Return the application, or resolve ``abstract`` from it (Laravel ``app``)."""
    application = get_application()
    if abstract is None:
        return application
    return application.make(abstract)


def resolve(abstract: type | str) -> Any:
    """Resolve ``abstract`` out of the container (Laravel ``resolve``)."""
    return get_application().make(abstract)
