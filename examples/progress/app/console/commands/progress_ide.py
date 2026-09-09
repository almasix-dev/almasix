"""Demo editor integrations — ide:install + ide:stubs + package paths (M47)."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.ide.install import install_editor_config
from almasix.ide.stubs import generate_stubs


class ProgressIdeCommand(Command):
    signature = "progress:ide"
    description = "Demo editor install config and type stubs (M47)"

    def handle(self) -> int:
        self.info("Editor integrations — ide:install + ide:stubs")
        root = self.app.base_path

        install = install_editor_config(root, force=True)
        if not install.ok:
            self.error(install.error or "ide:install failed")
            return self.FAILURE
        for path in install.written:
            try:
                rel = path.relative_to(root)
            except ValueError:
                rel = path
            self.line(f"  install -> {rel}")

        stubs = generate_stubs(root)
        if not stubs.ok:
            self.error(stubs.error or "ide:stubs failed")
            return self.FAILURE
        self.line(f"  stubs   -> {stubs.output_dir.relative_to(root)}")
        self.line(f"  models  -> {len(stubs.model_files)}")
        if stubs.routes_file is not None:
            self.line(f"  routes  -> {stubs.routes_file.relative_to(root)}")

        repo = self._repo_root(root)
        vsix = sorted((repo / "editors" / "vscode").glob("*.vsix")) if repo else []
        jb_dist = repo / "editors" / "jetbrains" / "build" / "distributions" if repo else None
        zips = sorted(jb_dist.glob("*.zip")) if jb_dist and jb_dist.is_dir() else []
        self.line(
            f"  vsix    -> {vsix[-1].name if vsix else '(run: cd editors/vscode && npm run package)'}"
        )
        self.line(
            f"  jb zip  -> {zips[-1].name if zips else '(run: cd editors/jetbrains && ./gradlew buildPlugin)'}"
        )
        self.line("  docs    -> Editor setup (Starlight) + VS Code ↔ PyCharm parity matrix")
        self.info("ide ok")
        return self.SUCCESS

    def _repo_root(self, app_root: Path) -> Path | None:
        """Monorepo root when running from examples/progress."""
        current = app_root.resolve()
        for candidate in (current, *current.parents):
            if (candidate / "editors" / "vscode").is_dir() and (
                candidate / "editors" / "jetbrains"
            ).is_dir():
                return candidate
        return None
