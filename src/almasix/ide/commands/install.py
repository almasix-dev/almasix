"""``smith ide:install`` — write local VS Code / JetBrains editor config."""

from __future__ import annotations

from pathlib import Path

from almasix.console.command import Command
from almasix.ide.install import install_editor_config


class IdeInstallCommand(Command):
    signature = (
        "ide:install "
        "{--path= : Application root (default: cwd / find bootstrap/app.py)} "
        "{--force : Overwrite existing .vscode / .idea notes} "
        "{--no-vscode : Skip .vscode recommendations and settings} "
        "{--no-jetbrains : Skip .idea/almasix-editor.md}"
    )
    description = "Write local editor config for Prism + Almasix LSP sideload"

    def handle(self) -> int:
        given = self.option("path")
        base = Path(str(given)).expanduser() if given else None
        result = install_editor_config(
            base,
            vscode=not bool(self.option("no_vscode")),
            jetbrains=not bool(self.option("no_jetbrains")),
            force=bool(self.option("force")),
        )
        if not result.ok:
            self.error(result.error or "ide:install failed.")
            return self.FAILURE

        for path in result.written:
            try:
                rel = path.relative_to(result.base_path)
            except ValueError:
                rel = path
            self.line(f"  wrote  -> {rel}")
        for note in result.notes:
            self.line(f"  note   -> {note}")
        self.info("ide:install ok")
        return self.SUCCESS
