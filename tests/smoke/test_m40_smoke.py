"""M40 smoke — Articulate's model surface in the living example."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.console.kernel import ConsoleKernel
from almasix.smith.cli import app as smith_app
from tests.support import purge_generated_app_modules, without_base_path

pytestmark = [pytest.mark.smoke, pytest.mark.regression]

PROGRESS = Path(__file__).resolve().parents[2] / "examples" / "progress"
runner = CliRunner()


@pytest.fixture
def progress(monkeypatch: pytest.MonkeyPatch) -> ConsoleKernel:
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    kernel = ConsoleKernel.from_cwd(PROGRESS)
    yield kernel
    purge_generated_app_modules()


def test_m40_s1_example_user_appends_an_accessor(progress: ConsoleKernel) -> None:
    from app.models.user import User

    user = User(name="Ada", email="ada@example.test", password="secret")
    data = user.to_dict()

    assert data["display_name"] == "Ada <ada@example.test>"
    assert "password" not in data
    assert user.without_appends().to_dict().get("display_name") is None


def test_m40_s2_example_post_is_prunable(progress: ConsoleKernel) -> None:
    from app.models.post import Post

    query = Post.prunable_query()
    sql = str(query.to_select())

    assert "deleted_at IS NOT NULL" in sql
    assert "deleted_at <" in sql


def test_m40_s3_model_prune_is_registered(progress: ConsoleKernel) -> None:
    progress.register_on_typer(smith_app)
    result = runner.invoke(smith_app, ["--help"])

    assert result.exit_code == 0
    assert "model:prune" in result.stdout


def test_m40_s4_model_prune_pretends_against_the_example(
    progress: ConsoleKernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`model:prune --pretend` against a freshly migrated example database."""
    monkeypatch.setenv("DB_CONNECTION", "sqlite")
    monkeypatch.setenv("DB_DATABASE", str(tmp_path / "prune_smoke.sqlite"))

    migrated = runner.invoke(smith_app, ["migrate"])
    assert migrated.exit_code == 0, migrated.stdout

    result = runner.invoke(smith_app, ["model:prune", "--pretend"])

    assert result.exit_code == 0, result.stdout
    assert "Post: 0 model(s) would be pruned." in result.stdout


def test_m40_s5_uuid_keys_round_trip(progress: ConsoleKernel) -> None:
    from almasix.orm import DatabaseManager, HasUuids, Model, Schema, set_manager

    class Ticket(HasUuids, Model):
        table = "tickets"
        fillable = ("subject",)

    async def scenario() -> tuple[str, int]:
        manager = DatabaseManager(
            {
                "default": "sqlite",
                "connections": {"sqlite": {"driver": "sqlite", "database": ":memory:"}},
            }
        )
        set_manager(manager)
        try:
            await Schema.create(
                "tickets",
                lambda table: (
                    table.string("id").primary(),
                    table.string("subject"),
                    table.timestamps(),
                ),
            )
            ticket = await Ticket.create(subject="Printer is on fire")
            with Ticket.without_timestamps():
                ticket.subject = "Printer is still on fire"
                await ticket.save_quietly()
            return ticket.id, await Ticket.query().count()
        finally:
            await manager.disconnect()
            set_manager(None)

    key, total = asyncio.run(scenario())
    assert len(key) == 36
    assert total == 1
