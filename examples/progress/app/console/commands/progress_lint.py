"""Demo the lint and format gate (M51).

Runs the same checks CI and ``make lint`` run — pinned ruff, explicit rule
selection, check + format --check — and prints the contract.
"""

from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path

from almasix.console.command import Command

ROOT = Path(__file__).resolve().parents[5]  # …/almasix (repo root)
PINNED_RUFF = "0.16.6"
SELECTION = ("E4", "E7", "E9", "F", "I", "UP", "B", "RUF100")


class ProgressLintCommand(Command):
    signature = "progress:lint"
    description = "Demo the lint/format gate — pinned ruff, make lint, CI job (M51)"

    def handle(self) -> int:
        version = importlib.metadata.version("ruff")
        self.info(f"ruff pin -> {version} (required {PINNED_RUFF})")
        if version != PINNED_RUFF:
            self.error(f"dev extra must pin ruff=={PINNED_RUFF}")
            return 1

        self.info(f"rule selection -> {', '.join(SELECTION)}")
        self.info("CI job -> lint (ruff check + format --check on 3.11–3.13)")

        check = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "src", "tests"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        fmt = subprocess.run(
            [sys.executable, "-m", "ruff", "format", "--check", "src", "tests"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

        if check.returncode != 0:
            self.line((check.stdout + check.stderr).strip() or "ruff check failed")
            self.error("ruff check -> failed")
            return 1
        self.info("ruff check -> clean")

        if fmt.returncode != 0:
            self.line((fmt.stdout + fmt.stderr).strip() or "ruff format --check failed")
            self.error("ruff format --check -> failed")
            return 1
        self.info("ruff format --check -> clean")

        self.success("lint and format gate ok")
        return 0
