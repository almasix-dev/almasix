"""Demo M36 starter kits — scaffold overlays, then soak Web + Vue auth HTTP."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
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
            self._soak(web, mode="web")

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

            # SPA — React / Vue / Svelte (file surface for all; HTTP soak for Vue)
            for frontend in ("react", "vue", "svelte"):
                root = scaffold_app(
                    f"kit{frontend}",
                    destination=workspace / frontend,
                    kit=frontend,
                    tests=False,
                )
                self._assert_spa(root, frontend)
                self.info(f"spa/{frontend} ok")
                if frontend == "vue":
                    self._soak(root, mode="spa")

            # Catalogue honesty
            assert "none" in KIT_NAMES and "web" in KIT_NAMES
            assert find_kit("conduit").name == "web"
            assert find_kit("spa").name == "react"
            self.info(f"kits catalogue → {', '.join(KIT_NAMES)}")

            self.success("kits ok")
            return 0
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def _soak(self, root: Path, *, mode: str) -> None:
        """Migrate SQLite, then register→logout→login in a clean subprocess."""
        migrated = subprocess.run(
            [sys.executable, "smith", "migrate", "--force"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "APP_BASE_PATH": ""},
        )
        assert migrated.returncode == 0, (
            f"migrate failed in {root}:\n{migrated.stdout}\n{migrated.stderr}"
        )
        self.line(f"  migrate ({mode}) -> ok")

        script = (
            "from almasix.installer.kit_soak import soak_auth; "
            f"print(soak_auth('.', mode={mode!r}))"
        )
        soaked = subprocess.run(
            [sys.executable, "-c", script],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "APP_BASE_PATH": ""},
        )
        out = (soaked.stdout or "") + (soaked.stderr or "")
        assert soaked.returncode == 0, f"auth soak failed ({mode}) in {root}:\n{out}"
        line = next(
            (row for row in soaked.stdout.splitlines() if "auth soak ok" in row),
            soaked.stdout.strip().splitlines()[-1] if soaked.stdout.strip() else "no output",
        )
        self.line(f"  {line}")
        self.info(f"{mode} auth soak ok")

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
        # SPA stubs pull Inertia via the ``almasix[inertia]`` extra.
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert "almasix[inertia]" in pyproject or "almasix-inertia" in pyproject
