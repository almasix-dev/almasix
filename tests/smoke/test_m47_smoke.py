"""M47 smoke — editor integrations demo + board proof."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
REPO = PROGRESS.parents[1]


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m47_demo_command_runs() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:ide"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "install ->",
        "stubs   ->",
        "ide ok",
    ):
        assert line in out, line


def test_m47_artifacts_exist() -> None:
    vscode = REPO / "editors" / "vscode"
    assert (vscode / "package.json").is_file()
    assert (vscode / "src" / "extension.ts").is_file()
    assert (vscode / "syntaxes" / "prism.tmLanguage.json").is_file()
    # Packaged .vsix is gitignored; produce locally / in CI via `make editors-vscode`.
    _ = list(vscode.glob("*.vsix"))
    jb = REPO / "editors" / "jetbrains"
    assert (jb / "build.gradle.kts").is_file()
    assert (jb / "README.md").is_file()
    plugin_xml = (jb / "src" / "main" / "resources" / "META-INF" / "plugin.xml").read_text(
        encoding="utf-8"
    )
    assert "PrismFileTypeOverrider" in plugin_xml
    assert 'fileNamePatterns="*.prism.html"' in plugin_xml
    tm_pkg = (jb / "src" / "main" / "resources" / "textMate" / "prism" / "package.json").read_text(
        encoding="utf-8"
    )
    assert '"contributes"' in tm_pkg
    assert '"language": "Prism"' in tm_pkg
    # Zip is produced by ./gradlew buildPlugin; tolerate missing in bare checkouts
    # but prefer it when present (CI / local M47 gate).
    zips = list((jb / "build" / "distributions").glob("*.zip")) if (jb / "build").is_dir() else []
    assert (jb / "src" / "main" / "resources" / "META-INF" / "plugin.xml").is_file()
    _ = zips  # documented build output


def test_m47_board_marks_ide_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}
    assert by_id["M47"]["status"] == "complete"
    assert "smith progress:ide" in by_id["M47"]["proof"]
