"""The column catalogue and its modifiers — Laravel's Migrations page, type by type."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql, sqlite

from almasix.orm import Schema
from almasix.orm.blueprint import Blueprint
from almasix.orm.facade import DB
from almasix.orm.grammar import UnsupportedByDialectError
from almasix.orm.schema import compile_table_statements
from tests.orm_support import memory_db  # noqa: F401


def column_sql(blueprint: Blueprint, dialect, index: int = 0) -> str:
    """The DDL one blueprint column compiles to, for the engine in front of us."""
    column = blueprint.columns[index].to_sqlalchemy(dialect)
    sa.Table("t", sa.MetaData()).append_column(column)
    return str(sa.schema.CreateColumn(column).compile(dialect=dialect))


def type_sql(blueprint: Blueprint, dialect, index: int = 0) -> str:
    return blueprint.columns[index].sa_type(dialect).compile(dialect=dialect)


# --- the catalogue ----------------------------------------------------------


async def test_every_column_type_survives_a_round_trip(memory_db) -> None:
    """Each type creates a column and reads a value back as itself."""

    def everything(table: Blueprint) -> None:
        table.id()
        table.char("code", 4)
        table.string("name")
        table.string("nickname", 32)
        table.tiny_text("blurb")
        table.text("body")
        table.medium_text("notes")
        table.long_text("essay")
        table.tiny_integer("rating")
        table.small_integer("rank")
        table.medium_integer("hits")
        table.integer("votes")
        table.big_integer("views")
        table.unsigned_integer("age")
        table.unsigned_big_integer("distance")
        table.float("weight")
        table.double("balance")
        table.decimal("price", 8, 2)
        table.boolean("active")
        table.enum("status", ["draft", "published"])
        table.json("options")
        table.jsonb("meta")
        table.date("published_on")
        table.date_time("scheduled_at")
        table.time("opens_at")
        table.year("vintage")
        table.binary("avatar")
        table.uuid()
        table.ulid()
        table.ip_address()
        table.mac_address()
        table.remember_token()
        table.timestamps()
        table.soft_deletes()

    await Schema.create("things", everything)

    await DB.table("things").insert(
        {
            "code": "ab12",
            "name": "Widget",
            "rating": 5,
            "votes": 3,
            "active": True,
            "status": "draft",
            "options": {"colour": "red"},
            "price": 9.5,
            "uuid": "0f8f-etc",
            "ip_address": "127.0.0.1",
        }
    )
    row = await DB.table("things").first()
    assert row["name"] == "Widget"
    assert row["status"] == "draft"
    # The builder writes a document and reads the text back, as Laravel's does.
    assert row["options"] == '{"colour": "red"}'
    assert row["remember_token"] is None

    names = {column["name"] for column in await Schema.columns("things")}
    assert {"essay", "vintage", "ulid", "mac_address", "deleted_at"} <= names


async def test_the_timestamp_and_soft_delete_families(memory_db) -> None:
    await Schema.create(
        "events",
        lambda table: (
            table.id(),
            table.date_time_tz("starts_at"),
            table.time_tz("doors_at"),
            table.timestamp("noticed_at"),
            table.timestamp_tz("seen_at"),
            table.timestamps_tz(),
            table.soft_deletes_tz(),
        ),
    )
    names = {column["name"] for column in await Schema.columns("events")}
    assert {"starts_at", "doors_at", "seen_at", "created_at", "updated_at", "deleted_at"} <= names

    nullable = Blueprint("t")
    nullable.nullable_timestamps()
    assert [column.name for column in nullable.columns] == ["created_at", "updated_at"]


def test_the_widths_mysql_spells_its_own_way() -> None:
    """A blueprint means the same thing on every engine, in each engine's words."""
    blueprint = Blueprint("t")
    blueprint.tiny_integer("a")
    blueprint.medium_integer("b")
    blueprint.tiny_text("c")
    blueprint.medium_text("d")
    blueprint.long_text("e")
    blueprint.year("f")
    blueprint.set("g", ["x", "y"])
    blueprint.enum("h", ["on", "off"])

    my = mysql.dialect()
    assert type_sql(blueprint, my, 0) == "TINYINT"
    assert type_sql(blueprint, my, 1) == "MEDIUMINT"
    assert type_sql(blueprint, my, 2) == "TINYTEXT"
    assert type_sql(blueprint, my, 3) == "MEDIUMTEXT"
    assert type_sql(blueprint, my, 4) == "LONGTEXT"
    assert type_sql(blueprint, my, 5) == "YEAR"
    assert type_sql(blueprint, my, 6) == "SET('x','y')"
    assert type_sql(blueprint, my, 7) == "ENUM('on','off')"

    lite = sqlite.dialect()
    assert type_sql(blueprint, lite, 0) == "SMALLINT"
    assert type_sql(blueprint, lite, 2) == "TEXT"
    assert type_sql(blueprint, lite, 5) == "INTEGER"
    assert "VARCHAR" in type_sql(blueprint, lite, 6)


def test_jsonb_and_uuid_are_native_on_postgresql() -> None:
    blueprint = Blueprint("t")
    blueprint.jsonb("meta")
    blueprint.uuid()
    blueprint.json("plain")

    pg = postgresql.dialect()
    assert type_sql(blueprint, pg, 0) == "JSONB"
    assert type_sql(blueprint, pg, 1) == "UUID"
    assert type_sql(blueprint, pg, 2) == "JSON"
    assert type_sql(blueprint, sqlite.dialect(), 0) == "JSON"
    assert type_sql(blueprint, sqlite.dialect(), 1) == "VARCHAR(36)"


def test_an_auto_incrementing_key_of_every_width() -> None:
    blueprint = Blueprint("t")
    blueprint.increments("a")
    blueprint.tiny_increments("b")
    blueprint.small_increments("c")
    blueprint.medium_increments("d")
    blueprint.big_increments("e")

    my = mysql.dialect()
    assert type_sql(blueprint, my, 1) == "TINYINT UNSIGNED"
    assert type_sql(blueprint, my, 3) == "MEDIUMINT UNSIGNED"
    assert type_sql(blueprint, my, 4) == "BIGINT"

    # SQLite only counts up for INTEGER PRIMARY KEY, so every width narrows.
    lite = sqlite.dialect()
    assert {type_sql(blueprint, lite, index) for index in range(5)} == {"INTEGER"}
    assert all(column.options["primary_key"] for column in blueprint.columns)


async def test_id_is_a_big_increments_that_still_counts_on_sqlite(memory_db) -> None:
    await Schema.create("posts", lambda table: (table.id(), table.string("title")))
    await DB.table("posts").insert({"title": "First"})
    await DB.table("posts").insert({"title": "Second"})
    assert await DB.table("posts").pluck("id") == [1, 2]
    assert type_sql(_with(lambda t: t.id()), mysql.dialect()) == "BIGINT"


def _with(callback) -> Blueprint:
    blueprint = Blueprint("t")
    callback(blueprint)
    return blueprint


def test_unsigned_is_mysqls_and_is_a_no_op_elsewhere() -> None:
    blueprint = _with(
        lambda t: (
            t.unsigned_tiny_integer("a"),
            t.unsigned_small_integer("b"),
            t.unsigned_medium_integer("c"),
            t.unsigned_integer("d"),
            t.unsigned_big_integer("e"),
            t.unsigned_decimal("f", 6, 3),
            t.string("g").unsigned(),
        )
    )
    my = mysql.dialect()
    assert type_sql(blueprint, my, 0) == "TINYINT UNSIGNED"
    assert type_sql(blueprint, my, 1) == "SMALLINT UNSIGNED"
    assert type_sql(blueprint, my, 3) == "INTEGER UNSIGNED"
    assert type_sql(blueprint, my, 4) == "BIGINT UNSIGNED"
    assert type_sql(blueprint, my, 5) == "DECIMAL(6, 3) UNSIGNED"
    # A width PostgreSQL has no unsigned form of stays itself.
    assert type_sql(blueprint, postgresql.dialect(), 4) == "BIGINT"
    assert type_sql(blueprint, my, 6) == "VARCHAR(255)"


def test_a_raw_column_is_written_out_word_for_word() -> None:
    blueprint = _with(lambda t: t.raw_column("shape", "GEOMETRY NOT NULL SRID 4326"))
    assert "GEOMETRY NOT NULL SRID 4326" in column_sql(blueprint, mysql.dialect())


def test_the_string_length_a_blueprint_reaches_for_by_default() -> None:
    assert type_sql(_with(lambda t: t.string("a")), mysql.dialect()) == "VARCHAR(255)"
    assert type_sql(_with(lambda t: t.string("a", 64)), mysql.dialect()) == "VARCHAR(64)"


# --- spatial and vector -----------------------------------------------------


def test_spatial_and_vector_types_per_engine() -> None:
    blueprint = _with(
        lambda t: (
            t.vector("embedding", 3),
            t.geometry("area"),
            t.geometry("spot", "point", srid=4326),
            t.geography("region"),
        )
    )
    pg = postgresql.dialect()
    assert type_sql(blueprint, pg, 0) == "VECTOR(3)"
    assert type_sql(blueprint, pg, 1) == "GEOMETRY(GEOMETRY)"
    assert type_sql(blueprint, pg, 2) == "GEOMETRY(POINT,4326)"
    assert type_sql(blueprint, pg, 3) == "GEOGRAPHY(GEOMETRY,4326)"

    my = mysql.dialect()
    assert type_sql(blueprint, my, 0) == "VECTOR(3)"
    assert type_sql(blueprint, my, 1) == "GEOMETRY"
    assert type_sql(blueprint, my, 3) == "GEOMETRY SRID 4326"

    lite = sqlite.dialect()
    assert type_sql(blueprint, lite, 1) == "BLOB"
    assert type_sql(blueprint, lite, 3) == "BLOB"
    with pytest.raises(UnsupportedByDialectError, match="vector columns"):
        type_sql(blueprint, lite, 0)


# --- modifiers ---------------------------------------------------------------


async def test_a_default_is_the_engines_not_the_applications(memory_db) -> None:
    """A row written by anything at all gets the default, as Laravel's does."""
    await Schema.create(
        "posts",
        lambda table: (
            table.id(),
            table.string("title"),
            table.string("status").default("draft"),
            table.integer("votes").default(0),
            table.boolean("live").default(False),
        ),
    )
    await DB.insert("INSERT INTO posts (title) VALUES (:title)", {"title": "Raw"})
    row = await DB.table("posts").first()
    assert row["status"] == "draft"
    assert row["votes"] == 0
    assert not row["live"]


def test_how_a_default_is_written_for_each_kind_of_value() -> None:
    blueprint = _with(
        lambda t: (
            t.string("a").default("O'Hara"),
            t.integer("b").default(7),
            t.boolean("c").default(True),
            t.json("d").default({"k": 1}),
            t.string("e").default(None),
            t.timestamp("f").use_current(),
        )
    )
    pg = postgresql.dialect()
    assert "DEFAULT 'O''Hara'" in column_sql(blueprint, pg, 0)
    assert "DEFAULT 7" in column_sql(blueprint, pg, 1)
    assert "DEFAULT true" in column_sql(blueprint, pg, 2)
    assert "DEFAULT '{\"k\": 1}'" in column_sql(blueprint, pg, 3)
    assert "DEFAULT" not in column_sql(blueprint, pg, 4)
    assert "DEFAULT CURRENT_TIMESTAMP" in column_sql(blueprint, pg, 5)
    assert "DEFAULT 1" in column_sql(blueprint, sqlite.dialect(), 2)


def test_a_callable_default_stays_on_this_side_of_the_wire() -> None:
    """Python cannot be a server default, so it stays a client-side one."""
    blueprint = _with(lambda t: t.string("code").default(lambda: "generated"))
    column = blueprint.columns[0].to_sqlalchemy(sqlite.dialect())
    assert column.server_default is None
    assert column.default is not None


def test_use_current_on_update_is_mysqls_touch() -> None:
    blueprint = _with(lambda t: t.timestamp("updated_at").use_current().use_current_on_update())
    assert "DEFAULT CURRENT_TIMESTAMP" in column_sql(blueprint, mysql.dialect())
    column = blueprint.columns[0].to_sqlalchemy(mysql.dialect())
    assert column.server_onupdate is not None
    assert blueprint.columns[0].to_sqlalchemy(sqlite.dialect()).server_onupdate is None


def test_generated_columns_are_computed_or_identity() -> None:
    virtual = _with(lambda t: t.string("full").virtual_as("first || ' ' || last"))
    stored = _with(lambda t: t.string("full").stored_as("first || ' ' || last"))
    identity = _with(lambda t: t.big_integer("seq").generated_as().always())

    assert "GENERATED ALWAYS AS" in column_sql(virtual, postgresql.dialect())
    assert "STORED" in column_sql(stored, postgresql.dialect())
    assert "GENERATED ALWAYS AS IDENTITY" in column_sql(identity, postgresql.dialect())

    sometimes = _with(lambda t: t.big_integer("seq").generated_as().always(False).start_from(100))
    assert "BY DEFAULT AS IDENTITY" in column_sql(sometimes, postgresql.dialect())
    assert "START WITH 100" in column_sql(sometimes, postgresql.dialect())


def test_comment_charset_collation_and_invisible_are_mysqls(memory_db) -> None:
    blueprint = Blueprint("posts")
    blueprint.string("title").comment("What it's called").charset("utf8mb4").collation(
        "utf8mb4_unicode_ci"
    ).invisible()
    statement = compile_table_statements(blueprint, mysql.dialect())[0]
    assert "CHARACTER SET utf8mb4" in statement
    assert "COLLATE utf8mb4_unicode_ci" in statement
    assert "INVISIBLE" in statement
    assert "COMMENT 'What it''s called'" in statement

    # Nothing of the sort survives to SQLite, which has no place to put it.
    plain = compile_table_statements(blueprint, sqlite.dialect())[0]
    assert "INVISIBLE" not in plain and "COLLATE utf8mb4_unicode_ci" not in plain


def test_first_after_and_before_place_a_column(memory_db) -> None:
    my = mysql.dialect()
    assert " FIRST" in compile_table_statements(_with(lambda t: t.string("a").first()), my)[0]
    assert (
        " AFTER `b`" in compile_table_statements(_with(lambda t: t.string("a").after("b")), my)[0]
    )
    assert (
        " BEFORE `b`" in compile_table_statements(_with(lambda t: t.string("a").before("b")), my)[0]
    )
    # Each one is the last word on placement.
    column = _with(lambda t: t.string("a").after("b").before("c").first()).columns[0]
    assert "after" not in column.options and "before" not in column.options


async def test_a_column_asking_for_an_index_gets_one_on_both_paths(memory_db) -> None:
    """`.index()` inside create() used to be silently dropped."""
    await Schema.create(
        "posts",
        lambda table: (table.id(), table.string("slug").index(), table.string("title")),
    )
    assert await Schema.has_index("posts", ["slug"])

    await Schema.table("posts", lambda table: table.string("author").index())
    assert await Schema.has_index("posts", ["author"])


async def test_the_polymorphic_pairs_and_the_index_they_carry(memory_db) -> None:
    await Schema.create(
        "comments",
        lambda table: (
            table.id(),
            table.morphs("commentable"),
            table.uuid_morphs("owner"),
            table.ulid_morphs("actor"),
            table.nullable_morphs("target", "ix_target_lookup"),
        ),
    )
    names = {column["name"] for column in await Schema.columns("comments")}
    assert {"commentable_id", "commentable_type", "owner_id", "actor_type"} <= names
    assert await Schema.has_index("comments", ["commentable_type", "commentable_id"])
    assert await Schema.has_index("comments", "ix_target_lookup")

    types = {column["name"]: column["type"] for column in await Schema.columns("comments")}
    assert types["commentable_id"] == "BIGINT"
    assert types["owner_id"] == "VARCHAR(36)"
    assert types["actor_id"] == "VARCHAR(26)"


def test_a_foreign_key_named_after_the_model_it_points_at() -> None:
    class Post:
        table = "posts"
        primary_key = "id"
        key_type = "int"

    class Company:
        table = "companies"
        primary_key = "uuid"
        key_type = "uuid"

    blueprint = Blueprint("t")
    blueprint.foreign_id_for(Post)
    blueprint.foreign_id_for(Company)
    blueprint.foreign_id_for(Post, "editor_id")
    blueprint.foreign_uuid("owner_uuid")
    blueprint.foreign_ulid("actor_ulid")

    assert [column.name for column in blueprint.columns] == [
        "post_id",
        "company_uuid",
        "editor_id",
        "owner_uuid",
        "actor_ulid",
    ]
    assert all(column.options["nullable"] for column in blueprint.columns)
    assert type_sql(blueprint, mysql.dialect(), 1) == "VARCHAR(36)"


def test_the_singular_a_foreign_key_is_named_from() -> None:
    from almasix.orm.blueprint import _singular_key

    assert _singular_key("companies") == "company"
    assert _singular_key("addresses") == "address"
    assert _singular_key("boxes") == "box"
    assert _singular_key("posts") == "post"
    assert _singular_key("staff") == "staff"


def test_table_options_travel_with_a_created_table() -> None:
    blueprint = Blueprint("posts")
    blueprint.id()
    blueprint.engine("InnoDB")
    blueprint.charset("utf8mb4")
    blueprint.collation("utf8mb4_unicode_ci")
    blueprint.comment("Everything published")
    table = blueprint.to_table(sa.MetaData(), mysql.dialect())
    assert table.kwargs["mysql_engine"] == "InnoDB"
    assert table.kwargs["mysql_charset"] == "utf8mb4"
    assert table.kwargs["mysql_collate"] == "utf8mb4_unicode_ci"
    assert table.comment == "Everything published"


def test_auto_increment_and_a_starting_value() -> None:
    blueprint = _with(lambda t: t.integer("seq").auto_increment().start_from(500))
    column = blueprint.columns[0]
    assert column.options["autoincrement"] is True
    assert column.options["start_from"] == 500


def test_a_default_written_as_sql_is_left_as_sql() -> None:
    blueprint = _with(lambda t: t.timestamp("seen_at").default(sa.text("CURRENT_TIMESTAMP")))
    assert "DEFAULT CURRENT_TIMESTAMP" in column_sql(blueprint, postgresql.dialect())


def test_constrained_needs_a_blueprint_behind_it() -> None:
    from almasix.orm.blueprint import Column, SchemaError

    with pytest.raises(SchemaError, match="Blueprint-owned"):
        Column("user_id", sa.Integer).constrained()


async def test_a_unique_column_is_unique_on_both_paths(memory_db) -> None:
    await Schema.create("tags", lambda table: (table.id(), table.string("name").unique()))
    await DB.table("tags").insert({"name": "php"})
    with pytest.raises(Exception, match="UNIQUE"):
        await DB.table("tags").insert({"name": "php"})


async def test_two_keys_to_one_table_and_a_key_to_this_one(memory_db) -> None:
    """A stub is made once per referenced table, and never for this table."""
    await Schema.create("people", lambda table: (table.id(), table.string("name")))
    await Schema.create(
        "threads",
        lambda table: (
            table.id(),
            table.foreign_id("author_id").constrained("people"),
            table.foreign_id("editor_id").constrained("people"),
            table.foreign_id("parent_id").nullable().constrained("threads"),
        ),
    )

    keys = await Schema.get_foreign_keys("threads")
    assert sorted(key["foreign_table"] for key in keys) == ["people", "people", "threads"]
