"""M24 smoke — factory docs, make:factory, the demo command, the board."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
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


def test_m24_docs_and_sidebar_exist() -> None:
    page = ROOT / "website" / "src" / "content" / "docs" / "database" / "factories.md"
    assert page.is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "database/factories" in sidebar
    seeding = (ROOT / "website" / "src" / "content" / "docs" / "database" / "seeding.md").read_text(
        encoding="utf-8"
    )
    assert "/database/factories/" in seeding


def test_m24_make_factory_writes_both_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m24_make", destination=tmp_path / "m24_make")
    monkeypatch.chdir(root)

    assert runner.invoke(smith_app, ["make:factory", "TagFactory"]).exit_code == 0
    plain = (root / "database" / "factories" / "tag_factory.py").read_text(encoding="utf-8")
    assert "class TagFactory(Factory):" in plain

    assert runner.invoke(smith_app, ["make:model", "Post", "-m", "-f"]).exit_code == 0
    written = (root / "database" / "factories" / "post_factory.py").read_text(encoding="utf-8")
    assert "model = Post" in written
    model = (root / "app" / "models" / "post.py").read_text(encoding="utf-8")
    assert "class Post(HasFactory, Model):" in model


def test_m24_the_example_seeder_runs_through_factories() -> None:
    seeder = (PROGRESS / "database" / "seeders" / "demo_seeder.py").read_text(encoding="utf-8")
    assert "User.factory()" in seeder
    assert "Post.factory()" in seeder
    assert (PROGRESS / "database" / "factories" / "user_factory.py").is_file()


def test_m24_progress_factories_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:factories"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "factories demo ok" in output
    assert "count + sequence -> published [True, False, True, False]" in output
    assert "has_attached -> ['member', 'member']" in output


def test_m24_board_marks_factories_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m24 = next(m for m in _milestones() if m["id"] == "M24")
    assert m24["status"] == "complete"
    assert any("progress:factories" in proof for proof in m24["proof"])
