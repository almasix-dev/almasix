"""``python -m almasix.ide.index`` — JSON symbol dump for JetBrains."""

from __future__ import annotations

import argparse
import sys

from almasix.ide.index import dump_index_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump Almasix IDE symbol index as JSON")
    parser.add_argument(
        "--path",
        default=None,
        help="Application root (default: cwd / find bootstrap/app.py)",
    )
    args = parser.parse_args(argv)
    try:
        sys.stdout.write(dump_index_json(args.path))
        sys.stdout.write("\n")
    except Exception as exc:  # pragma: no cover - defensive
        sys.stderr.write(f"ide.index failed: {exc}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
