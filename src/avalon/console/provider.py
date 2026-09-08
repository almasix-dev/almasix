"""Console service provider."""

from __future__ import annotations

from avalon.console.kernel import ConsoleKernel
from avalon.providers.provider import ServiceProvider


class ConsoleServiceProvider(ServiceProvider):
    """Binds the console kernel for schedule / Fiddle / command discovery."""

    def register(self) -> None:
        app = self.app

        def factory(_container):
            kernel = ConsoleKernel(app)
            kernel.discover()
            return kernel

        app.container.singleton(ConsoleKernel, factory)
        app.container.alias(ConsoleKernel, "console")

    def boot(self) -> None:
        from avalon.console.stub import FRAMEWORK_STUBS

        self.publishes({FRAMEWORK_STUBS: self.app.path("stubs")}, "avalon-stubs")
