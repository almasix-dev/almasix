"""Conduit service provider — routes, views, Prism directives, assets."""

from __future__ import annotations

from pathlib import Path

from almasix.providers import ServiceProvider

_HERE = Path(__file__).resolve().parent


class ConduitServiceProvider(ServiceProvider):
    """Registers Conduit config, routes, views, ``@conduit``, and the JS client."""

    def register(self) -> None:
        from almasix.conduit.defaults import config as defaults
        from almasix.conduit.manager import Conduit

        if not self.app.config.has("conduit"):
            self.app.config.set("conduit", dict(defaults))
        else:
            existing = self.app.config.get("conduit")
            if isinstance(existing, dict):
                self.app.config.set("conduit", {**defaults, **existing})
        if not self.app.container.bound(Conduit):
            self.app.container.instance(Conduit, Conduit)

    def boot(self) -> None:
        self.publishes(
            {_HERE / "stubs" / "conduit.py.stub": self.app.path("config", "conduit.py")},
            "conduit-config",
        )
        self.publishes(
            {
                _HERE / "resources" / "js" / "conduit.js": self.app.path(
                    "public", "vendor", "conduit", "conduit.js"
                )
            },
            "conduit-assets",
        )
        self.load_routes_from(_HERE / "routes" / "web.py")
        self.load_views_from(_HERE / "resources" / "views", "conduit")
        from almasix.conduit.commands.make_conduit import MakeConduitCommand

        self.commands([MakeConduitCommand])
        self._register_directives()
        self._register_namespaces()

    def _register_namespaces(self) -> None:
        from almasix.conduit.manager import Conduit

        Conduit.registry().add_namespace("app.conduit")
        Conduit.registry().add_namespace("almasix.conduit.demo")
        try:
            from almasix.conduit.demo import Counter

            Conduit.register("counter", Counter)
        except Exception:  # pragma: no cover
            pass

    def _register_directives(self) -> None:
        try:
            from almasix.prism.engine import Engine

            if not self.app.container.bound(Engine):
                return
            engine = self.app.make(Engine)
        except Exception:  # pragma: no cover
            return

        def conduit_directive(expr: str) -> str:
            return f"__w(context['__conduit_render']({expr}))"

        def scripts_directive(_expr: str) -> str:
            return "__w(context.get('__conduit_scripts', lambda: '')())"

        engine.directive("conduit", conduit_directive)
        engine.directive("conduitScripts", scripts_directive)
        # Alias during rename window
        engine.directive("flux", conduit_directive)
        engine.directive("fluxScripts", scripts_directive)

        def inject(context: dict) -> None:
            from almasix.conduit.manager import conduit as embed
            from almasix.conduit.mechanism import conduit_assets_script

            context.setdefault("__conduit_render", embed)
            context.setdefault("__conduit_scripts", conduit_assets_script)
            context.setdefault("__flux_render", embed)
            context.setdefault("__flux_scripts", conduit_assets_script)
            if self.app.config.get("conduit.inject_assets", True):
                context.setdefault("conduit_scripts", conduit_assets_script)
                context.setdefault("flux_scripts", conduit_assets_script)

        engine.composer("*", inject)
