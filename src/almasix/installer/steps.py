"""What happens after the files land: git, dependencies, assets, migrations.

Each step is skippable, reports what it ran, and never leaves the installer
holding an exception — a new application whose `npm install` failed is still a
new application, and the summary says which part did not happen.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from almasix.installer.options import InstallPlan


@dataclass
class StepResult:
    """One step, and how it went."""

    name: str
    ran: bool
    ok: bool = True
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.ran and not self.ok


def run_steps(plan: InstallPlan, root: Path) -> list[StepResult]:
    """Run every step the plan asked for, in the order they depend on."""
    results = [git_init(plan, root), install_dependencies(plan, root)]
    results.append(install_node(plan, root))
    results.append(migrate(plan, root))
    return results


def git_init(plan: InstallPlan, root: Path) -> StepResult:
    if not plan.git:
        return StepResult("git", ran=False)
    if shutil.which("git") is None:
        return StepResult("git", ran=True, ok=False, detail="git is not installed")
    if (root / ".git").exists():
        return StepResult("git", ran=False, detail="already a repository")

    steps: Sequence[Sequence[str]] = (
        ("git", "init", "--initial-branch", plan.branch),
        ("git", "add", "-A"),
        ("git", "commit", "-m", "Initial commit"),
    )
    for command in steps:
        completed = _run(command, root)
        if completed.returncode != 0:
            return StepResult(
                "git",
                ran=True,
                ok=False,
                detail=_first_error(completed) or f"`{' '.join(command)}` failed",
            )
    return StepResult("git", ran=True, detail=f"branch {plan.branch}, one commit")


def install_dependencies(plan: InstallPlan, root: Path) -> StepResult:
    if not plan.install:
        return StepResult("install", ran=False)
    command = _python_install_command(plan)
    if command is None:
        return StepResult(
            "install",
            ran=True,
            ok=False,
            detail=f"{plan.installer} is not installed",
        )
    completed = _run(command, root)
    if completed.returncode != 0:
        return StepResult(
            "install",
            ran=True,
            ok=False,
            detail=_first_error(completed) or "dependency install failed",
        )
    return StepResult("install", ran=True, detail=" ".join(command))


def install_node(plan: InstallPlan, root: Path) -> StepResult:
    if not plan.npm:
        return StepResult("npm", ran=False)
    if shutil.which("npm") is None:
        return StepResult("npm", ran=True, ok=False, detail="npm is not installed")
    for command in (("npm", "install"), ("npm", "run", "build")):
        completed = _run(command, root)
        if completed.returncode != 0:
            return StepResult(
                "npm",
                ran=True,
                ok=False,
                detail=_first_error(completed) or f"`{' '.join(command)}` failed",
            )
    return StepResult("npm", ran=True, detail="npm install && npm run build")


def migrate(plan: InstallPlan, root: Path) -> StepResult:
    if not plan.migrate:
        return StepResult("migrate", ran=False)
    completed = _run((sys.executable, "smith", "migrate", "--force"), root)
    if completed.returncode != 0:
        return StepResult(
            "migrate",
            ran=True,
            ok=False,
            detail=_first_error(completed) or "smith migrate failed",
        )
    return StepResult("migrate", ran=True, detail="users, sessions, cache, queue tables")


def _python_install_command(plan: InstallPlan) -> tuple[str, ...] | None:
    """``uv pip install`` when uv is around, plain pip otherwise."""
    choice = plan.installer
    if choice in {"auto", "uv"} and shutil.which("uv") is not None:
        return ("uv", "pip", "install", "-e", ".")
    if choice == "uv":
        return None
    if choice in {"auto", "pip"}:
        return (sys.executable, "-m", "pip", "install", "-e", ".")
    return None


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _first_error(completed: subprocess.CompletedProcess[str]) -> str:
    for stream in (completed.stderr, completed.stdout):
        for line in (stream or "").splitlines():
            if line.strip():
                return line.strip()
    return ""
