"""Demo M36 starter kits — scaffold each kit overlay and assert the Forge surface."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from almasix.console.command import Command
from almasix.installer.kits import KIT_NAMES, find_kit
from almasix.installer.scaffold import scaffold_app


class ProgressKitsCommand(Command):
    signature = "progress:kits"
    description = "Scaffold every M36 starter kit and assert production surfaces"

    def handle(self) -> int:
        workspace = Path(tempfile.mkdtemp(prefix="almasix-kits-"))
        try:
            self.info(f"workspace → {workspace}")

            # Web + Tailwind (default CSS for kits)
            web = scaffold_app(
                "kitweb",
                destination=workspace / "web",
                stack="tailwind",
                kit="web",
                tests=False,
            )
            self._assert_web(web)
            self.info("web/tailwind ok")

            # Web CSS variants
            for stack in ("bootstrap", "none"):
                root = scaffold_app(
                    f"kitweb{stack}",
                    destination=workspace / f"web_{stack}",
                    stack=stack,
                    kit="web",
                    tests=False,
                )
                assert (root / "routes" / "web.py").is_file()
                assert (root / "app" / "support" / "totp.py").is_file()
                self.info(f"web/{stack} ok")

            # API / Signet
            api = scaffold_app(
                "kitapi",
                destination=workspace / "api",
                stack="none",
                kit="api",
                tests=False,
            )
            api_routes = (api / "routes" / "api.py").read_text(encoding="utf-8")
            assert "auth:signet" in api_routes
            assert "TokenController" in api_routes
            user = (api / "app" / "models" / "user.py").read_text(encoding="utf-8")
            assert "HasApiTokens" in user
            self.info("api/signet ok")

            # SPA — React / Vue / Svelte
            for frontend in ("react", "vue", "svelte"):
                root = scaffold_app(
                    f"kit{frontend}",
                    destination=workspace / frontend,
                    kit=frontend,
                    tests=False,
                )
                self._assert_spa(root, frontend)
                self.info(f"spa/{frontend} ok")

            # Catalogue honesty
            assert "none" in KIT_NAMES and "web" in KIT_NAMES
            assert find_kit("conduit").name == "web"
            assert find_kit("spa").name == "react"
            self.info(f"kits catalogue → {', '.join(KIT_NAMES)}")

            self.success("kits ok")
            return 0
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _assert_web(self, root: Path) -> None:
        routes = (root / "routes" / "web.py").read_text(encoding="utf-8")
        for needle in (
            "PasswordResetController",
            "TwoFactorController",
            "TeamController",
            "NotificationController",
            "ProfileController",
            "VerificationController",
        ):
            assert needle in routes, needle
        assert (root / "resources" / "views" / "layouts" / "marketing.prism.html").is_file()
        assert (root / "resources" / "views" / "layouts" / "app.prism.html").is_file()
        welcome = (root / "resources" / "views" / "welcome.prism.html").read_text(encoding="utf-8")
        assert "forge-mesh" in welcome or "font-display" in welcome
        css = (root / "resources" / "css" / "app.css").read_text(encoding="utf-8")
        assert "#0d9488" in css or "0d9488" in css
        assert (root / "app" / "conduit" / "theme_toggle.py").is_file()
        migrations = list((root / "database" / "migrations").glob("*teams*"))
        assert migrations, "teams migration missing"
        assert (root / "app" / "support" / "totp.py").is_file()

    def _assert_spa(self, root: Path, frontend: str) -> None:
        pkg = (root / "package.json").read_text(encoding="utf-8")
        assert "@inertiajs/" in pkg
        assert frontend in pkg or (frontend == "vue" and "vue" in pkg)
        config = (root / "config" / "app.py").read_text(encoding="utf-8")
        assert "InertiaServiceProvider" in config
        boot = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
        assert "inertia" in boot
        pages = root / "resources" / "js" / "Pages"
        assert pages.is_dir()
        assert (
            (pages / "Welcome.jsx").is_file()
            or (pages / "Welcome.vue").is_file()
            or (pages / "Welcome.svelte").is_file()
        )
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert "almasix-inertia" in pyproject or "inertia" in pyproject
