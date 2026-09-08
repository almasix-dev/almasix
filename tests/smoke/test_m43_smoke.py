"""M43 smoke — the schema demo, the migration and pagination docs, and the board."""

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


def test_m43_demo_command_builds_alters_migrates_and_paginates() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:schema"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    for line in (
        "Schema.create ->",
        "Schema.table ->",
        "Schema.rename ->",
        "DB.pretend ->",
        "has_columns ->",
        "column_type ->",
        "get_indexes ->",
        "get_foreign_keys ->",
        "migrate --pretend ->",
        "migrate --step ->",
        "status ->",
        "migrate:rollback --step=1 ->",
        "paginate ->",
        "simple_paginate ->",
        "cursor_paginate ->",
        "links() ->",
        "schema, migration, and pagination demo ok",
    ):
        assert line in out, line

    # The three paginators have to agree about where the second page starts.
    assert "[1, 2, 3] then [4, 5, 6]" in out
    assert "?cursor=" in out


def test_m43_docs_cover_the_laravel_sections() -> None:
    docs = ROOT / "website" / "src" / "content" / "docs" / "database"

    migrations = (docs / "migrations.md").read_text(encoding="utf-8")
    for heading in (
        "### Squashing migrations",
        "### Setting the connection",
        "### Skipping a migration",
        "### Transactions",
        "## Running migrations",
        "### Forcing migrations to run in production",
        "### Rolling back",
        "### Migration status",
        "## Tables",
        "### Updating tables",
        "### Renaming and dropping",
        "### Inspecting the schema",
        "## Columns",
        "### Available column types",
        "### Column modifiers",
        "### Modifying columns",
        "### Renaming and dropping columns",
        "## Indexes",
        "### Foreign key constraints",
        "## Events",
    ):
        assert heading in migrations, heading

    pagination = (docs / "pagination.md").read_text(encoding="utf-8")
    for heading in (
        "### Paginating query builder results",
        "### Paginating Articulate results",
        "### Simple pagination",
        "### Cursor pagination",
        "## Displaying results",
        "### Appending query string values",
        "### Converting to JSON",
        "## Paginator instance methods",
    ):
        assert heading in pagination, heading


def test_m43_board_marks_the_schema_layer_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}

    assert by_id["M43"]["status"] == "complete"
    assert "smith progress:schema" in by_id["M43"]["proof"]

    # M43 is what finished M5: the query builder came in M42, the schema here.
    assert by_id["M5"]["status"] == "complete"


def test_m43_readme_points_at_the_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")

    assert "| **M43** | `smith progress:schema`" in readme
    assert "\nsmith progress:schema\n" in readme
