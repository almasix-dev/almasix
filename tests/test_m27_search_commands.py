"""M27 — the `scout:*` console commands.

The commands are synchronous and drive their own event loop, so the fixtures
build the schema in one loop and the command runs in another. The engine is
the fake, which records rather than indexes.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from almasix.console.commands.scout import (
    ScoutDeleteAllIndexesCommand,
    ScoutDeleteIndexCommand,
    ScoutFlushCommand,
    ScoutImportCommand,
    ScoutIndexCommand,
    ScoutQueueImportCommand,
    ScoutStatusCommand,
    ScoutSyncIndexSettingsCommand,
)
from almasix.console.kernel import ConsoleKernel
from almasix.framework import Application
from almasix.orm import DatabaseManager, Schema, set_manager
from almasix.orm.model import Model
from almasix.scout import EngineManager, FakeEngine, Scout, Searchable, set_engine_manager


class Post(Searchable, Model):
    table = "posts"
    timestamps = False
    searchable_columns = ("title",)

    def to_searchable_array(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title}


class Hidden(Searchable, Model):
    """Searchable, but nothing in it is ready for the index."""

    table = "posts"
    timestamps = False
    searchable_columns = ("title",)

    def should_be_searchable(self) -> bool:
        return False


@pytest.fixture
def database() -> Iterator[DatabaseManager]:
    manager = DatabaseManager(
        {
            "default": "sqlite",
            "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
        }
    )
    set_manager(manager)

    async def build() -> None:
        await Schema.create("posts", lambda t: (t.id(), t.string("title")))
        await Post.force_create({"title": "Almasix ships search"})
        await Post.force_create({"title": "Broadcasting"})

    asyncio.run(build())
    yield manager
    set_manager(None)


@pytest.fixture
def engine() -> Iterator[FakeEngine]:
    set_engine_manager(EngineManager(config={"driver": "collection"}))
    Scout.set_manager(None)
    yield Scout.fake()
    set_engine_manager(None)
    Scout.set_manager(None)


@pytest.fixture
def app_models() -> Iterator[types.ModuleType]:
    """Stand in for the app's `app.models` package, one module deep."""
    package = types.ModuleType("app.models")
    package.__path__ = []
    package.Post = Post
    package.Searchable = Searchable  # the mixin itself must be skipped
    app = types.ModuleType("app")
    app.__path__ = []
    sys.modules["app"] = app
    sys.modules["app.models"] = package
    yield package
    sys.modules.pop("app.models", None)
    sys.modules.pop("app", None)


def run(tmp_path: Path, command: type, name: str, argv: list[str] | None = None) -> int:
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(command)
    return kernel.run_argv(name, argv or [])


# --- importing ------------------------------------------------------------


def test_importing_a_model_fills_the_index(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, app_models
    assert run(tmp_path, ScoutImportCommand, "scout:import", ["Post"]) == 0

    output = capsys.readouterr().out
    assert "Post -> posts: 2 record(s)" in output
    assert "Imported." in output
    engine.assert_synced(Post, [1, 2])


def test_an_import_can_be_chunked(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
) -> None:
    del database, app_models
    assert run(tmp_path, ScoutImportCommand, "scout:import", ["Post", "--chunk", "1"]) == 0
    assert len(engine.written("update", "posts")) == 2


def test_a_dotted_path_names_a_model_too(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database
    argv = ["tests.test_m27_search_commands.Post"]
    assert run(tmp_path, ScoutImportCommand, "scout:import", argv) == 0
    assert "Post -> posts" in capsys.readouterr().out
    engine.assert_synced(Post)


def test_an_import_of_nothing_searchable_says_so(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(tmp_path, ScoutImportCommand, "scout:import") == 0
    assert "No searchable models found." in capsys.readouterr().out
    engine.assert_nothing_synced()


def test_a_model_that_is_not_searchable_is_named(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del engine
    assert run(tmp_path, ScoutImportCommand, "scout:import", ["Ghost"]) == 0
    output = capsys.readouterr().out
    assert "Model [Ghost] was not found, or is not searchable." in output


def test_a_dotted_path_that_leads_nowhere_is_named(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del engine
    argv = ["app.nowhere.Ghost"]
    assert run(tmp_path, ScoutImportCommand, "scout:import", argv) == 0
    assert "was not found" in capsys.readouterr().out


def test_a_module_that_will_not_import_does_not_stop_the_rest(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del database, engine
    broken = tmp_path / "models"
    broken.mkdir()
    (broken / "broken.py").write_text("raise ValueError('no')\n", encoding="utf-8")
    app_models.__path__ = [str(broken)]
    monkeypatch.syspath_prepend(str(tmp_path))

    assert run(tmp_path, ScoutImportCommand, "scout:import") == 0
    output = capsys.readouterr().out
    assert "Could not import app.models.broken" in output
    assert "Post -> posts" in output


# --- queued importing -------------------------------------------------------


def test_a_queued_import_hands_each_chunk_to_the_queue(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, engine, app_models
    import almasix.queue.helpers as queue_helpers

    queued: list[Any] = []

    async def capture(job: Any) -> None:
        queued.append(job)

    original = queue_helpers.dispatch
    queue_helpers.dispatch = capture
    try:
        argv = ["Post", "--chunk", "1"]
        assert run(tmp_path, ScoutQueueImportCommand, "scout:queue-import", argv) == 0
    finally:
        queue_helpers.dispatch = original

    assert "Post: 2 job(s) queued" in capsys.readouterr().out
    assert [job.keys for job in queued] == [[1], [2]]


def test_a_queued_import_skips_what_should_not_be_indexed(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, engine
    argv = ["tests.test_m27_search_commands.Hidden"]
    assert run(tmp_path, ScoutQueueImportCommand, "scout:queue-import", argv) == 0
    assert "Hidden: 0 job(s) queued" in capsys.readouterr().out


def test_a_queued_import_of_nothing_says_so(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del engine
    assert run(tmp_path, ScoutQueueImportCommand, "scout:queue-import") == 0
    assert "No searchable models found." in capsys.readouterr().out


# --- flushing ---------------------------------------------------------------


def test_flushing_empties_the_index(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, app_models
    assert run(tmp_path, ScoutFlushCommand, "scout:flush", ["Post"]) == 0
    assert "Post -> posts: flushed" in capsys.readouterr().out
    engine.assert_flushed(Post)


def test_flushing_nothing_says_so(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del engine
    assert run(tmp_path, ScoutFlushCommand, "scout:flush") == 0
    assert "No searchable models found." in capsys.readouterr().out


# --- index management -------------------------------------------------------


def test_creating_an_index(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = ["posts", "--key", "uuid"]
    assert run(tmp_path, ScoutIndexCommand, "scout:index", argv) == 0
    assert "Index [posts] created." in capsys.readouterr().out
    created = engine.written("create-index", "posts")
    assert created and created[0].payload == {"primaryKey": "uuid"}


def test_deleting_an_index(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(tmp_path, ScoutDeleteIndexCommand, "scout:delete-index", ["posts"]) == 0
    assert "Index [posts] deleted." in capsys.readouterr().out
    assert engine.written("delete-index", "posts")


def test_deleting_every_index(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(tmp_path, ScoutDeleteAllIndexesCommand, "scout:delete-all-indexes") == 0
    assert "All indexes deleted." in capsys.readouterr().out
    assert engine.written("delete-all-indexes")


@pytest.mark.parametrize(
    ("command", "name", "argv"),
    [
        (ScoutIndexCommand, "scout:index", ["posts"]),
        (ScoutDeleteIndexCommand, "scout:delete-index", ["posts"]),
        (ScoutDeleteAllIndexesCommand, "scout:delete-all-indexes", []),
    ],
)
def test_the_search_service_refusing_is_reported(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
    command: type,
    name: str,
    argv: list[str],
) -> None:
    async def refuse(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("meilisearch is not listening")

    engine.create_index = refuse  # type: ignore[method-assign]
    engine.delete_index = refuse  # type: ignore[method-assign]
    engine.delete_all_indexes = refuse  # type: ignore[method-assign]

    assert run(tmp_path, command, name, argv) == 1
    assert "meilisearch is not listening" in capsys.readouterr().err


# --- settings ---------------------------------------------------------------


def test_syncing_index_settings(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, app_models
    name = "scout:sync-index-settings"
    assert run(tmp_path, ScoutSyncIndexSettingsCommand, name) == 0
    output = capsys.readouterr().out
    assert "Post -> posts: settings updated" in output
    assert "1 index(es) updated." in output
    assert engine.written("settings", "posts")


def test_syncing_settings_that_are_not_configured_says_so(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, app_models

    async def nothing(_model: Any) -> bool:
        return False

    engine.sync_settings = nothing  # type: ignore[method-assign]
    name = "scout:sync-index-settings"
    assert run(tmp_path, ScoutSyncIndexSettingsCommand, name) == 0
    assert "No index settings are configured." in capsys.readouterr().out


def test_syncing_settings_reports_what_the_service_said(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, app_models

    async def refuse(_model: Any) -> bool:
        raise RuntimeError("index is locked")

    engine.sync_settings = refuse  # type: ignore[method-assign]
    name = "scout:sync-index-settings"
    assert run(tmp_path, ScoutSyncIndexSettingsCommand, name) == 1
    assert "Post: index is locked" in capsys.readouterr().err


def test_syncing_settings_without_a_searchable_model_says_so(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del engine
    name = "scout:sync-index-settings"
    assert run(tmp_path, ScoutSyncIndexSettingsCommand, name) == 0
    assert "No searchable models found." in capsys.readouterr().out


# --- status -----------------------------------------------------------------


def test_status_reports_the_engine_and_the_models(
    tmp_path: Path,
    database: DatabaseManager,
    engine: FakeEngine,
    app_models: types.ModuleType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database, engine, app_models
    assert run(tmp_path, ScoutStatusCommand, "scout:status") == 0
    output = capsys.readouterr().out
    assert "searching via [collection]" in output
    assert "queue: no" in output
    assert "after commit: no" in output
    assert "soft deletes indexed: no" in output
    assert "Post -> posts" in output


def test_status_says_when_no_model_is_searchable(
    tmp_path: Path,
    engine: FakeEngine,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del engine
    assert run(tmp_path, ScoutStatusCommand, "scout:status") == 0
    output = capsys.readouterr().out
    assert "No searchable models. Mix in almasix.scout.Searchable." in output
