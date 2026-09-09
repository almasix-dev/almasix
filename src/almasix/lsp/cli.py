"""CLI entry for ``almasix-lsp`` and ``python -m almasix.lsp``."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    """Run the language server (stdio by default)."""
    parser = argparse.ArgumentParser(
        prog="almasix-lsp",
        description="Almasix language server — completions, diagnostics, navigation.",
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        default=True,
        help="Communicate over stdin/stdout (default)",
    )
    parser.parse_args(argv)

    try:
        from almasix.lsp.server import create_server
    except ImportError as exc:  # pragma: no cover - missing optional extra
        print(
            "almasix-lsp requires the lsp extra: pip install 'almasix[lsp]'",
            file=sys.stderr,
        )
        print(f"({exc})", file=sys.stderr)
        return 1

    server = create_server()
    server.start_io()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
