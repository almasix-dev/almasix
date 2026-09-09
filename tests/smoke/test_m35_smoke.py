"""M35 smoke — RateLimiter, throttle middleware, login throttling, docs, board."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.http import RateLimiter
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


def test_m35_demo_command_covers_facade_throttle_and_login() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:rate-limiting"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    for line in (
        "attempt #3 (over)   -> False",
        "parse_rate('60,1')  -> 60 / 60s",
        "RateLimiter.for_('api') registered  -> True",
        "four hits            -> [200, 200, 200, 429]",
        "raise_for            -> 429",
        "attempt_login(...)",
        "rate-limiting demo ok",
    ):
        assert line in out, line


def test_m35_throttle_demo_route_refuses_the_fourth_hit(
    progress_client: TestClient,
) -> None:
    for suffix in ("127.0.0.1", "testclient", "0.0.0.0"):
        RateLimiter.clear(f"progress|progress:{suffix}")
    statuses = [progress_client.get("/api/throttle-demo").status_code for _ in range(4)]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3] == 429


def test_m35_docs_cover_limiter_throttle_and_login() -> None:
    docs = (ROOT / "website" / "src" / "content" / "docs" / "rate-limiting.md").read_text(
        encoding="utf-8"
    )
    for topic in (
        "RateLimiter",
        "throttle:api",
        "Limit.per_minute",
        "X-RateLimit-Limit",
        "Retry-After",
        "LoginRateLimiter",
        "attempt_login",
        "cache.limiter",
        "throttle_api",
    ):
        assert topic in docs, topic


def test_m35_board_marks_rate_limiting_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}
    assert by_id["M35"]["status"] == "complete"
    assert "smith progress:rate-limiting" in by_id["M35"]["proof"]


def test_m35_readme_points_at_the_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")
    assert "| **M35** | `smith progress:rate-limiting`" in readme
    assert "\nsmith progress:rate-limiting\n" in readme
