"""Altering a table after it exists — change, drop, rename, and what the schema says back."""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import mssql, mysql, oracle, postgresql, sqlite

from almasix.orm import Schema, SchemaError
from almasix.orm.blueprint import Blueprint
from almasix.orm.facade import DB
from almasix.orm.schema import compile_table_statements, rename_table_sql
from tests.orm_support import memory_db  # noqa: F401


def statements(callback, dialect) -> list[str]:
    blueprint = Blueprint("posts")
    callback(blueprint)
    return compile_table_statements(blueprint, dialect)


# --- change() ---------------------------------------------------------------


def test_change_restates_the_whole_column_for_mysql() -> None:
    """MySQL takes a whole definition, which is why Laravel's change() drops what it omits."""
    sql = statements(
        lambda t: t.string("title", 100).nullable(False).default("Untitled").change(),
        mysql.dialect(),
    )
    assert sql == [
        "ALTER TABLE `posts` MODIFY title VARCHAR(100) NOT NULL DEFAULT 'Untitled'"
    ]


def test_change_on_postgresql_says_one_thing_at_a_time() -> None:
    sql = statements(lambda t: t.integer("votes").nullable(False).default(0).change(), postgresql.dialect())
    assert sql == [
        'ALTER TABLE "posts" ALTER COLUMN "votes" TYPE INTEGER USING "votes"::INTEGER',
        'ALTER TABLE "posts" ALTER COLUMN "votes" SET NOT NULL',
        'ALTER TABLE "posts" ALTER COLUMN "votes" SET DEFAULT 0',
    ]

    dropped = statements(lambda t: t.string("title").change(), postgresql.dialect())
    assert dropped[1].endswith("DROP NOT NULL")
    assert dropped[2].endswith("DROP DEFAULT")

    stamped = statements(lambda t: t.timestamp("seen_at").use_current().change(), postgresql.dialect())
    assert stamped[2].endswith("SET DEFAULT CURRENT_TIMESTAMP")


def test_change_on_the_engines_that_spell_it_differently() -> None:
    assert statements(lambda t: t.string("title").change(), mssql.dialect()) == [
        "ALTER TABLE [posts] ALTER COLUMN [title] VARCHAR(255) NULL"
    ]
    assert statements(
        lambda t: t.string("title").nullable(False).change(), mssql.dialect()
    ) == ["ALTER TABLE [posts] ALTER COLUMN [title] VARCHAR(255) NOT NULL"]
    assert statements(lambda t: t.integer("votes").change(), oracle.dialect()) == [
        'ALTER TABLE "posts" MODIFY (votes INTEGER)'
    ]


def test_sqlite_cannot_change_a_column_and_says_so() -> None:
    with pytest.raises(SchemaError, match="copy the values across"):
        statements(lambda t: t.string("title").change(), sqlite.dialect())


def test_a_changed_column_is_not_added_again() -> None:
    """`change()` and an added column in one blueprint stay separate statements."""
    sql = statements(
        lambda t: (t.string("title", 60).change(), t.string("slug").index()),
        mysql.dialect(),
    )
    assert sql[0].startswith("ALTER TABLE `posts` MODIFY title")
    assert sql[1].startswith("ALTER TABLE `posts` ADD COLUMN slug")
    assert sql[2].startswith("CREATE INDEX")


async def test_change_runs_against_a_live_postgresql_shaped_blueprint(memory_db) -> None:
    """SQLite cannot run it, so the compile is the contract; the add path still runs."""
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    with pytest.raises(SchemaError):
        await Schema.table("posts", lambda table: table.string("title", 60).change())
    assert await Schema.has_column("posts", "title")


# --- dropping ----------------------------------------------------------------


def test_dropping_indexes_keys_and_the_primary_key() -> None:
    my = mysql.dialect()
    assert statements(lambda t: t.drop_index("ix_posts_slug"), my) == [
        "ALTER TABLE `posts` DROP INDEX `ix_posts_slug`"
    ]
    assert statements(lambda t: t.drop_unique(["slug"]), postgresql.dialect()) == [
        'DROP INDEX "uq_posts_slug"'
    ]
    assert statements(lambda t: t.drop_foreign(["user_id"]), my) == [
        "ALTER TABLE `posts` DROP FOREIGN KEY `posts_user_id_foreign`"
    ]
    assert statements(lambda t: t.drop_foreign("user_id"), postgresql.dialect()) == [
        'ALTER TABLE "posts" DROP CONSTRAINT "posts_user_id_foreign"'
    ]
    assert statements(lambda t: t.drop_primary(), my) == ["ALTER TABLE `posts` DROP PRIMARY KEY"]
    assert statements(lambda t: t.drop_primary(), postgresql.dialect()) == [
        'ALTER TABLE "posts" DROP CONSTRAINT "posts_pkey"'
    ]


def test_a_named_drop_takes_the_name_it_is_given() -> None:
    assert statements(lambda t: t.drop_unique(name="posts_slug_unique"), mysql.dialect()) == [
        "ALTER TABLE `posts` DROP INDEX `posts_slug_unique`"
    ]
    assert statements(
        lambda t: t.drop_foreign(name="fk_author"), postgresql.dialect()
    ) == ['ALTER TABLE "posts" DROP CONSTRAINT "fk_author"']


def test_sqlite_cannot_drop_constraints_and_says_so() -> None:
    lite = sqlite.dialect()
    with pytest.raises(SchemaError, match="drop a foreign key"):
        statements(lambda t: t.drop_foreign(["user_id"]), lite)
    with pytest.raises(SchemaError, match="drop a primary key"):
        statements(lambda t: t.drop_primary(), lite)
    with pytest.raises(SchemaError, match="rename an index"):
        statements(lambda t: t.rename_index("a", "b"), lite)


def test_drop_constrained_foreign_id_drops_both_halves() -> None:
    sql = statements(lambda t: t.drop_constrained_foreign_id("user_id"), mysql.dialect())
    assert sql == [
        "ALTER TABLE `posts` DROP FOREIGN KEY `posts_user_id_foreign`",
        "ALTER TABLE `posts` DROP COLUMN `user_id`",
    ]


async def test_the_convenience_drops_remove_what_they_added(memory_db) -> None:
    await Schema.create(
        "posts",
        lambda table: (
            table.id(),
            table.string("title"),
            table.remember_token(),
            table.morphs("owner"),
            table.timestamps(),
            table.soft_deletes(),
        ),
    )
    await Schema.table(
        "posts",
        lambda table: (
            table.drop_timestamps(),
            table.drop_soft_deletes(),
            table.drop_remember_token(),
            table.drop_morphs("owner"),
        ),
    )
    names = {column["name"] for column in await Schema.columns("posts")}
    assert names == {"id", "title"}


def test_renaming_an_index_per_engine() -> None:
    assert statements(lambda t: t.rename_index("a", "b"), mysql.dialect()) == [
        "ALTER TABLE `posts` RENAME INDEX `a` TO `b`"
    ]
    assert statements(lambda t: t.rename_index("a", "b"), postgresql.dialect()) == [
        'ALTER INDEX "a" RENAME TO "b"'
    ]
    assert statements(lambda t: t.rename_index("a", "b"), mssql.dialect()) == [
        "EXEC sp_rename 'posts.a', 'b', 'INDEX'"
    ]


def test_adding_a_primary_key_after_the_fact() -> None:
    assert statements(lambda t: t.primary(["a", "b"]), postgresql.dialect()) == [
        'ALTER TABLE "posts" ADD PRIMARY KEY ("a", "b")'
    ]
    assert statements(lambda t: t.primary("a", "pk_posts"), postgresql.dialect()) == [
        'ALTER TABLE "posts" ADD CONSTRAINT "pk_posts" PRIMARY KEY ("a")'
    ]


async def test_a_primary_key_declared_at_create_time(memory_db) -> None:
    await Schema.create(
        "tags",
        lambda table: (table.string("locale", 5), table.string("slug"), table.primary(["locale", "slug"])),
    )
    await DB.table("tags").insert({"locale": "en", "slug": "php"})
    with pytest.raises(Exception, match="UNIQUE|PRIMARY"):
        await DB.table("tags").insert({"locale": "en", "slug": "php"})


# --- renaming tables ------------------------------------------------------------


async def test_renaming_a_table(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert({"title": "First"})
    await Schema.rename("posts", "articles")
    assert not await Schema.has_table("posts")
    assert await DB.table("articles").count() == 1


def test_rename_table_sql_per_engine() -> None:
    assert rename_table_sql("a", "b", mysql.dialect()) == "RENAME TABLE `a` TO `b`"
    assert rename_table_sql("a", "b", postgresql.dialect()) == 'ALTER TABLE "a" RENAME TO "b"'
    assert rename_table_sql("a", "b", mssql.dialect()) == "EXEC sp_rename 'a', 'b'"


# --- inspection -------------------------------------------------------------------


async def test_what_the_schema_says_about_a_table(memory_db) -> None:
    await Schema.create(
        "users",
        lambda table: (table.id(), table.string("email").unique()),
    )
    await Schema.create(
        "posts",
        lambda table: (
            table.id(),
            table.string("title"),
            table.string("slug").index(),
            table.foreign_id("user_id").constrained().cascade_on_delete(),
        ),
    )

    assert await Schema.has_columns("posts", ["title", "slug"])
    assert not await Schema.has_columns("posts", ["title", "missing"])
    assert (await Schema.column_type("posts", "title")).startswith("VARCHAR")
    with pytest.raises(SchemaError, match="no column"):
        await Schema.column_type("posts", "missing")

    indexes = await Schema.get_indexes("posts")
    assert any(index["columns"] == ["slug"] and not index["unique"] for index in indexes)
    assert any(index["primary"] and index["columns"] == ["id"] for index in indexes)
    assert await Schema.has_index("posts", ["slug"])
    assert await Schema.has_index("posts", "ix_posts_slug")
    assert not await Schema.has_index("posts", ["slug"], unique=True)
    assert not await Schema.has_index("posts", ["nothing"])

    keys = await Schema.get_foreign_keys("posts")
    assert keys[0]["foreign_table"] == "users"
    assert keys[0]["columns"] == ["user_id"]
    assert keys[0]["on_delete"] == "CASCADE"

    assert await Schema.get_indexes("absent") == []
    assert await Schema.get_foreign_keys("absent") == []


async def test_views_are_listed_when_there_are_any(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.statement("CREATE VIEW recent AS SELECT * FROM posts")
    views = await Schema.get_views()
    assert [view["name"] for view in views] == ["recent"]
    assert "SELECT" in views[0]["definition"]


async def test_create_if_not_exists_leaves_a_table_alone(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.create_if_not_exists("posts", lambda table: table.string("other"))
    assert not await Schema.has_column("posts", "other")

    await Schema.create_if_not_exists("tags", lambda table: (table.id(), table.string("name")))
    assert await Schema.has_table("tags")


async def test_the_conditional_helpers_run_only_when_they_should(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await Schema.when_table_has_column("posts", "title", lambda table: table.string("subtitle"))
    await Schema.when_table_has_column("posts", "absent", lambda table: table.string("never"))
    await Schema.when_table_doesnt_have_column("posts", "slug", lambda table: table.string("slug"))
    await Schema.when_table_doesnt_have_column("posts", "title", lambda table: table.string("also_never"))

    names = {column["name"] for column in await Schema.columns("posts")}
    assert {"subtitle", "slug"} <= names
    assert "never" not in names and "also_never" not in names


async def test_dropping_every_table_ignores_the_order_they_reference_each_other_in(memory_db) -> None:
    await Schema.create("users", lambda table: (table.id(), table.string("email")))
    await Schema.create(
        "posts",
        lambda table: (table.id(), table.foreign_id("user_id").constrained()),
    )
    await Schema.drop_all_tables()
    assert await Schema.table_names() == []
    await Schema.drop_all_tables()  # nothing left to do, and nothing to complain about


def test_how_each_engine_switches_constraint_checking() -> None:
    from almasix.orm.schema import _foreign_key_switch

    assert _foreign_key_switch(sqlite.dialect(), False) == "PRAGMA foreign_keys=OFF"
    assert _foreign_key_switch(mysql.dialect(), True) == "SET FOREIGN_KEY_CHECKS=1"
    assert (
        _foreign_key_switch(postgresql.dialect(), False)
        == "SET session_replication_role = replica"
    )
    # SQL Server checks per constraint, so there is nothing global to say.
    assert _foreign_key_switch(mssql.dialect(), False) is None


async def test_an_engine_with_no_global_switch_is_left_alone(memory_db, monkeypatch) -> None:
    import almasix.orm.schema as schema_module

    monkeypatch.setattr(schema_module, "_foreign_key_switch", lambda dialect, enabled: None)
    await Schema.disable_foreign_key_constraints()
    await Schema.enable_foreign_key_constraints()


async def test_a_table_with_no_primary_key_reports_none(memory_db) -> None:
    await Schema.create("logs", lambda table: table.string("line"))
    assert all(not index["primary"] for index in await Schema.get_indexes("logs"))


async def test_foreign_keys_can_be_switched_off_around_a_block(memory_db) -> None:
    await Schema.create("users", lambda table: (table.id(),))
    await Schema.create(
        "posts",
        lambda table: (table.id(), table.foreign_id("user_id").constrained()),
    )
    await DB.statement("PRAGMA foreign_keys=ON")

    async with Schema.without_foreign_key_constraints():
        await DB.table("posts").insert({"user_id": 999})
    assert await DB.table("posts").count() == 1
