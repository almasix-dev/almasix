"""Exception handler service provider."""

from __future__ import annotations

import importlib
from pathlib import Path

from almasix.exceptions.handler import Handler
from almasix.exceptions.publish import framework_views_root
from almasix.providers.provider import ServiceProvider


class ExceptionsServiceProvider(ServiceProvider):
    """Binds the exception Handler and registers framework error view paths."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            handler_cls = _resolve_app_handler(app.base_path)
            return handler_cls(app)

        app.container.singleton(Handler, factory)
        app.container.alias(Handler, "exceptions.handler")

    def boot(self) -> None:
        try:
            from almasix.prism.engine import Engine
        except Exception:
            return
        if not self.app.container.bound(Engine):
            return
        engine = self.app.make(Engine)
        # App ``resources/views`` is registered first; framework default is fallback.
        fallback = framework_views_root("default")
        if fallback.is_dir():
            engine.add_path(fallback)


def _resolve_app_handler(base_path: str | Path) -> type[Handler]:
    """Prefer ``app.exceptions.handler.Handler`` when the app defines one."""
    del base_path  # import path is conventional; base_path reserved for future probes
    for dotted in (
        "app.exceptions.handler.Handler",
        "app.Exceptions.Handler.Handler",
    ):
        try:
            module_path, _, name = dotted.rpartition(".")
            module = importlib.import_module(module_path)
            candidate = getattr(module, name)
            if isinstance(candidate, type) and issubclass(candidate, Handler):
                return candidate
        except Exception:
            continue
    return Handler
