"""M16 smoke — Redis scaffold, progress command, board."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
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


def test_m16_scaffold_ships_redis_config(tmp_path: Path) -> None:
    root = scaffold_app("m16_redis", destination=tmp_path / "m16_redis")
    assert (root / "config" / "redis.py").is_file()
    assert "REDIS_HOST=" in (root / ".env").read_text(encoding="utf-8")
    assert '"redis"' in (root / "config" / "cache.py").read_text(encoding="utf-8")
    assert '"redis"' in (root / "config" / "queue.py").read_text(encoding="utf-8")


def test_m16_progress_redis_command_skips_without_server(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:redis"])
    assert result.exit_code == 0, result.stdout + result.stderr
    out = (result.stdout + result.stderr).lower()
    assert "redis" in out
