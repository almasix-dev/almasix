"""Smith commands for the language server."""

from __future__ import annotations

from almasix.console.command import Command


class LspServeCommand(Command):
    signature = "lsp:serve"
    description = "Run the Almasix language server over stdio"

    def handle(self) -> int:
        try:
            from almasix.lsp.server import create_server
        except ImportError as exc:
            self.error("Install the lsp extra: pip install 'almasix[lsp]'")
            self.line(f"  ({exc})")
            return self.FAILURE

        self.info("Starting almasix-lsp on stdio…")
        server = create_server()
        server.start_io()
        return self.SUCCESS
