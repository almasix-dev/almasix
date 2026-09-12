"""M56 smoke — validation exhaust demo, board, docs parity."""

from __future__ import annotations

import pathlib
import re

import pytest
from typer.testing import CliRunner

from almasix.console.kernel import ConsoleKernel
from almasix.smith.cli import app as smith_app
from almasix.validation import LARAVEL_RULES
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = pytest.mark.smoke

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROGRESS = ROOT / "examples" / "progress"
DOCS = ROOT / "website" / "src" / "content" / "docs" / "validation.md"
PARITY = ROOT / "docs" / "VALIDATION_PARITY.md"


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    kernel = ConsoleKernel.from_cwd(PROGRESS)
    kernel.load_console_routes()
    kernel.register_on_typer(smith_app)
    return PROGRESS


def test_progress_validation_demo(progress_cwd: pathlib.Path) -> None:
    result = CliRunner().invoke(smith_app, ["progress:validation"])
    output = result.stdout + (result.stderr or "")
    assert result.exit_code == 0, output
    assert f"available rules → {len(LARAVEL_RULES)}" in output
    assert "validation demo ok" in output


def test_m56_board_marks_validation_complete(progress_cwd: pathlib.Path) -> None:
    from fastapi.testclient import TestClient

    import bootstrap.app as module

    client = TestClient(module.asgi, raise_server_exceptions=False)
    board = client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}
    assert by_id["M56"]["status"] == "complete"
    assert any("progress:validation" in p for p in by_id["M56"]["proof"])
    assert any("112" in p for p in by_id["M56"]["proof"])

    ok = client.post(
        "/api/validate/dsl",
        json={"email": "ada@example.com", "name": "Ada"},
    )
    assert ok.status_code == 200
    assert ok.json()["via"] == "dsl"

    bad = client.post("/api/validate/dsl", json={"email": "nope", "name": "A"})
    assert bad.status_code == 422


def test_m56_docs_and_parity_cover_every_rule() -> None:
    docs = DOCS.read_text(encoding="utf-8")
    headings = set(re.findall(r"^### ([a-z0-9_]+)\s*$", docs, re.M))
    assert set(LARAVEL_RULES) <= headings
    parity = PARITY.read_text(encoding="utf-8")
    for name in LARAVEL_RULES:
        assert f"`{name}`" in parity
