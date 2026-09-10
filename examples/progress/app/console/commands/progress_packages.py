"""Demo package development APIs in the living example (M29)."""

from __future__ import annotations

from almasix.config import config
from almasix.console.command import Command
from almasix.prism.helpers import render
from almasix.providers import PackageManifest, ServiceProvider
from almasix.translation import __


class ProgressPackagesCommand(Command):
    signature = "progress:packages"
    description = "Demo package providers, discovery, publish tags, and namespaced views (M29)"

    def handle(self) -> int:
        tags = ServiceProvider.publishable_tags()
        self.info(f"publish tags → {', '.join(tags) or '(none)'}")
        assert "courier-config" in tags, "CourierServiceProvider should declare courier-config"

        driver = config("courier.driver")
        self.info(f"courier.driver → {driver}")
        assert driver == "pigeon", "merge_config_from should load package defaults"

        html = render("courier::welcome", {"driver": driver})
        self.info(f"view courier::welcome → {html.strip()}")
        assert "Courier package view" in html

        greeting = __("courier::messages.greeting")
        self.info(f"lang courier::messages.greeting → {greeting}")
        assert "Courier" in greeting

        discovered = PackageManifest().providers()
        self.info(f"discovered providers → {len(discovered)}")

        uris = {route.uri for route in self.app.router.routes}
        self.info(f"route /courier → {'/courier' in uris}")
        assert "/courier" in uris, "load_routes_from should register /courier"

        self.success("packages ok")
        return self.SUCCESS
