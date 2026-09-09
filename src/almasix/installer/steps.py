"""What happens after the files land: git, venv, dependencies, assets, migrations.

Each step is skippable, reports what it ran, and never leaves the installer
holding an exception — a new application whose `npm install` failed is still a
new application, and the summary says which part did not happen.
"""

from __future__ import annotations

import os
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
    results = [
        git_init(plan, root),
        create_venv(plan, root),
        install_dependencies(plan, root),
    ]
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
                detail=_failure_detail(completed, f"`{' '.join(command)}` failed"),
            )
    return StepResult("git", ran=True, detail=f"branch {plan.branch}, one commit")


def create_venv(plan: InstallPlan, root: Path) -> StepResult:
    """Create ``.venv`` inside the application when dependencies will be installed."""
    if not plan.install:
        return StepResult("venv", ran=False)

    python = venv_python(root)
    if python.is_file():
        return StepResult("venv", ran=True, detail=".venv already present")

    command = _venv_create_command(plan, root)
    if command is None:
        return StepResult(
            "venv",
            ran=True,
            ok=False,
            detail=f"{plan.installer} is not installed",
        )
    completed = _run(command, root)
    if completed.returncode != 0:
        return StepResult(
            "venv",
            ran=True,
            ok=False,
            detail=_failure_detail(completed, "venv creation failed"),
        )
    if not python.is_file():
        return StepResult(
            "venv",
            ran=True,
            ok=False,
            detail="venv creation finished but .venv/bin/python is missing",
        )
    return StepResult("venv", ran=True, detail=" ".join(command))


def install_dependencies(plan: InstallPlan, root: Path) -> StepResult:
    if not plan.install:
        return StepResult("install", ran=False)

    python = venv_python(root)
    if not python.is_file():
        return StepResult(
            "install",
            ran=True,
            ok=False,
            detail=".venv is missing — create the virtualenv first",
        )

    command = _python_install_command(plan, root)
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
            detail=_failure_detail(completed, "dependency install failed"),
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
                detail=_failure_detail(completed, f"`{' '.join(command)}` failed"),
            )
    return StepResult("npm", ran=True, detail="npm install && npm run build")


def migrate(plan: InstallPlan, root: Path) -> StepResult:
    if not plan.migrate:
        return StepResult("migrate", ran=False)
    python = app_python(root)
    completed = _run((str(python), "smith", "migrate", "--force"), root)
    if completed.returncode != 0:
        return StepResult(
            "migrate",
            ran=True,
            ok=False,
            detail=_failure_detail(completed, "smith migrate failed"),
        )
    return StepResult(
        "migrate",
        ran=True,
        detail="users, password_reset_tokens, sessions, cache, queue tables",
    )


def venv_python(root: Path) -> Path:
    """Interpreter inside the application's ``.venv``."""
    if os.name == "nt":  # pragma: no cover - Windows layout
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


def app_python(root: Path) -> Path:
    """Prefer the app venv; fall back to the process that ran ``almasix``."""
    candidate = venv_python(root)
    return candidate if candidate.is_file() else Path(sys.executable)


def _venv_create_command(plan: InstallPlan, root: Path) -> tuple[str, ...] | None:
    target = str(root / ".venv")
    choice = plan.installer
    if choice in {"auto", "uv"} and shutil.which("uv") is not None:
        return ("uv", "venv", target)
    if choice == "uv":
        return None
    if choice in {"auto", "pip"}:
        return (sys.executable, "-m", "venv", target)
    return None


def _python_install_command(plan: InstallPlan, root: Path) -> tuple[str, ...] | None:
    """Install the app editable into ``.venv`` (plus the engine extra when set)."""
    python = venv_python(root)
    packages = ["-e", "."]
    extra = plan.database_info.extra
    if extra:
        packages.append(extra)

    choice = plan.installer
    if choice in {"auto", "uv"} and shutil.which("uv") is not None:
        return ("uv", "pip", "install", "--python", str(python), *packages)
    if choice == "uv":
        return None
    if choice in {"auto", "pip"}:
        return (str(python), "-m", "pip", "install", *packages)
    return None


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a step command with live stdout/stderr (not captured silently)."""
    printable = " ".join(str(part) for part in command)
    print(f"$ {printable}", flush=True)
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=False,
        text=True,
        check=False,
    )
    # Streams were inherited; keep empty captured bodies for callers of _first_error.
    return subprocess.CompletedProcess(
        args=completed.args,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _first_error(completed: subprocess.CompletedProcess[str]) -> str:
    for stream in (completed.stderr, completed.stdout):
        for line in (stream or "").splitlines():
            if line.strip():
                return line.strip()
    return ""


def _failure_detail(completed: subprocess.CompletedProcess[str], fallback: str) -> str:
    return _first_error(completed) or f"{fallback} (see output above)"
