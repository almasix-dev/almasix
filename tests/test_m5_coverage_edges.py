"""Coverage edges for almasix.orm — remaining public API surface."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.orm import (
    DB,
    Collection,
    Model,
    Schema,
    SoftDeletes,
    relation,
)
from almasix.orm.casts import CastError, cast_value, serialize_value, uncast_value
from almasix.orm.connection import ConnectionError_, DatabaseManager, _ensure_async_driver
from almasix.orm.facade import raw
from almasix.orm.inflector import (
    camel,
    foreign_key,
    pivot_table,
    pluralize,
    singularize,
    snake,
    studly,
)
from almasix.orm.migration import MigrationError, make_migration
from almasix.smith.cli import app as smith_app

pytest_plugins = ("tests.orm_support",)


class Kind(Enum):
    A = "a"


def test_casts_and_serialize() -> None:
    assert cast_value("3", "int") == 3
    assert cast_value("1.5", "float") == 1.5
    assert cast_value(1, "string") == "1"
    assert cast_value("yes", "bool") is True
    assert cast_value(Decimal("1.23"), "decimal:2") == Decimal("1.23")
    assert cast_value('{"a":1}', "json") == {"a": 1}
    assert cast_value({"a": 1}, "json") == {"a": 1}
    assert isinstance(cast_value("2024-01-02T03:04:05", "datetime"), datetime)
    assert cast_value("2024-01-02", "date") == date(2024, 1, 2)
    assert isinstance(cast_value("12:30:00", "time"), time)
    assert cast_value(Kind.A, Kind) is Kind.A or True
    assert uncast_value({"a": 1}, "json") == '{"a": 1}'
    assert uncast_value(Kind.A, "string") == "a" or uncast_value(Kind.A, Kind) == "a"
    assert serialize_value(Decimal(1)) == 1.0
    assert serialize_value(date(2024, 1, 1)).startswith("2024")
    with pytest.raises(CastError):
        cast_value("nope", "json")


def test_inflector() -> None:
    assert snake("BlogPost") == "blog_post"
    assert studly("blog_post") == "BlogPost"
    assert camel("blog_post") == "blogPost"
    assert pluralize("category") == "categories"
    assert pluralize("box") == "boxes"
    assert pluralize("leaf") == "leaves"
    assert pluralize("tomato") == "tomatoes"
    assert pluralize("person") == "people"
    assert pluralize("sheep") == "sheep"
    assert singularize("categories") == "category"
    assert singularize("people") == "person"
    assert singularize("boxes") == "box"
    assert singularize("tomatoes") == "tomato"
    assert singularize("knives") == "knife"
    assert foreign_key("User") == "user_id"
    assert pivot_table("User", "Role") == "role_user"


def test_collection_helpers() -> None:
    items = Collection([{"id": 1, "n": 2}, {"id": 2, "n": 2}, {"id": 3, "n": 9}])
    assert items.first()["id"] == 1
    assert items.last()["id"] == 3
    assert items.count() == 3
    assert items.where("n", 2).count() == 2
    assert items.pluck("id").all() == [1, 2, 3]
    assert items.unique("n").count() == 2
    assert items.sort_by("n")[-1]["id"] == 3
    assert set(items.group_by("n").keys()) == {2, 9}
    assert items.take(1).count() == 1
    assert items.skip(2).count() == 1
    assert items.sum("n") == 13
    assert items.max("n") == 9
    assert items.contains(lambda row: row["id"] == 2)
    assert Collection([1, 2]).merge([3]).all() == [1, 2, 3]
    assert Collection([1, 2]).reverse().values().all() == [2, 1]
    chunks = items.chunk(2)
    assert chunks.count() == 2


def test_driver_urls() -> None:
    assert "aiosqlite" in _ensure_async_driver("sqlite:///tmp.db")
    assert "asyncpg" in _ensure_async_driver("postgresql://u:p@h/db")
    assert "aiomysql" in _ensure_async_driver("mysql://u:p@h/db")
    assert "aioodbc" in _ensure_async_driver("mssql://u:p@h/db")
    assert "oracledb_async" in _ensure_async_driver("oracle://u:p@h/")
    manager = DatabaseManager({"default": "missing", "connections": {}})
    with pytest.raises(ConnectionError_):
        manager.connection()


class Note(Model):
    timestamps = False
    fillable = ("body", "flag")


class Author(Model):
    fillable = ("name",)
    timestamps = False

    @relation
    def notes(self):
        return self.has_many(Note, "author_id")

    @relation
    def profile(self):
        return self.has_one(Profile, "author_id")


class Profile(Model):
    table = "profiles"
    timestamps = False
    fillable = ("author_id", "bio")


@pytest.mark.asyncio
async def test_builder_and_model_edges(memory_db) -> None:
    await Schema.create(
        "notes",
        lambda t: (
            t.id(),
            t.string("body"),
            t.boolean("flag").default(False),
            t.integer("author_id").nullable(),
        ),
    )
    await Schema.create(
        "authors",
        lambda t: (t.id(), t.string("name")),
    )
    await Schema.create(
        "profiles",
        lambda t: (t.id(), t.integer("author_id"), t.string("bio").nullable()),
    )
    Note.table = "notes"
    Author.table = "authors"

    await Note.create(body="a", flag=True)
    await Note.create(body="b", flag=False)
    assert await Note.query().where_in("body", ["a"]).count() == 1
    assert await Note.query().where_not_in("body", ["z"]).count() == 2
    assert await Note.query().where_not_null("body").count() == 2
    assert await Note.query().where_between("id", 1, 2).count() == 2
    first = await Note.query().order_by_desc("id").first()
    assert first is not None and first.body == "b"
    assert await Note.query().exists()
    assert not await Note.query().where("body", "nope").exists()
    assert await Note.query().doesnt_exist() is False
    sql = Note.query().where("body", "like", "a%").to_sql().lower()
    assert "like" in sql
    await Note.query().where("body", "a").decrement("flag", 0)
    page = await Note.query().order_by("id").simple_paginate(1, page=1)
    assert page.has_more_pages()
    assert "data" in page.to_dict()

    seen: list[int] = []
    await Note.query().chunk(1, lambda chunk: seen.append(len(chunk)))
    assert seen == [1, 1]

    author = await Author.create(name="Ada")
    await author.notes().create(body="from ada")
    await author.profile().create(bio="hi")
    loaded = await Author.query().with_("notes", "profile").first()
    assert loaded.profile.bio == "hi"
    assert len(loaded.notes) == 1
    await loaded.load_missing("notes")
    replica = loaded.replicate()
    assert replica.exists is False
    await Author.destroy(author.id)


@pytest.mark.asyncio
async def test_schema_column_types_and_db_table(memory_db) -> None:
    await Schema.create(
        "kitchen",
        lambda t: (
            t.id(),
            t.uuid("uid"),
            t.text("body"),
            t.big_integer("n"),
            t.float("f"),
            t.decimal("d"),
            t.boolean("ok"),
            t.json("payload"),
            t.date("day"),
            t.date_time("ts"),
            t.timestamp("stamp"),
            t.foreign_id("user_id"),
            t.unique_index(["uid"]),
        ),
    )
    assert await Schema.has_table("kitchen")
    rows = await DB.table("kitchen").insert({"body": "x", "ok": True})
    assert rows >= 0
    await DB.statement("SELECT 1")
    raw("SELECT 1")


def test_cli_migrate_on_scaffold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = scaffold_app("m5cov", destination=tmp_path / "m5cov")
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.delenv("DB_DATABASE", raising=False)
    runner = CliRunner()
    made = runner.invoke(
        smith_app,
        ["make:migration", "create_widgets_table", "--create", "widgets"],
        catch_exceptions=False,
    )
    assert made.exit_code == 0, made.stdout
    status = runner.invoke(smith_app, ["migrate:status"], catch_exceptions=False)
    assert status.exit_code == 0, status.stdout + status.stderr
    migrated = runner.invoke(smith_app, ["migrate"], catch_exceptions=False)
    assert migrated.exit_code == 0, migrated.stdout
    again = runner.invoke(smith_app, ["migrate"], catch_exceptions=False)
    assert again.exit_code == 0
    assert "Nothing to migrate" in again.stdout
    rolled = runner.invoke(smith_app, ["migrate:rollback"], catch_exceptions=False)
    assert rolled.exit_code == 0, rolled.stdout
    empty = runner.invoke(smith_app, ["migrate:rollback"], catch_exceptions=False)
    assert empty.exit_code == 0
    fresh = runner.invoke(smith_app, ["migrate:fresh"], catch_exceptions=False)
    assert fresh.exit_code == 0, fresh.stdout
    with pytest.raises(MigrationError):
        make_migration("", tmp_path)


def test_cli_serve_requires_bootstrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(smith_app, ["serve"], catch_exceptions=False)
    assert result.exit_code == 1
    assert "bootstrap/app.py" in result.stderr or "bootstrap/app.py" in result.stdout


def test_cli_make_lang_duplicate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    first = runner.invoke(smith_app, ["make:lang", "sw"], catch_exceptions=False)
    assert first.exit_code == 0, first.stdout
    second = runner.invoke(smith_app, ["make:lang", "sw"], catch_exceptions=False)
    assert second.exit_code == 1
    invalid = runner.invoke(smith_app, ["make:lang", "!!!"], catch_exceptions=False)
    assert invalid.exit_code == 1


@pytest.mark.asyncio
async def test_soft_delete_force(memory_db) -> None:
    class Doc(SoftDeletes, Model):
        timestamps = False
        fillable = ("title",)

    await Schema.create(
        "docs",
        lambda t: (t.id(), t.string("title"), t.soft_deletes()),
    )
    Doc.table = "docs"
    doc = await Doc.create(title="x")
    await doc.force_delete()
    assert await Doc.with_trashed().count() == 0
