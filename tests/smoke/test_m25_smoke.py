"""M25 smoke — document docs, the generators and commands, the route, the board."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "website" / "src" / "content" / "docs" / "articulate" / "documents"
runner = CliRunner()


@pytest.fixture()
def progress_cwd(monkeypatch: pytest.MonkeyPatch) -> Path:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    from almasix.console.kernel import ConsoleKernel

    ConsoleKernel.from_cwd(PROGRESS).register_on_typer(smith_app)
    return PROGRESS


@pytest.fixture()
def progress_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    module = importlib.import_module("bootstrap.app")
    return TestClient(module.asgi)


def test_m25_docs_are_broken_down_and_in_the_sidebar() -> None:
    for name in (
        "index.md",
        "getting-started.md",
        "querying.md",
        "relationships.md",
        "indexes.md",
        "aggregations.md",
        "compared.md",
    ):
        assert (DOCS / name).is_file(), name

    sidebar = (ROOT / "website" / "astro.config.mjs").read_text(encoding="utf-8")
    for slug in (
        "articulate/documents",
        "articulate/documents/getting-started",
        "articulate/documents/querying",
        "articulate/documents/relationships",
        "articulate/documents/indexes",
        "articulate/documents/aggregations",
        "articulate/documents/compared",
        "database/documents",
    ):
        assert slug in sidebar, slug

    database = ROOT / "website" / "src" / "content" / "docs" / "database"
    assert (database / "documents.md").is_file()
    getting_started = (database / "index.md").read_text(encoding="utf-8")
    assert "/database/documents/" in getting_started
    assert "/articulate/documents/" in getting_started
    engines = (database / "engines.md").read_text(encoding="utf-8")
    assert "### Document stores" in engines


def test_m25_compared_page_is_an_honest_feature_map() -> None:
    compared = (DOCS / "compared.md").read_text(encoding="utf-8")
    assert "Document store feature map" in compared
    for heading in (
        "## Core document ORM",
        "## Framework integrations often bundled elsewhere",
        "## Deliberate design choices",
    ):
        assert heading in compared, heading
    for phrase in (
        "**Shipped**",
        "**Partial**",
        "**Missing**",
        "MongoDB cache driver",
        "GridFS",
        "Scout",
        "Vector / Atlas Search",
        "Multi-document transactions",
        "memory` is a real store",
    ):
        assert phrase in compared, phrase

    # User docs stay framework-agnostic; no Laravel URLs or Eloquent framing.
    assert "laravel.com" not in compared.lower()
    assert "Eloquent" not in compared
    index = (DOCS / "index.md").read_text(encoding="utf-8")
    assert "Laravel has no first-party NoSQL" not in index


def test_m25_the_mongodb_extra_is_declared() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mongodb = ["motor' in pyproject


def test_m25_a_scaffolded_app_configures_a_document_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m25_scaffold", destination=tmp_path / "m25_scaffold")
    monkeypatch.chdir(root)
    config = (root / "config" / "database.py").read_text(encoding="utf-8")
    assert '"driver": "mongodb"' in config
    assert '"driver": "memory"' in config


def test_m25_make_document_writes_both_shapes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from almasix.installer.scaffold import scaffold_app

    root = scaffold_app("m25_make", destination=tmp_path / "m25_make")
    monkeypatch.chdir(root)

    assert runner.invoke(smith_app, ["make:document", "Article", "-f"]).exit_code == 0
    document = (root / "app" / "models" / "article.py").read_text(encoding="utf-8")
    assert "class Article(HasFactory, Document):" in document
    assert "indexes" in document
    factory = (root / "database" / "factories" / "article_factory.py").read_text(encoding="utf-8")
    assert "model = Article" in factory

    assert runner.invoke(smith_app, ["make:document", "Address", "-e"]).exit_code == 0
    embed = (root / "app" / "models" / "address.py").read_text(encoding="utf-8")
    assert "class Address(EmbeddedDocument):" in embed


def test_m25_documents_index_and_show(progress_cwd: Path) -> None:
    del progress_cwd
    pretend = runner.invoke(smith_app, ["documents:index", "--pretend"])
    output = pretend.stdout + pretend.stderr
    assert pretend.exit_code == 0, output
    assert "Activity [activities]" in output
    assert "action asc" in output

    created = runner.invoke(smith_app, ["documents:index", "--model", "Activity"])
    assert created.exit_code == 0, created.stdout + created.stderr

    shown = runner.invoke(smith_app, ["documents:show", "--database", "documents"])
    assert shown.exit_code == 0, shown.stdout + shown.stderr
    assert "memory [documents]" in shown.stdout + shown.stderr

    ambiguous = runner.invoke(smith_app, ["documents:show"])
    assert ambiguous.exit_code == 1
    assert "name one with --database" in ambiguous.stdout + ambiguous.stderr


def test_m25_progress_documents_command(progress_cwd: Path) -> None:
    del progress_cwd
    result = runner.invoke(smith_app, ["progress:documents"])
    output = result.stdout + result.stderr
    assert result.exit_code == 0, output
    assert "documents demo ok" in output
    assert "store -> memory [documents], collection activities" in output
    assert "embed -> Nairobi, KE" in output
    assert "refusal -> join() is SQL-only" in output
    assert "parity -> Eloquent-on-collections shipped" in output


def test_m25_route_returns_a_document_tour(progress_client: TestClient) -> None:
    response = progress_client.get("/api/documents")
    assert response.status_code == 200
    payload = response.json()
    assert payload["store"]["driver"] == "memory"
    assert payload["store"]["collection"] == "activities"
    assert payload["documents"]["count"] == 4
    assert payload["embedded"] == {"city": "Nairobi", "country": "KE"}
    assert payload["reference"]["user"] == "Ada"
    assert payload["soft_deletes"]["with_trashed"] >= payload["soft_deletes"]["visible"]
    assert "no joins" in payload["sql_only"]


def test_m25_board_marks_documents_complete(progress_cwd: Path) -> None:
    del progress_cwd
    from app.http.controllers.progress_controller import _milestones

    m25 = next(m for m in _milestones() if m["id"] == "M25")
    assert m25["status"] == "complete"
    assert any("progress:documents" in proof for proof in m25["proof"])
    assert any("L13 Mongo" in proof or "compared" in proof for proof in m25["proof"])
