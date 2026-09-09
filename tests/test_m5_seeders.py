"""M5 — Database seeders (Laravel Seeder / db:seed / migrate --seed)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.orm import (
    Model,
    Schema,
    Seeder,
    SeederError,
    WithoutModelEvents,
    invoke_seeder,
    load_database_seeder,
    make_seeder,
    reset_called,
    resolve_seeder_class,
    without_model_events,
)
from almasix.orm import model as model_mod
from almasix.smith.cli import app as smith_app
from tests.orm_support import memory_db  # noqa: F401

runner = CliRunner()


class Item(Model):
    table = "items"
    fillable = ("name",)
    timestamps = False


class CountingSeeder(Seeder):
    runs = 0

    async def run(self) -> None:
        type(self).runs += 1
        await Item.create(name=f"item-{type(self).runs}")


class ParamSeeder(Seeder):
    last_count = 0

    async def run(self, count: int = 1) -> None:
        type(self).last_count = count
        for i in range(count):
            await Item.create(name=f"param-{i}")


class QuietSeeder(WithoutModelEvents, Seeder):
    async def run(self) -> None:
        await Item.create(name="quiet")


class DatabaseSeeder(Seeder):
    async def run(self) -> None:
        await self.call([CountingSeeder])


@pytest.fixture
async def seed_db(memory_db) -> None:
    reset_called()
    CountingSeeder.runs = 0
    ParamSeeder.last_count = 0
    Item._events = {event: [] for event in Item._events}
    await Schema.create("items", lambda t: (t.id(), t.string("name")))
    yield
    model_mod._EVENTS_DISABLED = False


@pytest.mark.asyncio
async def test_call_and_call_once(seed_db) -> None:
    root = Seeder()
    await root.call([CountingSeeder])
    assert CountingSeeder.runs == 1
    assert await Item.query().count() == 1

    await root.call_once(CountingSeeder)
    assert CountingSeeder.runs == 1

    await root.call(CountingSeeder)
    assert CountingSeeder.runs == 2


@pytest.mark.asyncio
async def test_call_once_skips_already_called(seed_db) -> None:
    root = Seeder()
    await root.call_once(CountingSeeder)
    assert CountingSeeder.runs == 1
    await root.call_once(CountingSeeder)
    assert CountingSeeder.runs == 1


@pytest.mark.asyncio
async def test_resolve_string_container_and_sync_run(seed_db) -> None:
    class SyncSeeder(Seeder):
        ran = False

        def run(self) -> None:  # sync run()
            type(self).ran = True

    class FakeContainer:
        def make(self, cls):
            raise RuntimeError("force fallback")

    class GoodContainer:
        def make(self, cls):
            return cls()

    class BadContainer:
        def make(self, cls):
            return object()

    class Cmd:
        messages: list[str] = []

        def echo(self, msg: str) -> None:
            type(self).messages.append(msg)

    Cmd.messages = []
    root = Seeder().set_container(FakeContainer()).set_command(Cmd())
    resolved = root.resolve("tests.test_m5_seeders.CountingSeeder")
    assert isinstance(resolved, CountingSeeder)
    await root.call_silent(CountingSeeder)
    await root.call(CountingSeeder)
    assert Cmd.messages

    assert isinstance(
        Seeder().set_container(GoodContainer()).resolve(CountingSeeder), CountingSeeder
    )

    with pytest.raises(SeederError):
        root.resolve(object)  # type: ignore[arg-type]
    with pytest.raises(SeederError):
        root.resolve("NoDots")
    with pytest.raises(SeederError):
        Seeder().set_container(BadContainer()).resolve(CountingSeeder)

    await SyncSeeder()()
    assert SyncSeeder.ran is True


@pytest.mark.asyncio
async def test_resolve_seeder_class_edges(tmp_path: Path, seed_db) -> None:
    seeders = tmp_path / "database" / "seeders"
    seeders.mkdir(parents=True)
    (seeders / "alias_seeder.py").write_text(
        "from almasix.orm import Seeder\n"
        "class RenamedSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    # Class name AliasSeeder missing — fall back to first Seeder in module.
    found = resolve_seeder_class("AliasSeeder", base_path=tmp_path)
    assert found.__name__ == "RenamedSeeder"

    dotted = resolve_seeder_class("tests.test_m5_seeders.CountingSeeder")
    assert dotted is CountingSeeder

    with pytest.raises(SeederError):
        resolve_seeder_class("not_a_module")
    with pytest.raises(SeederError):
        resolve_seeder_class("tests.test_m5_seeders.Item")
    with pytest.raises(SeederError):
        make_seeder("", seeders)
    with pytest.raises(SeederError):
        make_seeder("/", seeders)

    # Invalid DatabaseSeeder body
    bad = tmp_path / "bad"
    (bad / "database" / "seeders").mkdir(parents=True)
    (bad / "database" / "seeders" / "database_seeder.py").write_text(
        "class DatabaseSeeder:\n    pass\n",
        encoding="utf-8",
    )
    with pytest.raises(SeederError):
        load_database_seeder(bad)

    # Module with no Seeder subclass under requested name
    (seeders / "empty_seeder.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(SeederError):
        resolve_seeder_class("EmptySeeder", base_path=tmp_path)

    forced = make_seeder("ForceSeeder", seeders, force=True)
    assert forced.name == "force_seeder.py"


def test_run_seeder_sync_cli_wrapper(tmp_path: Path) -> None:
    from almasix.orm import run_seeder

    seeders = tmp_path / "database" / "seeders"
    seeders.mkdir(parents=True)
    (seeders / "database_seeder.py").write_text(
        "from almasix.orm import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    run_seeder(base_path=tmp_path)


@pytest.mark.asyncio
async def test_call_with_and_call_silent(seed_db, capsys) -> None:
    root = Seeder()
    await root.call_with(ParamSeeder, {"count": 3})
    assert ParamSeeder.last_count == 3
    assert await Item.query().count() == 3
    out = capsys.readouterr().out
    assert "ParamSeeder" in out
    assert "RUNNING" in out

    await root.call_silent(ParamSeeder, {"count": 1})
    assert await Item.query().count() == 4
    silent_out = capsys.readouterr().out
    assert silent_out == ""


@pytest.mark.asyncio
async def test_without_model_events_mixin_and_context(seed_db) -> None:
    fired: list[str] = []

    def on_created(model: Item) -> None:
        fired.append("created")

    Item.listen("created", on_created)

    await QuietSeeder()()
    assert await Item.query().where("name", "quiet").exists()
    assert fired == []

    with without_model_events():
        await Item.create(name="ctx")
    assert fired == []

    await Item.create(name="loud")
    assert fired == ["created"]


@pytest.mark.asyncio
async def test_make_and_load_database_seeder(tmp_path: Path, seed_db) -> None:
    seeders = tmp_path / "database" / "seeders"
    path = make_seeder("WidgetSeeder", seeders)
    assert path.name == "widget_seeder.py"
    text = path.read_text(encoding="utf-8")
    assert "class WidgetSeeder(Seeder)" in text

    db_path = seeders / "database_seeder.py"
    db_path.write_text(
        "from almasix.orm import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    cls = load_database_seeder(tmp_path)
    assert cls.__name__ == "DatabaseSeeder"
    resolved = resolve_seeder_class("WidgetSeeder", base_path=tmp_path)
    assert resolved.__name__ == "WidgetSeeder"

    with pytest.raises(SeederError):
        load_database_seeder(tmp_path / "missing")
    with pytest.raises(SeederError):
        resolve_seeder_class("MissingSeeder", base_path=tmp_path)
    with pytest.raises(SeederError):
        make_seeder("WidgetSeeder", seeders)


@pytest.mark.asyncio
async def test_run_seeder_default_entry(tmp_path: Path, seed_db) -> None:
    seeders = tmp_path / "database" / "seeders"
    seeders.mkdir(parents=True)
    (seeders / "database_seeder.py").write_text(
        "from almasix.orm import Seeder\n"
        "from tests.test_m5_seeders import CountingSeeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        await self.call_silent([CountingSeeder])\n",
        encoding="utf-8",
    )
    await invoke_seeder(base_path=tmp_path)
    assert CountingSeeder.runs == 1


def test_scaffold_ships_database_seeder(tmp_path: Path) -> None:
    root = scaffold_app("seed_app", destination=tmp_path / "seed_app")
    assert (root / "database" / "seeders" / "database_seeder.py").is_file()
    assert (root / "database" / "__init__.py").is_file()
    text = (root / "database" / "seeders" / "database_seeder.py").read_text(encoding="utf-8")
    assert "class DatabaseSeeder(Seeder)" in text


def test_cli_make_seeder_and_db_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("cli_seed", destination=tmp_path / "cli_seed")
    monkeypatch.chdir(root)
    monkeypatch.setenv("DB_CONNECTION", "sqlite")
    monkeypatch.setenv("DB_DATABASE", str(tmp_path / "cli_seed.sqlite"))

    made = runner.invoke(smith_app, ["make:seeder", "UserSeeder"], catch_exceptions=False)
    assert made.exit_code == 0, made.stdout
    assert (root / "database" / "seeders" / "user_seeder.py").is_file()

    (root / "database" / "seeders" / "database_seeder.py").write_text(
        "from almasix.orm import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    seeded = runner.invoke(smith_app, ["db:seed"], catch_exceptions=False)
    assert seeded.exit_code == 0, seeded.stdout
    assert "Database seeding completed successfully." in seeded.stdout

    classed = runner.invoke(
        smith_app,
        ["db:seed", "--class", "UserSeeder"],
        catch_exceptions=False,
    )
    assert classed.exit_code == 0, classed.stdout


def test_cli_db_seed_missing_seeder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("seed_miss", destination=tmp_path / "seed_miss")
    (root / "database" / "seeders" / "database_seeder.py").unlink()
    monkeypatch.chdir(root)
    monkeypatch.setenv("DB_CONNECTION", "sqlite")
    monkeypatch.setenv("DB_DATABASE", str(tmp_path / "seed_miss.sqlite"))
    failed = runner.invoke(smith_app, ["db:seed"], catch_exceptions=False)
    assert failed.exit_code == 1


def test_cli_migrate_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("mig_seed", destination=tmp_path / "mig_seed")
    monkeypatch.chdir(root)
    monkeypatch.setenv("DB_CONNECTION", "sqlite")
    monkeypatch.setenv("DB_DATABASE", str(tmp_path / "mig_seed.sqlite"))

    mig = root / "database" / "migrations" / "2020_01_01_000000_create_widgets_table.py"
    mig.write_text(
        "from almasix.orm import Migration, Schema\n"
        "class CreateWidgets(Migration):\n"
        "    async def up(self):\n"
        "        await Schema.create('widgets', lambda t: (t.id(), t.string('name')))\n"
        "    async def down(self):\n"
        "        await Schema.drop_if_exists('widgets')\n",
        encoding="utf-8",
    )
    (root / "database" / "seeders" / "database_seeder.py").write_text(
        "from almasix.orm import Seeder\n"
        "class DatabaseSeeder(Seeder):\n"
        "    async def run(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    result = runner.invoke(smith_app, ["migrate", "--seed"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    assert "Migrated:" in result.stdout
    assert "Database seeding completed successfully." in result.stdout

    fresh = runner.invoke(smith_app, ["migrate:fresh", "--seed"], catch_exceptions=False)
    assert fresh.exit_code == 0, fresh.stdout
    assert "Database seeding completed successfully." in fresh.stdout
