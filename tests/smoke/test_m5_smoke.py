"""M5 smoke — generators, scaffold database config, living example models."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

runner = CliRunner()


def test_m5_s1_scaffold_ships_database_config(tmp_path: Path) -> None:
    root = scaffold_app("m5_db", destination=tmp_path / "m5_db")
    assert (root / "config" / "database.py").is_file()
    env = (root / ".env").read_text(encoding="utf-8")
    assert "DB_CONNECTION=sqlite" in env
    assert (root / "database" / "migrations").is_dir()
    assert (root / "database" / "seeders" / "database_seeder.py").is_file()
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "database/*.sqlite" in gitignore


def test_m5_s1b_progress_keeps_scaffold_baseline(tmp_path: Path) -> None:
    """Progress must remain a superset of `almasix new` so scaffold gaps stay visible."""
    scaffold = scaffold_app("baseline", destination=tmp_path / "baseline")
    progress = Path(__file__).resolve().parents[2] / "examples" / "progress"
    # Content may diverge (demo routes, README); paths must exist.
    skip_names = {".env", ".gitkeep"}  # .env local; .gitkeep replaced by real migrations/views
    missing: list[str] = []
    for path in scaffold.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(scaffold)
        if relative.name in skip_names:
            continue
        if not (progress / relative).exists():
            missing.append(relative.as_posix())
    assert missing == [], f"progress missing scaffold files: {missing}"
    assert (progress / "database" / "migrations").is_dir()
    assert list((progress / "database" / "migrations").glob("*create_demo_tables.py"))
    assert (progress / "database" / "seeders" / "database_seeder.py").is_file()
    assert (progress / "database" / "seeders" / "demo_seeder.py").is_file()


def test_m5_s2_make_model_and_migration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("m5_make", destination=tmp_path / "m5_make")
    monkeypatch.chdir(root)
    result = runner.invoke(smith_app, ["make:model", "Post", "-m"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    assert (root / "app" / "models" / "post.py").is_file()
    migrations = list((root / "database" / "migrations").glob("*create_posts_table.py"))
    assert len(migrations) == 1


def test_m5_s3_progress_posts_eager_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    from fastapi.testclient import TestClient

    from tests.support import purge_generated_app_modules, without_base_path

    root = Path(__file__).resolve().parents[2] / "examples" / "progress"
    db_path = tmp_path / "progress_smoke.sqlite"
    purge_generated_app_modules()
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("APP_NAME", raising=False)
    without_base_path(monkeypatch)
    monkeypatch.setenv("DB_CONNECTION", "sqlite")
    monkeypatch.setenv("DB_DATABASE", str(db_path))
    try:
        module = importlib.import_module("bootstrap.app")
        client = TestClient(module.asgi)

        posts = client.get("/api/posts")
        assert posts.status_code == 200
        body = posts.json()
        assert body["count"] >= 1
        assert body["posts"][0]["author"]["email"]

        tour = client.get("/api/orm")
        assert tour.status_code == 200
        features = tour.json()["features"]
        assert features["eager_load"]["sample_author"]
        assert features["soft_deletes"]["trashed_count"] >= 1
        assert features["belongs_to_many_pivot"]["sample_roles"]

        users = client.get("/api/users")
        assert users.status_code == 200
        assert users.json()["count"] >= 2

        pages = client.get("/api/posts/pages?page=1&per_page=1")
        assert pages.status_code == 200
        assert pages.json()["per_page"] == 1

        relation = client.get("/api/users/1/posts")
        assert relation.status_code == 200
        assert relation.json()["unloaded_attribute_raises"] is True

        upsert = client.post(
            "/api/users/upsert",
            json={"email": "ada@almasix.dev", "name": "Ada Lovelace"},
        )
        assert upsert.status_code == 200
        assert upsert.json()["user"]["name"] == "Ada Lovelace"

        comments = client.get("/api/posts/1/comments")
        assert comments.status_code == 200
        assert comments.json()["comments"]
    finally:
        purge_generated_app_modules()
