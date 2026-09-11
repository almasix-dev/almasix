"""M54 smoke — almasix.conduit demo, wire update, board, docs."""

from __future__ import annotations

import importlib
import re
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
    module = importlib.import_module("bootstrap.app")
    app = module.application
    app._asgi = None
    module.asgi = app.asgi
    return TestClient(module.asgi, raise_server_exceptions=False)


def test_m54_progress_conduit_command(progress_cwd: Path) -> None:
    result = runner.invoke(smith_app, ["progress:conduit"])
    assert result.exit_code == 0, result.stdout + result.stderr
    assert "conduit ok" in result.stdout


def test_m54_conduit_demo_page(progress_client: TestClient) -> None:
    response = progress_client.get("/conduit")
    assert response.status_code == 200
    assert b"wire:id=" in response.content
    assert b"almasix.conduit" in response.content


def test_m54_conduit_update_endpoint(progress_client: TestClient) -> None:
    from almasix.conduit import Conduit
    from almasix.conduit.mechanism import snapshot
    from app.conduit.counter import Counter

    page = progress_client.get("/conduit")
    assert page.status_code == 200
    # Unsigned posts must be rejected (signed:relative middleware).
    # CSRF may fire first (419) when no token; with a token, signature yields 403.
    bare = progress_client.post(
        "/conduit/update",
        json={"fingerprint": {"name": "counter"}, "serverMemo": {"data": {}, "checksum": ""}},
        headers={"Content-Type": "application/json", "X-CSRF-TOKEN": "not-a-real-token"},
    )
    assert bare.status_code in {403, 419}

    m_ep = re.search(rb'conduit-endpoint" content="([^"]+)"', page.content)
    assert m_ep, "demo page must expose signed conduit-endpoint meta"
    endpoint = m_ep.group(1).decode()
    assert "signature=" in endpoint

    # CSRF token + signed URL, but prove unsigned path still fails signature when CSRF ok
    token = None
    m = re.search(rb'csrf-token" content="([^"]+)"', page.content)
    if m:
        token = m.group(1).decode()
    unsigned_authed = progress_client.post(
        "/conduit/update",
        json={"fingerprint": {"name": "counter"}, "serverMemo": {"data": {}, "checksum": ""}},
        headers={"Content-Type": "application/json", "X-CSRF-TOKEN": token or ""},
    )
    assert unsigned_authed.status_code == 403

    Conduit.register("counter", Counter)
    c = Conduit.component("counter")
    c.conduit_id = "smoke-1"
    c.mount()
    snap = snapshot(c)
    payload = {
        **snap,
        "updates": [],
        "calls": [{"method": "increment", "params": []}],
    }
    headers = {"Content-Type": "application/json", "X-CSRF-TOKEN": token or ""}
    response = progress_client.post(endpoint, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("error") is None
    assert data["serverMemo"]["data"]["count"] == 1
    assert "html" in data.get("effects", {}) or "data" in data.get("effects", {})
    assert "signature=" in data.get("effects", {}).get("endpoint", "")


def test_m54_board_marks_conduit_complete(progress_client: TestClient) -> None:
    data = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in data["milestones"]}
    assert by_id["M54"]["status"] == "complete"
    assert "conduit" in by_id["M54"]["name"].lower()
    assert any("progress:conduit" in p for p in by_id["M54"]["proof"])


def test_m54_docs_exist() -> None:
    assert (DOCS / "conduit.md").is_file()
    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    assert "conduit" in sidebar
    docs = (DOCS / "conduit.md").read_text(encoding="utf-8")
    assert "signed update" in docs.lower() or "signed:relative" in docs
    matrix = docs.split("## Livewire 4 parity matrix", 1)[1].split("## ", 1)[0]
    assert "| partial |" not in matrix and "| planned |" not in matrix
    from almasix.conduit.parity import parity_summary

    summary = parity_summary()
    assert summary["partial"] == 0 and summary["planned"] == 0
    assert summary["complete"] == sum(summary.values())
    import importlib.util

    assert importlib.util.find_spec("almasix.conduit") is not None
