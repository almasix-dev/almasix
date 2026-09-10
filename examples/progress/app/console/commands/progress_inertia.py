"""Demo almasix-inertia server adapter (M55)."""

from __future__ import annotations

from inertia import Inertia
from inertia.ssr import render_ssr

from almasix.console.command import Command


class ProgressInertiaCommand(Command):
    signature = "progress:inertia"
    description = "Demo almasix-inertia render, partial props, version, SSR (M55)"

    def handle(self) -> int:
        Inertia.share("app_name", "Progress")
        Inertia.set_version("progress-test-v1")

        response = Inertia.render(
            "Welcome",
            {
                "framework": "almasix",
                "count": 3,
                "heavy": Inertia.lazy(lambda: "computed-heavy"),
                "notes": Inertia.defer(lambda: ["a", "b"]),
                "tags": Inertia.merge(["x"]),
            },
        )
        page = response._page(None)
        assert page["component"] == "Welcome"
        assert page["props"]["framework"] == "almasix"
        assert page["props"]["app_name"] == "Progress"
        assert "heavy" not in page["props"]
        assert "notes" in page.get("deferredProps", {}).get("default", [])
        assert page.get("mergeProps") == ["tags"]
        assert page["version"] == "progress-test-v1"
        self.info(f"page → {page['component']} v{page['version']} (lazy/defer/merge ok)")

        html = response._document(page)
        assert 'id="app"' in html or "data-page" in html
        assert "Welcome" in html
        self.info(f"root document → {len(html)} bytes")

        # Partial reload filtering + lazy resolution
        class _Req:
            def header(self, name: str, default=None):
                headers = {
                    "X-Inertia-Partial-Component": "Welcome",
                    "X-Inertia-Partial-Data": "framework,heavy,notes",
                }
                return headers.get(name, default)

        partial = response._page(_Req())  # type: ignore[arg-type]
        assert partial["props"]["framework"] == "almasix"
        assert partial["props"]["heavy"] == "computed-heavy"
        assert partial["props"]["notes"] == ["a", "b"]
        assert "count" not in partial["props"]
        self.info("partial reload + lazy/defer resolve ok")

        # SSR graceful fallback when worker down
        ssr = render_ssr(page)
        self.info(f"ssr (may be None if worker down) → {ssr is not None}")

        uris = {route.uri for route in self.app.router.routes}
        self.info(f"routes with inertia → {[u for u in uris if 'inertia' in u]}")
        self.success("inertia ok")
        return 0
