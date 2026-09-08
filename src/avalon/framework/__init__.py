"""Application kernel: Application, IoC container, boot lifecycle."""

from avalon.framework.application import Application
from avalon.framework.bootstrap import ApplicationBuilder, Middleware
from avalon.framework.container import Container, ResolutionError
from avalon.framework.helpers import (
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
    "ResolutionError",
    "app",
    "current_application",
    "get_application",
    "resolve",
    "set_application",
]
