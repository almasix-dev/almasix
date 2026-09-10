"""Prism service provider."""

from __future__ import annotations

from pathlib import Path

from almasix.prism.engine import Engine
from almasix.prism.helpers import ViewFactory, set_engine
from almasix.providers.provider import ServiceProvider


class PrismServiceProvider(ServiceProvider):
    """Binds the view engine and registers ``resources/views``."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            engine = Engine(paths=[], cache_enabled=True)
            # Conventional Laravel-shaped path; create-on-write is the app's job.
            engine.add_path(app.path("resources", "views"))
            # The views the framework itself ships — pagination links, so far.
            # It comes second, so an application's own copy wins.
            engine.add_path(Path(__file__).parent / "views")
            return engine

        app.container.singleton(Engine, factory)
        app.container.alias(Engine, "view.engine")
        app.container.singleton(ViewFactory, lambda c: ViewFactory(c.resolve(Engine)))
        app.container.alias(ViewFactory, "view")

    def boot(self) -> None:
        set_engine(self.app.make(Engine))
        self._register_commands()

    def _register_commands(self) -> None:
        try:
            from almasix.console.kernel import ConsoleKernel
            from almasix.prism.commands.format import PrismFormatCommand

            kernel = self.app.make(ConsoleKernel)
            kernel.register(PrismFormatCommand)
        except Exception:  # pragma: no cover - soft boot
            pass
