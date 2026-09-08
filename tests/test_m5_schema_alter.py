"""Schema.table alter APIs — after/before, rename, unique indexes, foreign keys."""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import mysql, postgresql

from almasix.orm import Schema, SchemaError
from almasix.orm.facade import DB
from almasix.orm.schema import Blueprint, compile_table_statements
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def test_after_and_before_compile_for_mysql(memory_db) -> None:
    """after()/before() are MySQL/MariaDB positioning; still add the column on SQLite."""
    await Schema.create(
        "posts",
        lambda table: (table.id(), table.string("title"), table.timestamps()),
    )
    await Schema.table(
        "posts",
        lambda table: table.string("slug").nullable().after("title"),
    )
    assert await Schema.has_column("posts", "slug")

    bp_after = Blueprint("posts")
    bp_after.string("excerpt").after("title")
    after_sql = compile_table_statements(bp_after, mysql.dialect())[0]
    assert "AFTER `title`" in after_sql

    bp_before = Blueprint("posts")
    bp_before.string("subtitle").before("title")
    before_sql = compile_table_statements(bp_before, mysql.dialect())[0]
    assert "BEFORE `title`" in before_sql

    # SQLite ignores position keywords (dialect is not mysql).
    bp_sqlite = Blueprint("posts")
    bp_sqlite.string("ignore_pos").after("title")
    sqlite_sql = compile_table_statements(bp_sqlite, memory_db.connection().engine.dialect)[0]
    assert "AFTER" not in sqlite_sql


async def test_rename_column(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.table("posts", lambda table: table.rename_column("title", "headline"))
    assert await Schema.has_column("posts", "headline")
    assert not await Schema.has_column("posts", "title")


async def test_unique_index_single_and_composite(memory_db) -> None:
    await Schema.create(
        "posts",
        lambda table: (
            table.id(),
            table.string("slug"),
            table.string("locale"),
            table.string("email"),
        ),
    )
    await Schema.table("posts", lambda table: table.unique("email"))
    assert await Schema.has_index("posts", "uq_posts_email")

    await Schema.table(
        "posts",
        lambda table: table.unique(["slug", "locale"], name="posts_slug_locale_unique"),
    )
    assert await Schema.has_index("posts", "posts_slug_locale_unique")

    await Schema.table("posts", lambda table: table.string("code").unique())
    assert await Schema.has_column("posts", "code")


async def test_foreign_id_constrained_on_add(memory_db) -> None:
    await Schema.create("users", lambda table: (table.id(), table.string("name")))
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.table(
        "posts",
        lambda table: (
            table.foreign_id("user_id").nullable().constrained().cascade_on_delete(),
        ),
    )
    assert await Schema.has_column("posts", "user_id")

    user_id = await DB.table("users").insert_get_id({"name": "Ada"})
    await DB.table("posts").insert({"title": "Hello", "user_id": user_id})
    with pytest.raises(Exception):
        await DB.table("posts").insert({"title": "Orphan", "user_id": 99999})


async def test_foreign_id_constrained_custom_table(memory_db) -> None:
    await Schema.create("authors", lambda table: (table.id(), table.string("name")))
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.table(
        "posts",
        lambda table: table.foreign_id("author_id").constrained("authors").null_on_delete(),
    )
    assert await Schema.has_column("posts", "author_id")


async def test_foreign_on_existing_column_sqlite_raises(memory_db) -> None:
    await Schema.create("users", lambda table: (table.id(),))
    await Schema.create(
        "posts",
        lambda table: (table.id(), table.integer("user_id")),
    )
    with pytest.raises(SchemaError, match="SQLite cannot add a foreign key"):
        await Schema.table(
            "posts",
            lambda table: table.foreign("user_id").references("id").on("users").cascade_on_delete(),
        )


async def test_foreign_on_existing_column_compiles_for_postgres(memory_db) -> None:
    bp = Blueprint("posts")
    bp.foreign("user_id").references("id").on("users").cascade_on_delete().cascade_on_update()
    sql = compile_table_statements(bp, postgresql.dialect())
    assert len(sql) == 1
    assert 'ADD CONSTRAINT "posts_user_id_foreign"' in sql[0]
    assert 'FOREIGN KEY ("user_id") REFERENCES "users" ("id")' in sql[0]
    assert "ON DELETE CASCADE" in sql[0]
    assert "ON UPDATE CASCADE" in sql[0]


async def test_create_with_foreign_id_constrained(memory_db) -> None:
    await Schema.create("users", lambda table: (table.id(), table.string("email")))
    await Schema.create(
        "posts",
        lambda table: (
            table.id(),
            table.string("title"),
            table.foreign_id("user_id").constrained().cascade_on_delete(),
        ),
    )
    assert await Schema.has_column("posts", "user_id")
