"""M44 — dialect conformance executed on every claimed engine.

Compile-only coverage already lives in ``test_m42_dialects.py`` and the M43
alter suites. This module *runs* the paths that differ per dialect: schema
DDL, upsert, JSON wheres, locking, transactions / savepoints, and pagination.

Point ``ALMASIX_TEST_DB`` at ``sqlite`` (default), ``pgsql``, ``mysql``, or
``mariadb`` — CI runs the matrix; locals stay offline on SQLite.
"""

from __future__ import annotations

import json

import pytest

from almasix.orm import DB, Schema
from almasix.orm.model import Model
from tests.orm_support import engine_capabilities, skip_on_engine
from tests.orm_support import test_engine as active_engine

pytest_plugins = ("tests.orm_support",)


class Account(Model):
    table = "m44_accounts"
    timestamps = False
    fillable = ("email", "name")


async def _accounts_table() -> None:
    await Schema.drop_if_exists("m44_accounts")
    await Schema.create(
        "m44_accounts",
        lambda t: (
            t.id(),
            t.string("email"),
            t.string("name"),
            t.unique(["email"]),
        ),
    )


async def _posts_table() -> None:
    await Schema.drop_if_exists("m44_posts")
    await Schema.create(
        "m44_posts",
        lambda t: (
            t.id(),
            t.string("title"),
            t.json("meta").nullable(),
        ),
    )


# --- schema DDL -------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_create_and_inspect_round_trip(memory_db) -> None:
    await _posts_table()
    assert await Schema.has_table("m44_posts")
    assert await Schema.has_columns("m44_posts", ["id", "title", "meta"])
    columns = await Schema.columns("m44_posts")
    assert {column["name"] for column in columns} >= {"id", "title", "meta"}
    await Schema.drop("m44_posts")
    assert not await Schema.has_table("m44_posts")


@pytest.mark.asyncio
@skip_on_engine("sqlite")
async def test_schema_change_column_on_server_engines(memory_db) -> None:
    await Schema.drop_if_exists("m44_alter")
    await Schema.create(
        "m44_alter",
        lambda t: (t.id(), t.string("label", 20)),
    )
    await Schema.table(
        "m44_alter",
        lambda t: t.string("label", 40).nullable().change(),
    )
    assert await Schema.has_column("m44_alter", "label")
    await Schema.drop_if_exists("m44_alter")


# --- upsert -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_native_upsert_round_trip(memory_db) -> None:
    assert engine_capabilities()["native_upsert"]
    await _accounts_table()

    assert (
        await Account.query().upsert(
            {"email": "a@b.c", "name": "Ada"},
            unique_by=["email"],
            update=["name"],
        )
        >= 1
    )
    assert (
        await Account.query().upsert(
            [
                {"email": "a@b.c", "name": "Updated"},
                {"email": "g@b.c", "name": "Grace"},
            ],
            unique_by=["email"],
            update=["name"],
        )
        >= 1
    )
    names = await Account.query().order_by("email").pluck("name")
    assert names.all() == ["Updated", "Grace"]


# --- JSON wheres ------------------------------------------------------------


@pytest.mark.asyncio
async def test_json_path_wheres_and_updates(memory_db) -> None:
    await _posts_table()
    await DB.table("m44_posts").insert(
        [
            {
                "title": "Ada",
                "meta": json.dumps({"languages": ["en", "fr"], "alerts": {"email": True}}),
            },
            {
                "title": "Grace",
                "meta": json.dumps({"languages": ["en"], "alerts": {"email": False}}),
            },
        ]
    )

    multilingual = (
        await DB.table("m44_posts").where_json_length("meta->languages", ">", 1).pluck("title")
    )
    assert list(multilingual) == ["Ada"]

    emailed = await DB.table("m44_posts").where("meta->alerts->email", True).pluck("title")
    assert list(emailed) == ["Ada"]

    contains = (
        await DB.table("m44_posts").where_json_contains("meta->languages", "fr").pluck("title")
    )
    assert list(contains) == ["Ada"]

    await DB.table("m44_posts").where("title", "Grace").update({"meta->alerts->email": True})
    raw = await DB.table("m44_posts").where("title", "Grace").value("meta")
    updated = raw if isinstance(raw, dict) else json.loads(raw)
    assert updated["alerts"]["email"] is True


# --- locking ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_row_locks_compile_and_run(memory_db) -> None:
    await _posts_table()
    await DB.table("m44_posts").insert({"title": "locked", "meta": None})

    async with DB.transaction():
        rows = await DB.table("m44_posts").where("title", "locked").lock_for_update().get()
        assert len(rows) == 1
        shared = await DB.table("m44_posts").where("title", "locked").shared_lock().get()
        assert len(shared) == 1

    # SQLite ignores lock clauses; server engines emit them. Either way the
    # query must succeed rather than raise.
    assert active_engine() in {"sqlite", "pgsql", "mysql", "mariadb"}


# --- transactions / savepoints ----------------------------------------------


@pytest.mark.asyncio
async def test_transactions_and_nested_savepoints(memory_db) -> None:
    await _posts_table()

    # Nested ``async with DB.transaction()`` uses a SAVEPOINT; an inner raise
    # undoes only the inner work.
    async with DB.transaction():
        await DB.table("m44_posts").insert({"title": "outer", "meta": None})
        assert DB.transaction_level() == 1
        with pytest.raises(RuntimeError, match="roll the savepoint"):
            async with DB.transaction():
                await DB.table("m44_posts").insert({"title": "inner", "meta": None})
                raise RuntimeError("roll the savepoint back")

    titles = list(await DB.table("m44_posts").order_by("id").pluck("title"))
    assert titles == ["outer"]

    # Hand-opened nesting reports depth and rolls the inner frame alone.
    await DB.begin_transaction()
    await DB.table("m44_posts").insert({"title": "manual", "meta": None})
    await DB.begin_transaction()
    assert DB.transaction_level() == 2
    await DB.table("m44_posts").insert({"title": "nested", "meta": None})
    await DB.rollback()
    await DB.commit()
    titles = list(await DB.table("m44_posts").order_by("id").pluck("title"))
    assert titles == ["outer", "manual"]


# --- pagination -------------------------------------------------------------


@pytest.mark.asyncio
async def test_offset_and_cursor_pagination(memory_db) -> None:
    await _posts_table()
    await DB.table("m44_posts").insert([{"title": f"Post {n}", "meta": None} for n in range(1, 8)])

    page = await DB.table("m44_posts").order_by("id").paginate(3, 2)
    assert [row["title"] for row in page] == ["Post 4", "Post 5", "Post 6"]
    assert page.total == 7

    simple = await DB.table("m44_posts").order_by("id").simple_paginate(3, 1)
    assert [row["title"] for row in simple] == ["Post 1", "Post 2", "Post 3"]
    assert simple.has_more_pages()

    first = await DB.table("m44_posts").order_by("id").cursor_paginate(3)
    assert [row["title"] for row in first] == ["Post 1", "Post 2", "Post 3"]
    second = await DB.table("m44_posts").order_by("id").cursor_paginate(3, first.next_cursor())
    assert [row["title"] for row in second] == ["Post 4", "Post 5", "Post 6"]
