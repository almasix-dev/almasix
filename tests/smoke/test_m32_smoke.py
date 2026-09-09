"""M32 smoke — the installer demo, the docs, and the board."""

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


def test_m32_demo_command_scaffolds_every_stack_and_migrates() -> None:
    result = subprocess.run(
        [sys.executable, "smith", "progress:install"],
        cwd=PROGRESS,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    for line in (
        "stack tailwind",
        "stack bootstrap",
        "stack plain",
        "stack none       -> no Node",
        "database sqlite   -> DB_CONNECTION=sqlite, sqlite file: True",
        "database pgsql    -> DB_CONNECTION=pgsql, sqlite file: False",
        "0001_01_01_000000_create_users_table.py",
        "0001_01_01_000001_create_cache_table.py",
        "0001_01_01_000002_create_jobs_table.py",
        "migrate -> exit 0",
        "no-interaction -> stack=tailwind, database=sqlite",
        "stub:publish --scaffold ->",
        "installer demo ok",
    ):
        assert line in out, line

    # The default migrations create what the framework itself reads, and the
    # generated application answers a request afterwards.
    assert "cache, cache_locks, failed_jobs, jobs, migrations" in out
    assert "welcome page -> 200 True" in out


def test_m32_docs_cover_the_installer_and_the_stacks() -> None:
    docs = ROOT / "website" / "src" / "content" / "docs"

    installation = (docs / "installation.mdx").read_text(encoding="utf-8")
    for heading in (
        "## Every question, and its flag",
        "## Frontend stacks",
        "## Databases",
        "## The default migrations",
        "## Scaffolding from your own stubs",
    ):
        assert heading in installation, heading
    for flag in ("--stack", "--database", "--no-tests", "--git", "--install", "--stubs", "--migrate"):
        assert flag in installation, flag
    for command in ("cache:table", "queue:table", "queue:failed-table", "session:table"):
        assert command in installation, command

    bundling = (docs / "asset-bundling.md").read_text(encoding="utf-8")
    assert "## `@vite`" in bundling
    assert "### `@viteReactRefresh`" in bundling
    assert "public/hot" in bundling


def test_m32_board_marks_the_installer_complete(progress_client: TestClient) -> None:
    board = progress_client.get("/api/progress").json()
    by_id = {milestone["id"]: milestone for milestone in board["milestones"]}

    assert by_id["M32"]["status"] == "complete"
    assert "smith progress:install" in by_id["M32"]["proof"]


def test_m32_readme_points_at_the_demo() -> None:
    readme = (PROGRESS / "README.md").read_text(encoding="utf-8")

    assert "| **M32** | `smith progress:install`" in readme
    assert "\nsmith progress:install\n" in readme


def test_m32_a_scaffolded_app_ships_the_tables_the_framework_reads(tmp_path: Path) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("smoke_tables", destination=tmp_path / "smoke_tables")
    migrations = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((root / "database" / "migrations").glob("*.py"))
    )

    for table in (
        "users",
        "password_reset_tokens",
        "sessions",
        "cache",
        "cache_locks",
        "jobs",
        "failed_jobs",
    ):
        assert f'Schema.create("{table}"' in migrations, table
