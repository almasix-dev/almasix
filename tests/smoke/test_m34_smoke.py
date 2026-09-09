"""M34 smoke — security headers, CORS, maintenance mode, docs, and the board."""

from __future__ import annotations

import importlib
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


def test_m34_demo_command_covers_headers_cors_and_maintenance() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:security"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "X-Content-Type-Options       nosniff",
        "X-Frame-Options              SAMEORIGIN",
        "csp_nonce()",
        "paths              -> ['api/*', 'signet/csrf-cookie']",
        "'secret': 'demo-secret'",
        "'retry': 60",
        "marker after up     -> gone",
        "security demo ok",
    ):
        assert line in out, line


def test_m34_a_web_page_carries_security_headers(progress_client: TestClient) -> None:
    response = progress_client.get("/")
    assert response.status_code == 200
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert response.headers.get("x-frame-options") == "SAMEORIGIN"
    assert response.headers.get("referrer-policy") == "strict-origin-when-cross-origin"


def test_m34_down_and_up_round_trip_over_http(progress_client: TestClient) -> None:
    down = subprocess.run(
        [sys.executable, "smith", "down", "--secret=smoke", "--retry=15"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    assert down.returncode == 0, down.stdout + down.stderr
    try:
        denied = progress_client.get("/api/health")
        assert denied.status_code == 503
        assert denied.headers.get("retry-after") == "15"

        granted = progress_client.get("/api/health?secret=smoke", follow_redirects=False)
        assert granted.status_code == 302
        assert progress_client.get("/api/health").status_code == 200
    finally:
        up = subprocess.run(
            [sys.executable, "smith", "up"],
            cwd=PROGRESS,
            capture_output=True,
            text=True,
            check=False,
        )
        assert up.returncode == 0, up.stdout + up.stderr


def test_m34_docs_cover_headers_cors_and_maintenance() -> None:
    docs = (ROOT / "website" / "src" / "content" / "docs" / "security.md").read_text(
        encoding="utf-8"
    )
    for topic in (
        "X-Content-Type-Options",
        "csp_nonce",
        "config/cors.py",
        "smith down",
        "--secret",
        "Retry-After",
    ):
        assert topic in docs, topic


def test_m34_board_marks_security_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}
    assert by_id["M34"]["status"] == "complete"
    assert "smith progress:security" in by_id["M34"]["proof"]


def test_m34_readme_points_at_the_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")
    assert "| **M34** | `smith progress:security`" in readme
    assert "\nsmith progress:security\n" in readme
