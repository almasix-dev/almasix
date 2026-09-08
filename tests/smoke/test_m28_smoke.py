"""M28 smoke — the testing toolkit, its docs, its scaffold, and the board."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs" / "testing"
runner = CliRunner()


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


def test_m28_docs_and_sidebar_exist() -> None:
    for page in ("index.md", "http-tests.md", "console-tests.md", "database.md", "mocking.md"):
        assert (DOCS / page).is_file(), page
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "'testing'" in sidebar
    assert "'testing/http-tests'" in sidebar
    assert "'testing/mocking'" in sidebar


def test_m28_a_scaffolded_app_ships_a_suite_that_passes(tmp_path: Path) -> None:
    """`almasix new` writes tests, and they are green before a line is added."""
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m28_scaffold", destination=tmp_path / "m28_scaffold")
    assert (root / "tests" / "conftest.py").is_file()
    assert (root / "tests" / "feature" / "example_test.py").is_file()
    assert (root / "tests" / "unit" / "example_test.py").is_file()
    assert 'python_classes = ["Test*", "*Test"]' in (root / "pyproject.toml").read_text()

    finished = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr


def test_m28_make_test_writes_a_feature_and_a_unit_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m28_generator", destination=tmp_path / "m28_generator")
    monkeypatch.chdir(root)
    kernel = _kernel_for(root)

    assert kernel.run_command("make:test", {"name": "PostTest"}, {}) == 0
    assert kernel.run_command("make:test", {"name": "SlugTest"}, {"unit": True}) == 0

    feature = (root / "tests" / "feature" / "post_test.py").read_text(encoding="utf-8")
    unit = (root / "tests" / "unit" / "slug_test.py").read_text(encoding="utf-8")
    assert "class PostTest(TestCase):" in feature
    assert "class SlugTest:" in unit


def test_m28_progress_testing_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:testing"])
    output = result.stdout + result.stderr

    assert result.exit_code == 0, output
    assert "testing demo ok" in output
    assert "rendered the [progress] view" in output
    assert "console -> progress:hello greeted the test and exited 0" in output
    assert "database -> the transaction rolled back, 0 row(s) left behind" in output
    assert "travel -> the clock reads 2030-01-01 inside the block" in output


def test_m28_the_examples_own_suite_passes() -> None:
    """The living example is tested by the toolkit it demonstrates."""
    finished = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    assert finished.returncode == 0, finished.stdout + finished.stderr


def test_m28_board_marks_the_testing_toolkit_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m28 = next(m for m in _milestones() if m["id"] == "M28")
    assert m28["status"] == "complete"
    assert any("progress:testing" in proof for proof in m28["proof"])


def _kernel_for(root: Path) -> object:
    from almasix.console.kernel import ConsoleKernel

    kernel = ConsoleKernel.from_cwd(root)
    kernel.discover_framework_commands()
    return kernel
