"""Inertia package service provider."""

from __future__ import annotations

from pathlib import Path

from almasix.providers import ServiceProvider

_HERE = Path(__file__).resolve().parent


class InertiaServiceProvider(ServiceProvider):
    """Registers Inertia config, root view, middleware alias, and SSR command."""

    def register(self) -> None:
        self.merge_config_from(_HERE / "config" / "inertia.py", "inertia")

    def boot(self) -> None:
        self.publishes(
            {_HERE / "config" / "inertia.py": self.app.path("config", "inertia.py")},
            "inertia-config",
        )
        self.publishes(
            {
                _HERE / "resources" / "views" / "app.prism.html": self.app.path(
                    "resources", "views", "app.inertia.prism.html"
                )
            },
            "inertia-views",
        )
        self.load_views_from(_HERE / "resources" / "views", "inertia")
        self._register_directives()
        self._register_middleware_alias()
        from inertia.console.start_ssr import InertiaStartSsrCommand

        self.commands([InertiaStartSsrCommand])

    def _register_middleware_alias(self) -> None:
        # Alias is also set in progress bootstrap; keep config discoverable.
        aliases = self.app.config.get("http.middleware_aliases") or {}
        if isinstance(aliases, dict) and "inertia" not in aliases:
            aliases = {
                **aliases,
                "inertia": "inertia.middleware.HandleInertiaRequests",
            }
            self.app.config.set("http.middleware_aliases", aliases)

    def _register_directives(self) -> None:
        try:
            from almasix.prism.engine import Engine

            if not self.app.container.bound(Engine):
                return
            engine = self.app.make(Engine)
        except Exception:  # pragma: no cover
            return

        def inertia_directive(_expr: str) -> str:
            return (
                '__w(\'<div id="app" data-page="\' + '
                "__e(str(context.get('page_json') or '{}')) + '\">' + "
                "str(context.get('ssr_body') or '') + '</div>')"
            )

        def inertia_head_directive(_expr: str) -> str:
            return "__w(str(context.get('ssr_head') or ''))"

        engine.directive("inertia", inertia_directive)
        engine.directive("inertiaHead", inertia_head_directive)
