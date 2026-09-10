"""Demo editor integrations — ide:install + ide:stubs + package paths (M47)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.ide.install import install_editor_config
from almasix.ide.stubs import generate_stubs

_IDE_SUPPORT_REPO = "https://github.com/almasix-dev/ide-support"
_VS_MARKETPLACE = "https://marketplace.visualstudio.com/items?itemName=almasix.almasix"


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

        self.line(f"  ide-support -> {_IDE_SUPPORT_REPO}")
        self.line(f"  vscode  -> {_VS_MARKETPLACE}")
        self.line("  jetbrains -> Marketplace com.almasix.ide")
        self.line("  docs    -> Editor setup (Starlight) + VS Code ↔ PyCharm parity matrix")
        self.info("ide ok")
        return self.SUCCESS
