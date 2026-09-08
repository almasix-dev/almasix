"""M5 — dialect-native upsert SQL and driver URL extras."""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import mysql, postgresql, sqlite

from almasix.orm import Model, Schema
from almasix.orm.builder import QueryBuilder, _native_upsert

pytest_plugins = ("tests.orm_support",)


class Account(Model):
    table = "accounts"
    timestamps = False
    fillable = ("email", "name")


def test_native_upsert_sql_per_dialect() -> None:
    table = sa.table(
        "accounts",
        sa.column("email"),
        sa.column("name"),
    )
    rows = [{"email": "a@b.c", "name": "Ada"}]
    unique = ["email"]
    update = ["name"]

    sqlite_sql = str(
        _native_upsert(table, rows, unique, update, "sqlite").compile(dialect=sqlite.dialect())
    ).lower()
    assert "on conflict" in sqlite_sql and "do update" in sqlite_sql

    pg_sql = str(
        _native_upsert(table, rows, unique, update, "postgresql").compile(
            dialect=postgresql.dialect()
        )
    ).lower()
    assert "on conflict" in pg_sql and "do update" in pg_sql

    mysql_sql = str(
        _native_upsert(table, rows, unique, update, "mysql").compile(dialect=mysql.dialect())
    ).lower()
    assert "on duplicate key update" in mysql_sql

    assert _native_upsert(table, rows, unique, update, "oracle") is None


@pytest.mark.asyncio
async def test_sqlite_native_upsert_round_trip(memory_db) -> None:
    await Schema.create(
        "accounts",
        lambda t: (
            t.id(),
            t.string("email"),
            t.string("name"),
            t.unique_index(["email"]),
        ),
    )
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

    with pytest.raises(ValueError):
        await Account.query().upsert({"email": "x"}, unique_by=[])

    await Account.query().upsert(
        {"email": "a@b.c", "name": "Ignored"},
        unique_by=["email"],
        update=[],
    )
    assert (await Account.query().where("email", "a@b.c").value("name")) == "Updated"


def test_right_join_compiles_on_modern_sqlite() -> None:
    sql = (
        QueryBuilder(table="users")
        .right_join("posts", "users.id", "posts.user_id")
        .to_sql()
        .lower()
    )
    assert "right" in sql or "outer" in sql
