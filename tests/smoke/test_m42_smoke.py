"""M42 smoke — the query builder demo, the database docs, and the board."""

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


def test_m42_demo_command_exercises_the_builder_and_the_layer_under_it() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:queries"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    for line in (
        "where_any ->",
        "where_past ->",
        "where_exists ->",
        "where_not ->",
        "join_sub ->",
        "union ->",
        "having_between ->",
        "where_json_length ->",
        "json path where ->",
        "where_json_contains ->",
        "JSON update ->",
        "insert_or_ignore ->",
        "with_attributes ->",
        "sole ->",
        "implode ->",
        "transaction_level ->",
        "after_commit ->",
        "DB.pretend ->",
        "to_sql ->",
        "to_raw_sql ->",
        "get_bindings ->",
        "DB.listen heard",
        "query builder demo ok",
    ):
        assert line in out, line

    # The debugging pair is only worth having if it is a pair.
    assert "WHERE users.name = ?" in out
    assert "WHERE users.name = 'Ada'" in out


def test_m42_docs_cover_the_laravel_sections() -> None:
    docs = ROOT / "website" / "src" / "content" / "docs" / "database"

    queries = (docs / "queries.md").read_text(encoding="utf-8")
    for heading in (
        "## Running database queries",
        "### Chunking results",
        "## Raw expressions",
        "## Joins",
        "### Advanced join clauses",
        "### Subquery joins",
        "### Lateral joins",
        "## Unions",
        "## Basic where clauses",
        "### Where any / all / none clauses",
        "### JSON where clauses",
        "### Logical grouping",
        "## Advanced where clauses",
        "### Where exists clauses",
        "### Full text where clauses",
        "## Ordering, grouping, limit and offset",
        "## Conditional clauses",
        "### Upserts",
        "### Updating JSON columns",
        "### Increment and decrement",
        "## Delete statements",
        "## Pessimistic locking",
        "## Reusable query components",
        "## Debugging",
    ):
        assert heading in queries, heading

    index = (docs / "index.md").read_text(encoding="utf-8")
    for heading in (
        "### Read and write connections",
        "### Pooled connections",
        "## Running SQL queries",
        "### Using multiple connections",
        "### Listening for query events",
        "### Monitoring cumulative query time",
        "## Database transactions",
        "### Handling deadlocks",
        "### Manually using transactions",
        "## Connecting to the database CLI",
        "## Inspecting your databases",
        "## Monitoring your databases",
    ):
        assert heading in index, heading


def test_m42_board_marks_the_query_builder_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}

    assert by_id["M42"]["status"] == "complete"
    assert "smith progress:queries" in by_id["M42"]["proof"]
    # M5's query builder is what M42 closed; M43 closed the schema layer after it.
    assert any("M42" in proof for proof in by_id["M5"]["proof"])


def test_m42_readme_points_at_the_demo(progress_client: TestClient) -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")

    assert "| **M42** | `smith progress:queries`" in readme
    assert "\nsmith progress:queries\n" in readme
    assert "exhausted in M42" in readme
