"""M41 smoke — relationship docs, the ORM tour, and the milestone board."""

from __future__ import annotations

import importlib
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


def test_m41_docs_cover_the_laravel_sections() -> None:
    page = (
        ROOT / "website" / "src" / "content" / "docs" / "articulate" / "relationships.md"
    ).read_text(encoding="utf-8")
    for heading in (
        "## Has one of many",
        "## Default models",
        "## Chaperone",
        "## Many to many: the intermediate table",
        "## Custom polymorphic types",
        "## Querying relationship existence",
        "## Aggregating related models",
        "## Eager loading",
        "## Touching parent timestamps",
    ):
        assert heading in page, heading


def test_m41_orm_tour_exercises_the_new_relationship_surface(
    progress_client: TestClient,
) -> None:
    features = progress_client.get("/api/orm").json()["features"]

    # Pivot rows arrive as objects rather than flattened pivot_* attributes.
    assert features["belongs_to_many_pivot"]["sample_roles"][0]["pivot_level"] is not None

    assert features["one_of_many"]["latest_post"]
    assert features["default_models"]["orphan_author"] == "Ghost Writer"
    assert features["chaperone"]["child_sees_parent"]

    sums = features["aggregates"]["sums"]
    assert any(row["posts_exists"] for row in sums)
    assert any(row["posts_sum_views"] for row in sums)

    assert features["existence_queries"]["where_relation"]
    assert features["existence_queries"]["with_where_has"]["published_posts"]


def test_m41_board_marks_relationships_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}

    assert by_id["M40"]["status"] == "complete"
    assert by_id["M41"]["status"] == "complete"
    assert by_id["M41"]["name"] == "Relationship exhaust"
    assert by_id["M42"]["status"] == "next"


def test_m41_board_covers_every_planned_milestone(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    ids = {m["id"] for m in board["milestones"]}

    # The board tracks the whole plan, not just the milestones that shipped first.
    assert {f"M{n}" for n in range(49)} == ids
    assert board["total"] == 49
    assert board["completed"] + board["in_progress"] + board["planned"] == board["total"]


def test_m41_board_is_honest_about_partial_milestones(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {m["id"]: m for m in board["milestones"]}

    # M5's ladder shipped but its pages are not exhausted, and M30 is one part in.
    assert by_id["M5"]["status"] == "partial"
    assert by_id["M30"]["status"] == "partial"
    assert board["in_progress"] == 2


def test_m41_board_page_renders_the_new_rows(progress_client: TestClient) -> None:
    page = progress_client.get("/progress").text

    assert "Relationship exhaust" in page
    assert "Avalon Language Server" in page
    assert "in progress" in page
    assert "@section" not in page
