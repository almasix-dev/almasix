"""M44 smoke — multi-engine demo, support matrix docs, and the board."""

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


def test_m44_demo_command_probes_the_active_engine() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:engines"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    for line in (
        "active engine ->",
        "CI executes -> sqlite, pgsql, mysql",
        "Schema.create ->",
        "upsert ->",
        "where_json_length ->",
        "where_json_contains ->",
        "lock_for_update ->",
        "nested savepoint ->",
        "paginate ->",
        "cursor_paginate ->",
        "multi-engine database demo ok",
    ):
        assert line in out, line


def test_m44_ci_matrix_covers_the_claimed_engines() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "orm-engines:" in ci
    assert "ALMASIX_TEST_DB" in ci
    assert "test_m44_conformance.py" in ci
    for engine in ("sqlite", "pgsql", "mysql"):
        assert f"engine: {engine}" in ci, engine
    assert "postgres:16" in ci or "postgres:16-alpine" in ci
    assert "mysql:8" in ci


def test_m44_docs_publish_an_honest_support_matrix() -> None:
    engines = (ROOT / "website" / "src" / "content" / "docs" / "database" / "engines.md").read_text(
        encoding="utf-8"
    )
    for heading in (
        "## Engines Almasix claims",
        "## Feature matrix",
        "## What SQLite cannot do",
        "## Running the suite against another engine",
    ):
        assert heading in engines, heading
    for phrase in (
        "Executed in CI",
        "compile-only",
        "Native upsert",
        "Row locks",
        "Transactional DDL",
        "ALMASIX_TEST_DB",
    ):
        assert phrase in engines, phrase


def test_m44_board_marks_multi_engine_ci_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}

    assert by_id["M44"]["status"] == "complete"
    assert "smith progress:engines" in by_id["M44"]["proof"]
    assert any("pgsql" in item and "mysql" in item for item in by_id["M44"]["proof"])


def test_m44_readme_names_the_engines_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")
    assert "smith progress:engines" in readme
    assert "M44" in readme
