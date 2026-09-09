"""M51 smoke — lint pin, CI job, make lint, demo, and the board."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m51_ruff_is_pinned_exactly() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "ruff==0.16.6" in pyproject
    assert importlib.metadata.version("ruff") == "0.16.6"

    assert "[tool.ruff.lint]" in pyproject
    assert "select = [" in pyproject
    for rule in ("E4", "E7", "E9", "F", "I", "UP", "B", "RUF100"):
        assert f'"{rule}"' in pyproject or f"'{rule}'" in pyproject, rule


def test_m51_make_lint_and_ci_enforce_check_and_format() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "ruff check src tests" in makefile
    assert "ruff format --check src tests" in makefile

    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^  lint:", ci)
    assert "ruff check src tests" in ci
    assert "ruff format --check src tests" in ci
    assert "0.16.6" in ci


def test_m51_lint_is_green() -> None:
    check = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr

    fmt = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "src", "tests"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr


def test_m51_demo_command_runs_the_gate() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:lint"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "ruff pin -> 0.16.6",
        "rule selection ->",
        "CI job -> lint",
        "ruff check -> clean",
        "ruff format --check -> clean",
        "lint and format gate ok",
    ):
        assert line in out, line


def test_m51_board_marks_lint_gate_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}
    assert by_id["M51"]["status"] == "complete"
    assert "smith progress:lint" in by_id["M51"]["proof"]
    assert any("0.16.6" in item for item in by_id["M51"]["proof"])


def test_m51_readme_claims_match_ci() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "make lint" in readme
    assert "ruff" in readme.lower()
    # The old honesty disclaimer must not return once the gate exists.
    assert "not a CI gate yet" not in readme
    assert "does not pass" not in readme
