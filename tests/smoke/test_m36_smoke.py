"""M36 smoke — starter kits scaffold, board, docs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs"
runner = CliRunner()


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.syspath_prepend(str(ROOT / "packages" / "courier" / "src"))
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    monkeypatch.syspath_prepend(str(ROOT / "packages" / "courier" / "src"))
    import importlib

    module = importlib.import_module("bootstrap.app")
    app = module.application
    app._asgi = None
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m36_progress_kits_command(progress_cwd: Path) -> None:
    result = runner.invoke(smith_app, ["progress:kits"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "kits ok" in result.stdout
    assert "web/tailwind ok" in result.stdout
    assert "api/signet ok" in result.stdout
    assert "spa/react ok" in result.stdout


def test_m36_board_marks_kits_complete(progress_client: TestClient) -> None:
    data = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in data["milestones"]}
    assert by_id["M36"]["status"] == "complete"
    assert any("progress:kits" in p for p in by_id["M36"]["proof"])


def test_m36_docs_and_stubs_exist() -> None:
    assert (DOCS / "starter-kits.md").is_file()
    docs = (DOCS / "starter-kits.md").read_text(encoding="utf-8")
    assert "Forge" in docs or "forge" in docs.lower()
    assert "--kit" in docs
    kits = ROOT / "src" / "almasix" / "installer" / "stubs" / "kits"
    assert (kits / "web" / "_common").is_dir()
    assert (kits / "api" / "_common").is_dir()
    assert (kits / "spa" / "react").is_dir()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "starter-kits" in sidebar


def test_m36_kit_catalogue() -> None:
    from almasix.installer.kits import KIT_NAMES, find_kit

    assert find_kit("web").kind == "web"
    assert find_kit("api").force_stack == "none"
    assert find_kit("react").frontend == "react"
    assert find_kit("vue").frontend == "vue"
    assert find_kit("svelte").frontend == "svelte"
    assert "none" in KIT_NAMES
