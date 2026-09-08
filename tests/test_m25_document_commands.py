"""M25 — the `documents:index` and `documents:show` console commands.

These are synchronous, like the commands themselves: each drives its own event
loop, so setup and assertions run in separate ones. The store is in-process, so
it survives across those loops.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from almasix.console.commands.documents import DocumentsIndexCommand, DocumentsShowCommand
from almasix.console.kernel import ConsoleKernel
from almasix.framework import Application
from almasix.orm import DatabaseManager, Document, set_manager


class Article(Document):
    connection = "docs"
    collection = "articles"
    fillable = ("title",)

    indexes = (
        {"keys": [("title", 1)], "unique": True, "name": "title_unique"},
        {"keys": [("created_at", -1)]},
    )


class Note(Document):
    connection = "docs"
    fillable = ("body",)


def run_async(operation: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    return asyncio.run(operation())


@pytest.fixture
def documents() -> Any:
    manager = DatabaseManager(
        {
            "default": "sqlite",
            "connections": {
                "sqlite": {"driver": "sqlite", "database": ":memory:"},
                "docs": {"driver": "memory"},
            },
        }
    )
    set_manager(manager)
    yield manager
    set_manager(None)


@pytest.fixture
def app_models() -> Any:
    """Stand in for the app's `app.models` package."""
    package = types.ModuleType("app.models")
    package.__path__ = []
    package.Article = Article
    package.Note = Note
    package.Document = Document  # the base class must be skipped
    app = types.ModuleType("app")
    app.__path__ = []
    sys.modules["app"] = app
    sys.modules["app.models"] = package
    yield package
    sys.modules.pop("app.models", None)
    sys.modules.pop("app", None)


def run(tmp_path: Path, command: type, name: str, argv: list[str]) -> int:
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(command)
    return kernel.run_argv(name, argv)


def index(tmp_path: Path, argv: list[str] | None = None) -> int:
    return run(tmp_path, DocumentsIndexCommand, "documents:index", argv or [])


def show(tmp_path: Path, argv: list[str] | None = None) -> int:
    return run(tmp_path, DocumentsShowCommand, "documents:show", argv or [])


# --- documents:index --------------------------------------------------------


def test_index_creates_every_declared_index(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    assert index(tmp_path) == 0
    output = capsys.readouterr().out
    assert "Article [articles]: title asc (unique)" in output
    assert "created_at desc" in output
    assert "2 index(es) created." in output

    names = run_async(lambda: documents.store("docs").indexes("articles"))
    assert [entry["name"] for entry in names] == ["title_unique", "created_at_-1"]


def test_index_can_say_what_it_would_do(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    assert index(tmp_path, ["--pretend"]) == 0
    assert "would be created" in capsys.readouterr().out
    assert run_async(lambda: documents.store("docs").indexes("articles")) == []


def test_index_can_be_told_which_document(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    assert index(tmp_path, ["--model", "Article"]) == 0
    output = capsys.readouterr().out
    assert "Article" in output
    assert "Note" not in output


def test_index_names_a_document_it_cannot_find(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    assert index(tmp_path, ["--model", "Nothing"]) == 0
    captured = capsys.readouterr()
    assert "Document [Nothing] was not found" in captured.out + captured.err
    assert "No document models found." in captured.out


def test_index_says_so_when_nothing_declares_an_index(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    assert index(tmp_path, ["--model", "Note"]) == 0
    assert "No document model declares any indexes." in capsys.readouterr().out


def test_index_reports_a_store_that_refuses(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("the store said no")

    monkeypatch.setattr(documents.store("docs"), "create_index", refuse)
    assert index(tmp_path, ["--model", "Article"]) == 1
    captured = capsys.readouterr()
    assert "Article: the store said no" in captured.out + captured.err


def test_index_without_an_app_finds_nothing(tmp_path: Path, documents: Any, capsys: Any) -> None:
    sys.modules.pop("app.models", None)
    assert index(tmp_path) == 0
    assert "No document models found." in capsys.readouterr().out


def test_a_module_that_will_not_import_is_reported_not_fatal(
    tmp_path: Path, documents: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = types.ModuleType("app.models")
    package.__path__ = [str(tmp_path / "models")]
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / "broken.py").write_text("import nothing_at_all\n", encoding="utf-8")
    app = types.ModuleType("app")
    app.__path__ = []
    monkeypatch.setitem(sys.modules, "app", app)
    monkeypatch.setitem(sys.modules, "app.models", package)

    assert index(tmp_path) == 0
    captured = capsys.readouterr()
    assert "Could not import app.models.broken" in captured.out + captured.err


# --- documents:show ---------------------------------------------------------


def test_show_lists_collections_counts_and_indexes(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    run_async(lambda: Article.create(title="Notes"))
    assert index(tmp_path, ["--model", "Article"]) == 0
    capsys.readouterr()

    assert show(tmp_path, ["--database", "docs"]) == 0
    output = capsys.readouterr().out
    assert "memory [docs]" in output
    assert "articles: 1 document(s)" in output
    assert "index title_unique: title asc (unique)" in output


def test_show_can_be_asked_for_one_collection(
    tmp_path: Path, documents: Any, app_models: Any, capsys: Any
) -> None:
    run_async(lambda: Article.create(title="Notes"))
    run_async(lambda: Note.create(body="hello"))

    assert show(tmp_path, ["--database", "docs", "--collection", "notes"]) == 0
    output = capsys.readouterr().out
    assert "notes: 1 document(s)" in output
    assert "articles" not in output


def test_show_falls_back_to_the_only_document_store(
    tmp_path: Path, documents: Any, capsys: Any
) -> None:
    assert show(tmp_path) == 0
    assert "memory [docs]" in capsys.readouterr().out


def test_show_uses_the_default_connection_when_it_holds_documents(
    tmp_path: Path, documents: Any, capsys: Any
) -> None:
    documents.default = "docs"
    assert show(tmp_path) == 0
    assert "memory [docs]" in capsys.readouterr().out


def test_show_refuses_to_guess_between_stores(
    tmp_path: Path, documents: Any, capsys: Any
) -> None:
    documents.add_connection("other", {"driver": "memory"})
    assert show(tmp_path) == 1
    captured = capsys.readouterr()
    assert "name one with --database" in captured.out + captured.err


def test_show_says_when_no_store_is_configured(tmp_path: Path, capsys: Any) -> None:
    set_manager(
        DatabaseManager(
            {
                "default": "sqlite",
                "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
            }
        )
    )
    try:
        assert show(tmp_path) == 1
        captured = capsys.readouterr()
        assert "No document store is configured" in captured.out + captured.err
    finally:
        set_manager(None)


def test_show_reports_an_empty_store(tmp_path: Path, documents: Any, capsys: Any) -> None:
    assert show(tmp_path, ["--database", "docs"]) == 0
    assert "No collections yet" in capsys.readouterr().out


def test_show_rejects_a_database_flag_with_no_name(
    tmp_path: Path, documents: Any, capsys: Any
) -> None:
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(DocumentsShowCommand)
    command = DocumentsShowCommand()
    command._options = {"database": True, "collection": None}  # type: ignore[attr-defined]
    assert command.handle() == command.INVALID
    captured = capsys.readouterr()
    assert "provide a connection name" in captured.out + captured.err


def test_make_document_reports_a_factory_it_cannot_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """The document lands; the factory in the way is named rather than clobbered."""
    from almasix.console.commands.make import MakeDocumentCommand, MakeFactoryCommand

    monkeypatch.chdir(tmp_path)
    factory = tmp_path / "database" / "factories" / "article_factory.py"
    factory.parent.mkdir(parents=True)
    factory.write_text("# mine\n", encoding="utf-8")

    assert run(tmp_path, MakeDocumentCommand, "make:document", ["Article", "-f"]) == 1
    captured = capsys.readouterr()
    assert "already exists" in captured.out + captured.err
    assert (tmp_path / "app" / "models" / "article.py").is_file()
    assert factory.read_text(encoding="utf-8") == "# mine\n"

    assert run(tmp_path, MakeFactoryCommand, "make:factory", ["TagFactory"]) == 0
    plain = (tmp_path / "database" / "factories" / "tag_factory.py").read_text(encoding="utf-8")
    assert "class TagFactory(Factory):" in plain
    assert "model =" not in plain

    assert run(tmp_path, MakeFactoryCommand, "make:factory", ["NoteFactory", "--model", "Note"]) == 0
    bound = (tmp_path / "database" / "factories" / "note_factory.py").read_text(encoding="utf-8")
    assert "model = Note" in bound


def test_show_reports_a_store_that_will_not_answer(
    tmp_path: Path, documents: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refuse() -> list[str]:
        raise RuntimeError("the store is down")

    monkeypatch.setattr(documents.store("docs"), "collections", refuse)
    assert show(tmp_path, ["--database", "docs"]) == 1
    captured = capsys.readouterr()
    assert "the store is down" in captured.out + captured.err
