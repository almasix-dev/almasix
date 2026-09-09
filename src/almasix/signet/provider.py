"""Register Signet routes, config defaults, and the prune command."""

from __future__ import annotations

from pathlib import Path

from almasix.providers.provider import ServiceProvider

_STUBS = Path(__file__).resolve().parent / "stubs"


class SignetServiceProvider(ServiceProvider):
    """Laravel Sanctum provider — CSRF cookie route + publishable config/migration."""

    def register(self) -> None:
        self._merge_config()

    def boot(self) -> None:
        self.publishes(
            {
                _STUBS / "config" / "signet.py.stub": "config/signet.py",
            },
            "signet-config",
        )
        self.publishes(
            {
                _STUBS / "migrations" / "create_personal_access_tokens_table.py.stub": (
                    "database/migrations/0001_01_01_000003_create_personal_access_tokens_table.py"
                ),
            },
            "signet-migrations",
        )
        self._register_routes()
        self._register_commands()

    def _merge_config(self) -> None:
        try:
            if not self.app.config.has("signet"):
                from almasix.signet.defaults import default_signet_config

                self.app.config.set("signet", default_signet_config())
        except Exception:  # pragma: no cover - soft boot
            pass

    def _register_routes(self) -> None:
        try:
            from almasix.routing import Route
            from almasix.signet.http import csrf_cookie
        except Exception:  # pragma: no cover - soft boot
            return

        try:
            if self.app.router.has("signet.csrf-cookie"):  # pragma: no branch
                return
        except Exception:  # pragma: no cover - soft boot
            pass

        with Route.group(middleware=["web"]):
            Route.get("/signet/csrf-cookie", csrf_cookie).name("signet.csrf-cookie")

    def _register_commands(self) -> None:
        try:
            from almasix.console.kernel import ConsoleKernel
            from almasix.signet.commands.prune_expired import SignetPruneExpiredCommand

            kernel = self.app.make(ConsoleKernel)
            kernel.register(SignetPruneExpiredCommand)
        except Exception:  # pragma: no cover - soft boot
            pass
