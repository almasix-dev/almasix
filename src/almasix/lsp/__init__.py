"""Public API for the Almasix language server package."""

from __future__ import annotations

from almasix.lsp.index import AppIndex, RouteInfo, build_index, find_app_root

__all__ = [
    "AppIndex",
    "RouteInfo",
    "build_index",
    "create_server",
    "find_app_root",
    "run_stdio",
]


def create_server():
    """Create the configured pygls language server (requires ``almasix[lsp]``)."""
    from almasix.lsp.server import create_server as _create

    return _create()


def run_stdio() -> int:
    """Start the language server on stdin/stdout; return a process exit code."""
    from almasix.lsp.cli import main

    return main()
