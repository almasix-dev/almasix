"""Fill remaining M5 coverage: relation contracts, model events, CLI errors."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from almasix.orm import DB, Collection, Model, RelationNotLoadedError
from almasix.orm.builder import _invoke_scope
from almasix.orm.casts import _parse_datetime, cast_value
from almasix.orm.eager import eager_load, eager_load_counts
from almasix.orm.migration import MigrationError, Migrator
from almasix.orm.relations import Relation
from almasix.smith.cli import app as smith_app
from almasix.smith.ports import NoFreePortError, find_available_port
from tests.test_m5_parity import Badge, Memo, Nation, Person, Remark, Tag, _schema

pytest_plugins = ("tests.orm_support",)


@pytest.mark.asyncio
async def test_remaining_relation_and_builder_contracts(memory_db) -> None:
    await _schema(memory_db)
    tz = await Nation.create(name="TZ")
    ada = Person()
    ada.force_fill({"name": "Ada", "votes": 1, "flag": True, "nation_id": tz.id})
    await ada.save()
    await ada.notes().create(body="hello", views=1)
    await ada.bio().create(text="bio")
    gold = await Badge.create(name="gold")
    await ada.badges().attach(gold, {"level": "a"})
    await ada.comments().create(body="c")
    await ada.portrait().create(body="p")
    tag = await Tag.create(name="t")
    await ada.tags().attach(tag)

    base = Relation(ada, Memo)
    with pytest.raises(NotImplementedError):
        base.query()
    with pytest.raises(NotImplementedError):
        base.eager_query([ada])
    with pytest.raises(NotImplementedError):
        base.match([ada], Collection(), "notes")
    with pytest.raises(NotImplementedError):
        base.existence_query(Person.query())
    with pytest.raises(NotImplementedError):
        base.grouping_column()
    with pytest.raises(NotImplementedError):
        base.parent_match_key()

    await Memo.query().has("author").get()
    await Memo.query().with_count("author").get()
    await Memo.query().where_has("author").get()
    loaded = (
        await Person.query()
        .with_({"badges": None, "comments": None, "portrait": None, "tags": None})
        .get()
    )
    assert loaded[0].relation_loaded("badges")
    await Nation.query().has("memos").with_("memos").with_count("memos").get()
    await Person.query().has("notes", "=", 1).get()
    await ada.notes().first_or_create({"body": "brand-new"}, {"views": 0})
    await ada.badges().detach()
    await ada.tags().detach()

    empty = Remark()
    empty.force_fill({"body": "x", "commentable_id": None, "commentable_type": "Person"})
    assert await empty.commentable().get() is None
    empty.force_fill({"commentable_id": 1, "commentable_type": "Nope"})
    with pytest.raises(LookupError):
        await empty.commentable().get()
    ghost = Remark()
    ghost.force_fill({"body": "g", "commentable_id": 1, "commentable_type": "Ghost"})
    await ghost.save()
    await Remark.query().with_("commentable").get()

    Person.query().column(sa.literal_column("1"))
    with pytest.raises(ValueError):
        Person.query().join("memos", "people.id", "???", "memos.person_id")
    Person.query().when(False, lambda q: None)
    Person.query().with_({"notes": lambda q: q})
    sql = Memo.query().latest().to_sql().lower()
    assert "created_at" in sql or "order" in sql
    with pytest.raises(RuntimeError):
        DB.table("people").has("notes")
    await Person.query().update({"votes": 0})
    await DB.table("badges").delete()
    found = await Person.query().first_or_new({"name": "Ada"})
    assert found.exists
    await Person.query().upsert(
        {"name": "Ada", "votes": 1, "flag": True}, unique_by=["name"], update=[]
    )

    seen: list[int] = []
    await Person.query().order_by("id").chunk(10, lambda chunk: seen.append(len(chunk)))
    names = [row.name async for row in Person.query().cursor(size=10)]
    assert names

    async def visit(row):
        return True

    await Person.query().each(visit, size=10)
    await eager_load([], "notes")
    await eager_load([ada], [])
    await eager_load([ada], [{"notes": None}])
    await eager_load_counts([], "notes", "notes_count")
    nested = await Person.query().with_("notes.author").first()
    nested.set_relation("notes", None)
    await eager_load([nested], ["notes.author"])

    def none_scope(query):
        query.where("flag", True)

    _invoke_scope(none_scope, Person, Person.query(), (), {})
    _invoke_scope(lambda *_a, **_k: None, Person, Person.query(), (), {})


@pytest.mark.asyncio
async def test_remaining_model_hooks(memory_db) -> None:
    await _schema(memory_db)

    class Booted(Model):
        table = "people"
        timestamps = False
        fillable = ("name", "votes", "flag")
        visible = ("name",)
        hidden = ("secret",)
        appends = ("secret",)

        def boot(cls):
            cls.add_global_scope("boot", lambda query: query)

        def get_secret_attribute(self, _value=None) -> str:
            return "x"

        def set_flag_attribute(self, value):
            return None

        def get_votes_attribute(self, value):
            return value

    class Child(Booted):
        pass

    assert "boot" in Child.get_global_scopes()
    row = Booted()
    row.force_fill({"name": "A", "votes": 3, "flag": True})
    row.set_attribute("flag", True)
    assert row.get_attributes()["name"] == "A"
    row._extra["bonus"] = 1
    assert row.bonus == 1
    assert row.get_original() is not None
    assert row.is_(row)
    other = object()
    assert (row == other) is False
    payload = row.to_dict()
    assert "name" in payload and "votes" not in payload
    row.set_relation("notes", None)
    row.to_dict()
    await row.save()
    assert row.was_changed()
    await Booted.destroy(999)
    filled = Booted()
    filled.fill({"name": "B", "nope": 1})
    assert "nope" not in filled.get_attributes()

    class GuardedOnly(Model):
        table = "people"
        timestamps = False
        fillable = ()
        guarded = ("secret",)

    assert GuardedOnly.is_fillable("name")
    assert not GuardedOnly.is_fillable("secret")

    memo = await Memo.create(body="t", views=0)
    await memo.touch()
    fresh = await Memo.create(body="gone", views=0)
    await DB.table("memos").where("id", fresh.id).delete()
    await fresh.refresh()

    async def on_created(model):
        return True

    Memo.listen("created", on_created)
    Memo.listen("replicating", on_created)
    made = await Memo.create(body="evt", views=0)
    made.replicate()
    Memo.listen("creating", lambda _m: False)
    blocked = Memo()
    blocked.force_fill({"body": "no", "views": 0})
    assert await blocked.save() is False
    Memo._events["creating"] = []
    Memo.listen("updating", lambda _m: False)
    made.views = 9
    assert await made.save() is False
    Memo._events["updating"] = []
    Memo.listen("deleting", lambda _m: False)
    assert await made.delete() is False
    Memo._events["deleting"] = []
    Memo.listen("saving", lambda _m: False)
    assert await made.save() is False
    Memo._events["saving"] = []

    pending = Person().notes
    with pytest.raises(RelationNotLoadedError):
        next(iter(pending))
    await Collection([made]).load_missing("author")
    await Collection([made]).load_missing("author")
    assert Collection([1, 2]).is_not_empty()
    assert _parse_datetime(None) is None
    assert isinstance(_parse_datetime(datetime.now(UTC)), datetime)
    assert cast_value("1.25", "decimal") == Decimal("1.25")

    class Loose(Model):
        table = "people"
        timestamps = False

        bogus = 1

    with pytest.raises(AttributeError, match="is not a relation"):
        Loose().get_relation("bogus")
    with pytest.raises(AttributeError):
        Loose().get_relation("missing")

    await DB.disconnect()


def test_cli_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    status = runner.invoke(smith_app, ["migrate:status"], catch_exceptions=False)
    assert status.exit_code == 0
    assert "No migrations" in status.stdout
    migrated = runner.invoke(smith_app, ["migrate"], catch_exceptions=False)
    assert migrated.exit_code == 0
    rolled = runner.invoke(smith_app, ["migrate:rollback"], catch_exceptions=False)
    assert rolled.exit_code == 0
    fresh = runner.invoke(smith_app, ["migrate:fresh"], catch_exceptions=False)
    assert fresh.exit_code == 0
    made = runner.invoke(smith_app, ["make:migration", "???"], catch_exceptions=False)
    assert made.exit_code == 1
    model = runner.invoke(smith_app, ["make:model", "Widget"], catch_exceptions=False)
    assert model.exit_code == 0
    with patch(
        "almasix.console.commands.runtime.find_available_port", side_effect=NoFreePortError("full")
    ):
        serve = runner.invoke(smith_app, ["serve", "--app", "x:y"], catch_exceptions=False)
        assert serve.exit_code == 1
    with pytest.raises(ValueError):
        find_available_port(start=5, end=1)


@pytest.mark.asyncio
async def test_migrator_missing_file_on_rollback(memory_db, tmp_path: Path) -> None:
    migrator = Migrator(tmp_path)
    await migrator._ensure_table()
    await DB.statement(
        'INSERT INTO "migrations" (migration, batch) VALUES (:migration, :batch)',
        {"migration": "ghost", "batch": 1},
    )
    with pytest.raises(MigrationError):
        await migrator.rollback()
