"""ORM remaining coverage → 100%."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa

from almasix.orm.builder import QueryBuilder, _native_upsert
from almasix.orm.collection import Collection
from almasix.orm.connection import Connection
from almasix.orm.eager import _children, eager_load
from almasix.orm.migration import MigrationError, _load
from almasix.orm.model import Model, RelationNotLoadedError
from almasix.orm.schema import Column
from almasix.orm.seeder import SeederError, _load_module


@pytest.mark.asyncio
async def test_builder_scope_missing_and_insert_get_id_fallback() -> None:
    class Post(Model):
        table = "posts"

        @classmethod
        def scope_published(cls, query):
            return query.where("published", True)

    builder = QueryBuilder(model=Post, table="posts")
    assert isinstance(builder.published(), QueryBuilder)
    with pytest.raises(AttributeError):
        _ = builder.nope()

    with patch.object(QueryBuilder, "first", AsyncMock(return_value=None)):
        with pytest.raises(Exception):
            await QueryBuilder(model=Post, table="posts").first_or_fail()

    class FakeResult:
        lastrowid = 99

        def scalar(self):
            return None

    class FakeConn:
        class engine:
            class dialect:
                insert_returning = False

        dialect = "sqlite"

        async def execute(self, statement):
            return FakeResult()

    with patch.object(QueryBuilder, "get_connection", return_value=FakeConn()):
        assert await builder.insert_get_id({"title": "x"}) == 99

    class FakeResult2:
        lastrowid = None

        def scalar(self):
            return None

    class FakeConn2(FakeConn):
        async def execute(self, statement):
            return FakeResult2()

    with patch.object(QueryBuilder, "get_connection", return_value=FakeConn2()):
        assert await builder.insert_get_id({"id": 7, "title": "y"}) == 7

    class FakeConn3:
        class engine:
            class dialect:
                insert_returning = True

        dialect = "postgresql"

        async def execute(self, statement):
            return FakeResult2()

    with patch.object(QueryBuilder, "get_connection", return_value=FakeConn3()):
        assert await builder.insert_get_id({"id": 3, "title": "z"}) == 3


@pytest.mark.asyncio
async def test_builder_upsert_probe_and_mysql_empty_update() -> None:
    class Post(Model):
        table = "posts"

    builder = QueryBuilder(model=Post, table="posts")

    class FakeConn:
        dialect = "oracle"

        async def execute(self, statement):
            return SimpleNamespace(rowcount=1)

    with patch.object(QueryBuilder, "get_connection", return_value=FakeConn()):
        with patch.object(QueryBuilder, "_upsert_probe", AsyncMock(return_value=2)) as probe:
            assert await builder.upsert({"email": "a", "name": "n"}, unique_by=["email"]) == 2
            probe.assert_awaited()

    table = sa.table("t", sa.column("id"), sa.column("name"))
    stmt = _native_upsert(table, [{"id": 1}], ["id"], [], "mysql")
    assert stmt is not None


def test_model_accessors_relations_load_missing() -> None:
    from almasix.orm import relation

    class Post(Model):
        table = "posts"

    class User(Model):
        table = "users"
        lazy_relations = False

        def get_label_attribute(self, value=None):
            return f"L:{value}"

        @relation
        def posts(self):
            return self.has_many(Post)

    u = User()
    u._attributes["label"] = "x"
    assert u.get_attribute("label") == "L:x"

    class User2(Model):
        table = "users"

        def get_virtual_attribute(self):
            return "virt"

    assert User2().get_attribute("virtual") == "virt"

    u3 = User()
    u3._relations["posts"] = ["p"]
    assert u3.get_attribute("posts") == ["p"]

    with pytest.raises(RelationNotLoadedError):
        bool(User().posts)

    class UserLazy(Model):
        table = "users"
        lazy_relations = True

        @relation
        def posts(self):
            return self.has_many(Post)

    with pytest.raises(RelationNotLoadedError, match="Await"):
        bool(UserLazy().posts)


@pytest.mark.asyncio
async def test_load_missing_and_eager_children() -> None:
    class User(Model):
        table = "users"

    u = User()
    u.set_relation("posts", Collection([User()]))
    await u.load_missing("posts")  # already loaded → pending empty

    parent = User()
    parent.set_relation("kids", None)
    assert _children([parent], "kids") == []
    parent.set_relation("kids", Collection([User(), User()]))
    assert len(_children([parent], "kids")) == 2
    parent.set_relation("kids", User())
    assert len(_children([parent], "kids")) == 1

    await eager_load([], {"x": None})


def test_schema_column_fk_on_update_delete() -> None:
    col = Column(
        "user_id", sa.Integer, references="users.id", on_delete="CASCADE", on_update="CASCADE"
    )
    sa_col = col.to_sqlalchemy()
    assert sa_col is not None

    col2 = Column("user_id", sa.Integer, references="users.id", on_update="SET NULL")
    assert col2.to_sqlalchemy() is not None


@pytest.mark.asyncio
async def test_connection_sqlite_fk_pragma(tmp_path: Path) -> None:
    db = tmp_path / "fk.sqlite"
    conn = Connection("t", {"driver": "sqlite", "database": str(db)})
    async with conn.engine.connect() as c:
        await c.execute(sa.text("select 1"))
        await c.commit()


def test_migration_and_seeder_load_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "2026_01_01_000000_x.py"
    path.write_text("class X: pass\n", encoding="utf-8")
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: None)
    with pytest.raises(MigrationError):
        _load(path)
    with pytest.raises(SeederError):
        _load_module(tmp_path / "s.py", "mod")
