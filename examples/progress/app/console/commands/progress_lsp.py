"""Demo Almasix language server index against this app (M46)."""

from __future__ import annotations

from almasix.console.command import Command
from almasix.lsp import build_index


class ProgressLspCommand(Command):
    signature = "progress:lsp"
    description = "Demo almasix-lsp application index (M46)"

    def handle(self) -> int:
        self.info("Language server — build_index")
        index = build_index(self.app.base_path)
        if index.error:
            self.error(index.error)
            return self.FAILURE
        self.line(f"  views  -> {len(index.views)}")
        self.line(f"  routes -> {len(index.routes)}")
        self.line(f"  config -> {len(index.config_keys)}")
        self.line(f"  models -> {len(index.models)}")
        self.line(f"  middleware -> {len(index.middleware_aliases)}")
        self.line(f"  translations -> {len(index.translation_keys)}")
        self.line("  run: almasix-lsp  |  python -m almasix.lsp  |  smith lsp:serve")
        self.info("lsp ok")
        return self.SUCCESS
