"""M40 — the `model:prune` console command.

These tests are synchronous: the command drives its own event loop, like every
other Smith command, so the setup and assertions run in separate loops. The
`db` helper drops stale pooled connections before each hop.
"""

from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from almasix.console.commands.model_prune import ModelPruneCommand
from almasix.console.kernel import ConsoleKernel
from almasix.framework import Application
from almasix.orm import DatabaseManager, MassPrunable, Model, Prunable, Schema, set_manager

_MANAGER: DatabaseManager | None = None


class Flight(Prunable, Model):
    table = "flights"
    fillable = ("name",)

    def prunable(self) -> Any:
        return self.query().where("name", "like", "old%")


class Bulk(MassPrunable, Model):
    table = "flights"
    fillable = ("name",)

    def prunable(self) -> Any:
        return self.query().where("name", "like", "old%")


class Untouched(Model):
    table = "flights"
    fillable = ("name",)


def db(operation: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
    """Run a coroutine on a fresh loop with fresh connections."""

    async def main() -> Any:
        assert _MANAGER is not None
        await _MANAGER.disconnect()  # anything pooled belongs to a dead loop
        return await operation()

    return asyncio.run(main())


@pytest.fixture
def database(tmp_path: Path) -> Any:
    global _MANAGER
    path = tmp_path / "prune.sqlite"
    _MANAGER = DatabaseManager(
        {
            "default": "sqlite",
            "connections": {"sqlite": {"driver": "sqlite", "database": str(path)}},
        }
    )
    set_manager(_MANAGER)

    async def seed() -> None:
        await Schema.create(
            "flights",
            lambda table: (table.id(), table.string("name"), table.timestamps()),
        )
        for name in ("old-1", "old-2", "keep"):
            await Flight.create(name=name)

    db(seed)
    yield _MANAGER
    db(lambda: _MANAGER.disconnect())
    set_manager(None)
    _MANAGER = None


@pytest.fixture
def app_models() -> Any:
    """Stand in for the app's `app.models` package."""
    package = types.ModuleType("app.models")
    package.__path__ = []  # a package with no submodules
    package.Flight = Flight
    package.Bulk = Bulk
    package.Untouched = Untouched
    package.Prunable = Prunable
    package.MassPrunable = MassPrunable  # the base mixins must be skipped
    app = types.ModuleType("app")
    app.__path__ = []
    sys.modules["app"] = app
    sys.modules["app.models"] = package
    yield package
    sys.modules.pop("app.models", None)
    sys.modules.pop("app", None)


def run(tmp_path: Path, argv: list[str]) -> int:
    kernel = ConsoleKernel(Application(tmp_path))
    kernel.register(ModelPruneCommand)
    return kernel.run_argv("model:prune", argv)


def count(model: type[Model]) -> int:
    return db(lambda: model.query().count())


def test_prune_command_prunes_every_prunable_model(
    tmp_path: Path, database, app_models, capsys
) -> None:
    code = run(tmp_path, [])
    output = capsys.readouterr().out

    assert code == 0
    assert "Bulk: 2 model(s) pruned." in output
    assert "Flight: 0 model(s) pruned." in output  # Bulk already took them
    assert "Untouched" not in output
    assert count(Untouched) == 1


def test_prune_command_may_target_one_model(
    tmp_path: Path, database, app_models, capsys
) -> None:
    code = run(tmp_path, ["--model=Flight"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Flight: 2 model(s) pruned." in output
    assert "Bulk" not in output
    assert count(Flight) == 1


def test_prune_command_accepts_a_dotted_class_path(
    tmp_path: Path, database, app_models, capsys
) -> None:
    run(tmp_path, ["--model=app.models.Flight"])
    assert "Flight: 2 model(s) pruned." in capsys.readouterr().out


def test_prune_command_may_exclude_models(
    tmp_path: Path, database, app_models, capsys
) -> None:
    code = run(tmp_path, ["--except=Bulk"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Flight: 2 model(s) pruned." in output
    assert "Bulk" not in output


def test_prune_command_pretends(
    tmp_path: Path, database, app_models, capsys
) -> None:
    code = run(tmp_path, ["--pretend", "--model=Flight"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Flight: 2 model(s) would be pruned." in output
    assert count(Flight) == 3


def test_prune_command_honors_the_chunk_size(
    tmp_path: Path, database, app_models, capsys
) -> None:
    run(tmp_path, ["--model=Flight", "--chunk=1"])
    assert "Flight: 2 model(s) pruned." in capsys.readouterr().out


def test_model_and_except_cannot_be_combined(
    tmp_path: Path, database, app_models, capsys
) -> None:
    code = run(tmp_path, ["--model=Flight", "--except=Bulk"])
    assert code == 2
    assert "cannot be combined" in capsys.readouterr().err


def test_unknown_models_warn(
    tmp_path: Path, database, app_models, capsys
) -> None:
    code = run(tmp_path, ["--model=Nope"])
    output = capsys.readouterr().out

    assert code == 0
    assert "was not found or is not prunable" in output
    assert "No prunable models found." in output


def test_prune_command_survives_an_app_without_models(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """An app with no `app/models` package at all."""
    from almasix.console.commands import model_prune

    def missing(name: str) -> Any:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(model_prune.importlib, "import_module", missing)

    code = run(tmp_path, [])
    assert code == 0
    assert "No prunable models found." in capsys.readouterr().out


def test_prune_command_walks_submodules(
    tmp_path: Path, database, capsys, monkeypatch
) -> None:
    """A real `app/models/` directory, imported module by module."""
    models_dir = tmp_path / "app" / "models"
    models_dir.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (models_dir / "__init__.py").write_text("", encoding="utf-8")
    (models_dir / "flight.py").write_text(
        "from tests.test_m40_prune_command import Flight\n", encoding="utf-8"
    )
    (models_dir / "broken.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    _forget_app_modules()

    code = run(tmp_path, [])
    output = capsys.readouterr().out
    assert code == 0
    assert "Flight: 2 model(s) pruned." in output
    assert "Could not import app.models.broken" in output

    _forget_app_modules()


def _forget_app_modules() -> None:
    for name in [key for key in sys.modules if key == "app" or key.startswith("app.")]:
        sys.modules.pop(name, None)
