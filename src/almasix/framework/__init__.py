"""Application kernel: Application, IoC container, boot lifecycle."""

from almasix.framework.application import Application
from almasix.framework.bootstrap import ApplicationBuilder, Middleware
from almasix.framework.container import (
    CircularDependencyError,
    Container,
    ResolutionError,
)
from almasix.framework.helpers import (
    app,
    current_application,
    get_application,
    resolve,
    set_application,
)

__all__ = [
    "Application",
    "ApplicationBuilder",
    "Container",
    "Middleware",
    "CircularDependencyError",
    "ResolutionError",
    "app",
    "current_application",
    "get_application",
    "resolve",
    "set_application",
]
