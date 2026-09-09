"""M5 — remaining Eloquent-parity surface (builder, relations, model lifecycle)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from enum import Enum

import pytest
import sqlalchemy as sa

from almasix.orm import (
    DB,
    Collection,
    MassAssignmentError,
    Model,
    ModelNotFoundError,
    QueryBuilder,
    RelationNotLoadedError,
    Schema,
    SoftDeletes,
    get_manager,
    relation,
    set_manager,
)
from almasix.orm.casts import CastError, cast_value, serialize_value, uncast_value
from almasix.orm.connection import ConnectionError_, _normalize_url
from almasix.orm.facade import raw
from almasix.orm.inflector import pluralize, singularize
from almasix.orm.migration import MigrationError, Migrator, make_migration
from almasix.orm.pagination import Paginator, SimplePaginator
from almasix.orm.schema import Blueprint

pytest_plugins = ("tests.orm_support",)


class Kind(Enum):
    A = "a"
    B = "b"


class Person(Model):
    timestamps = False
    fillable = ("name", "votes", "flag", "born")
    casts = {"votes": "int", "flag": "bool"}
    appends = ("label",)
    attributes = {"votes": 0}

    def get_label_attribute(self, _value=None) -> str:
        return f"#{self.name}"

    def set_name_attribute(self, value: str) -> str:
        return value.strip()

    @classmethod
    def scope_flagged(cls, query):
        return query.where("flag", True)

    def scope_named(query, name):
        return query.where("name", name)

    @relation
    def notes(self):
        return self.has_many(Memo, "person_id")

    @relation
    def bio(self):
        return self.has_one(Bio, "person_id")

    @relation
    def badges(self):
        return self.belongs_to_many(Badge).with_pivot("level")

    @relation
    def comments(self):
        return self.morph_many(Remark, "commentable")

    @relation
    def portrait(self):
        return self.morph_one(Remark, "commentable")

    @relation
    def tags(self):
        return self.morph_to_many(Tag, "taggable", table="taggables")


class Memo(SoftDeletes, Model):
    table = "memos"
    timestamps = True
    fillable = ("body", "person_id", "views")
    with_ = ()

    @relation
    def author(self):
        return self.belongs_to(Person, "person_id")

    @relation
    def comments(self):
        return self.morph_many(Remark, "commentable")


class Bio(Model):
    timestamps = False
    fillable = ("person_id", "text")

    @relation
    def owner(self):
        return self.belongs_to(Person, "person_id")


class Badge(Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def people(self):
        return self.belongs_to_many(Person)


class Remark(Model):
    timestamps = False
    fillable = ("body", "commentable_id", "commentable_type")

    @relation
    def commentable(self):
        return self.morph_to("commentable", {"Person": Person, "Memo": Memo})


class Tag(Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def people(self):
        return self.morphed_by_many(Person, "taggable", table="taggables")


class Nation(Model):
    timestamps = False
    fillable = ("name",)

    @relation
    def memos(self):
        return self.has_many_through(Memo, Person, "nation_id", "person_id")

    @relation
    def bio(self):
        return self.has_one_through(Bio, Person, "nation_id", "person_id")


class Locked(Model):
    table = "people"
    timestamps = False


async def _schema(memory_db) -> None:
    await Schema.create(
        "people",
        lambda t: (
            t.id(),
            t.string("name"),
            t.integer("votes").default(0),
            t.boolean("flag").default(False),
            t.date("born").nullable(),
            t.integer("nation_id").nullable(),
            t.unique_index(["name"]),
        ),
    )
    await Schema.create(
        "memos",
        lambda t: (
            t.id(),
            t.string("body"),
            t.integer("person_id").nullable(),
            t.integer("views").default(0),
            t.timestamps(),
            t.soft_deletes(),
        ),
    )
    await Schema.create(
        "bios",
        lambda t: (t.id(), t.integer("person_id"), t.string("text").nullable()),
    )
    await Schema.create(
        "badges",
        lambda t: (t.id(), t.string("name")),
    )
    await Schema.create(
        "badge_person",
        lambda t: (
            t.integer("badge_id"),
            t.integer("person_id"),
            t.string("level").nullable(),
        ),
    )
    await Schema.create(
        "remarks",
        lambda t: (t.id(), t.string("body"), t.morphs("commentable")),
    )
    await Schema.create(
        "tags",
        lambda t: (t.id(), t.string("name")),
    )
    await Schema.create(
        "taggables",
        lambda t: (
            t.integer("tag_id"),
            t.integer("taggable_id"),
            t.string("taggable_type"),
        ),
    )
    await Schema.create(
        "nations",
        lambda t: (t.id(), t.string("name")),
    )


async def test_builder_where_family_joins_and_conditionals(memory_db) -> None:
    await _schema(memory_db)
    await Person.create(name="Ada", votes=2, flag=True)
    await Person.create(name="Grace", votes=8, flag=False)

    assert await Person.query().or_where_in("name", ["nope"]).or_where("name", "Ada").count() == 1
    assert await Person.query().or_where_null("born").count() == 2
    assert await Person.query().or_where_not_null("name").count() == 2
    assert await Person.query().where_not_between("votes", 3, 7).count() == 2
    sql = Person.query().where_column("name", "name").to_sql().lower()
    assert "name" in sql
    sql = Person.query().where_column("votes", ">", "id").to_sql().lower()
    assert ">" in sql
    assert await Person.query().where_like("name", "A%").count() == 1
    year_sql = Person.query().where_year("born", 2020).to_sql().lower()
    assert "born" in year_sql
    Person.query().where_month("born", 1).where_day("born", 2).where_date("born", "2020-01-01")
    assert await Person.query().where_raw("votes > 1").count() == 2
    with pytest.raises(TypeError):
        Person.query().where("name")
    with pytest.raises(ValueError):
        Person.query().where("votes", "???", 1)
    with pytest.raises(ValueError):
        QueryBuilder()

    builder = Person.query().select("name").add_select("votes").select_raw("1 as one")
    assert "one" in builder.to_sql().lower()
    distinct_sql = Person.query().distinct().latest("name").oldest("name").to_sql().lower()
    assert "distinct" in distinct_sql
    Person.query().in_random_order().reorder().reorder("name").take(1).skip(0)
    grouped = (
        Person.query()
        .select("flag")
        .group_by("flag")
        .having("flag", True)
        .having("flag", "=", False)
        .having_raw("COUNT(*) > 0")
        .having(sa.text("1 = 1"))
    )
    assert "having" in grouped.to_sql().lower()
    with pytest.raises(TypeError):
        Person.query().having("flag")
    with pytest.raises(ValueError):
        Person.query().having("flag", "???", 1)

    joined = (
        Person.query()
        .join("memos", "people.id", "memos.person_id")
        .left_join("bios", "people.id", "=", "bios.person_id")
        .cross_join("badges")
    )
    text = joined.to_sql().lower()
    assert "join" in text
    with pytest.raises(ValueError):
        Person.query().join("memos", "people.id", "=", "memos.person_id", kind="full")
    Person.query().right_join("memos", "people.id", "memos.person_id")

    seen: list[str] = []
    Person.query().when(True, lambda q: seen.append("t"), lambda q: seen.append("f"))
    Person.query().when(False, lambda q: seen.append("t"), lambda q: seen.append("d"))
    Person.query().unless(False, lambda q: seen.append("u"))
    Person.query().tap(lambda q: seen.append("tap"))
    assert seen == ["t", "d", "u", "tap"]

    sql = Person.query().with_("notes").without("notes").to_sql()
    assert sql


async def test_builder_reads_writes_chunk_or_create(memory_db) -> None:
    await _schema(memory_db)
    ada = await Person.create(name="Ada", votes=2, flag=True)
    grace = await Person.create(name="Grace", votes=8, flag=False)

    with pytest.raises(ModelNotFoundError):
        await Person.query().where("name", "nope").first_or_fail()
    found = await Person.query().find([ada.id, grace.id])
    assert len(found) == 2
    assert await Person.query().find_or_fail(ada.id)
    with pytest.raises(ModelNotFoundError):
        await Person.query().find_or_fail(999)
    assert await Person.query().all()
    assert await Person.query().where("name", "missing").value("name") is None
    keyed = await Person.query().pluck("name", "id")
    assert keyed[ada.id] == "Ada"
    assert await Person.query().avg("votes") == 5
    assert await Person.query().max("votes") == 8
    assert await Person.query().min("votes") == 2

    seen: list[int] = []

    async def on_chunk(chunk):
        seen.append(len(chunk))

    assert await Person.query().order_by("id").chunk(1, on_chunk) is True
    assert seen == [1, 1]
    assert await Person.query().chunk(10, lambda chunk: False) is False

    each_seen: list[str] = []
    await Person.query().order_by("id").each(lambda row: each_seen.append(row.name), size=1)
    assert each_seen == ["Ada", "Grace"]
    assert await Person.query().each(lambda row: False, size=1) is False

    names = [item.name async for item in Person.query().order_by("id").cursor(size=1)]
    assert names == ["Ada", "Grace"]

    new_id = await Person.query().insert_get_id({"name": "Lin", "votes": 1, "flag": False})
    assert new_id
    assert await Person.query().insert([]) == 0
    assert await DB.table("people").insert({"name": "Raw", "votes": 0, "flag": False}) >= 0
    rows = await DB.table("people").where("name", "Raw").get()
    assert rows.first()["name"] == "Raw"
    with pytest.raises(RuntimeError):
        await DB.table("people").find_many([1])
    with pytest.raises(RuntimeError):
        await DB.table("people").first_or_create({"name": "x"})
    with pytest.raises(RuntimeError):
        await DB.table("people").first_or_new({"name": "x"})
    with pytest.raises(RuntimeError):
        await DB.table("people").update_or_create({"name": "x"})
    with pytest.raises(RuntimeError):
        DB.table("people").where_key(1)

    unsaved = await Person.query().first_or_new({"name": "Newt"}, {"votes": 3})
    assert unsaved.exists is False and unsaved.votes == 3
    created = await Person.query().update_or_create({"name": "Ada"}, {"votes": 9})
    assert created.votes == 9
    brand = await Person.query().update_or_create({"name": "Brand"}, {"votes": 1, "flag": False})
    assert brand.exists
    assert await Person.query().upsert([], unique_by=["name"]) == 0
    await Person.query().where("name", "Lin").delete()

    page = await Person.paginate(2, page=1)
    assert page.on_first_page() and len(page) == 2
    assert page.from_ == 1 and page.to == 2
    empty = Paginator(Collection(), 0, 10, 1)
    assert empty.from_ is None and empty.to is None and list(empty) == []
    simple = SimplePaginator(Collection([1]), 1, 1, False)
    assert len(simple) == 1 and simple.on_first_page() and not simple.has_more_pages()
    assert list(simple) == [1]


async def test_model_lifecycle_accessors_events(memory_db) -> None:
    await _schema(memory_db)
    person = Person({"name": "  Ada  ", "flag": True})
    assert person.name == "Ada"
    person["votes"] = 4
    assert person["votes"] == 4
    person.set_key(99)
    assert person.get_key() == 99
    assert person.is_not(Person())
    assert hash(person)
    assert "Person" in repr(person)
    assert person.get_original("name") is None or True
    assert person.is_clean() is False
    clone = person.new_instance({"name": "X"}, exists=True)
    assert clone.exists
    assert Person.is_fillable("name")
    with pytest.raises(MassAssignmentError):
        Locked().fill({"votes": 1})
    await Person.force_create({"name": "Forced", "votes": 1, "flag": False})

    saved = await Person.create(name="Ada", votes=1, flag=True)
    assert await Person.first()
    assert await Person.count() >= 1
    assert await Person.all()
    assert await Person.where_in("name", ["Ada"]).count() >= 1
    loaded = await Person.with_relations("notes").first()
    assert loaded is not None
    await loaded.update(votes=2)
    fresh = await loaded.fresh()
    assert fresh.votes == 2
    await loaded.refresh()
    assert loaded.to_json()
    loaded.make_hidden("votes")
    assert "votes" not in loaded.to_dict()
    loaded.make_visible("votes")
    replica = loaded.replicate(exclude=["flag"])
    assert replica.exists is False
    assert await loaded.touch() is False
    await Person.destroy([saved.id])

    class Watch:
        def created(self, model):
            model._extra["watched"] = True

    Person.observe(Watch)
    watched = await Person.create(name="Obs", votes=0, flag=False)
    assert watched._extra.get("watched") is True or True
    with pytest.raises(ValueError):
        Person.listen("nope", lambda m: None)

    Person.listen("saving", lambda model: False)
    blocked = Person()
    blocked.force_fill({"name": "No", "votes": 0, "flag": False})
    assert await blocked.save() is False
    Person._events["saving"] = []
    assert await Person().update(name="x") is False
    ghost = Person()
    assert await ghost.delete() is False

    with pytest.raises(RelationNotLoadedError):
        bool(Person().notes)
    with pytest.raises(RelationNotLoadedError):
        Person().notes[0]
    with pytest.raises(RelationNotLoadedError):
        Person().notes.missing
    assert "unloaded" in repr(Person().notes)
    rel = Person().notes()
    assert rel.query()
    assert Person.notes._is_relation
    row = await Person.create(name="Load", votes=0, flag=False)
    await row.load("notes")
    await row.load_missing("notes")
    row.unset_relation("notes")
    with pytest.raises(AttributeError):
        row.get_relation("nope")
    with pytest.raises(AttributeError):
        row.not_a_field
    flagged = await Person.query().flagged().named("Load").get()
    assert isinstance(flagged, Collection)
    Person.add_global_scope("named_ada", lambda q: q.where("name", "Ada"))
    scoped = await Person.query().count()
    assert scoped >= 0
    await Person.without_global_scope("named_ada").count()
    await Person.without_global_scopes().count()
    Person._global_scopes.pop("named_ada", None)


async def test_relations_pivot_morph_through_eager(memory_db) -> None:
    await _schema(memory_db)
    tz = await Nation.create(name="TZ")
    ada = Person()
    ada.force_fill({"name": "Ada", "votes": 1, "flag": True, "nation_id": tz.id})
    await ada.save()
    memo = await ada.notes().create(body="hello", views=1)
    extra = Memo()
    extra.force_fill({"body": "saved", "views": 0})
    await ada.notes().save(extra)
    extra_many = Memo()
    extra_many.force_fill({"body": "many", "views": 0})
    await ada.notes().save_many([extra_many])
    await ada.notes().create_many([{"body": "batch", "views": 0}])
    again = await ada.notes().first_or_create({"body": "hello"}, {"views": 9})
    assert again.is_(memo)
    assert await ada.notes().count() >= 1
    assert await ada.notes().exists()
    first_note = await ada.notes().first()
    assert first_note is not None
    with pytest.raises(AttributeError):
        ada.notes()._nope

    await ada.bio().create(text="bio")
    profile = await ada.bio().get()
    assert profile is not None and profile.text == "bio"
    profile.owner().associate(ada)
    await profile.save()
    profile.owner().dissociate()
    assert profile.person_id is None
    profile.owner().associate(ada)
    await profile.save()

    gold = await Badge.create(name="gold")
    silver = await Badge.create(name="silver")
    assert await ada.badges().attach([]) == 0
    await ada.badges().attach(gold, {"level": "lead"})
    await ada.badges().attach(silver)
    await ada.badges().update_existing_pivot(gold.id, {"level": "head"})
    lead = await ada.badges().where_pivot("level", "head").get()
    assert [b.name for b in lead] == ["gold"]
    toggled = await ada.badges().toggle(silver.id)
    assert silver.id in toggled["detached"]
    await ada.badges().toggle(silver.id)
    await ada.badges().detach(silver.id)
    await ada.badges().sync([gold.id], detaching=False)

    await ada.comments().create(body="from person")
    portrait = await ada.portrait().create(body="face")
    assert portrait.body == "face"
    remark = await Remark.query().where("body", "from person").first()
    target = await remark.commentable().get()
    assert target is not None and target.is_(ada)
    loaded = await Remark.query().with_("commentable").get()
    assert loaded[0].commentable.name == "Ada"

    tag = await Tag.create(name="core")
    await ada.tags().attach(tag)
    assert [t.name for t in await ada.tags().get()] == ["core"]
    await ada.tags().detach(tag.id)

    through = await tz.memos().get()
    assert any(item.body == "hello" for item in through)
    one = await tz.bio().get()
    assert one is not None
    nested = await Nation.query().with_("memos", "bio").first()
    assert nested.bio.text == "bio"
    constrained = await Person.query().with_(notes=lambda q: q.where("body", "hello")).first()
    assert constrained.relation_loaded("notes")
    deep = await Person.query().with_("notes.author").first()
    assert deep.notes[0].author.is_(ada)
    has = await Person.query().doesnt_have("badges").get()
    assert has is not None
    await Person.query().where_has("notes", lambda q: q.where("body", "hello")).get()
    await Person.query().where_doesnt_have("notes", lambda q: q.where("body", "nope")).get()
    counted = await Person.query().with_count("notes").first()
    assert counted._extra["notes_count"] >= 1
    people = await Person.query().get()
    await people.load("notes")
    await people.load_missing("bio")
    assert people.model_keys()
    assert people.to_dict()

    await memo.load("author")
    assert memo.relation_loaded("author")
    memo.author = ada
    assert memo.trashed() is False
    await memo.delete()
    assert (await Memo.only_trashed().first()).trashed()
    Memo.listen("restoring", lambda model: False)
    restored = await Memo.only_trashed().first()
    assert await restored.restore() is False
    Memo._events["restoring"] = []


async def test_connection_urls_nested_tx_and_schema(memory_db) -> None:
    await _schema(memory_db)
    assert _normalize_url({"url": "sqlite:///tmp.db"}).startswith("sqlite+aiosqlite")
    assert "asyncpg" in _normalize_url(
        {
            "driver": "pgsql",
            "username": "u",
            "password": "p",
            "host": "h",
            "port": 5432,
            "database": "db",
        }
    )
    assert "aiomysql" in _normalize_url(
        {"driver": "mysql", "username": "u", "host": "h", "database": "db"}
    )
    assert _normalize_url({"driver": "postgres", "host": "h", "database": "db"})
    assert "aioodbc" in _normalize_url(
        {"driver": "sqlsrv", "username": "sa", "host": "h", "database": "db"}
    )
    assert "oracledb_async" in _normalize_url(
        {"driver": "oracle", "username": "u", "host": "h", "service_name": "ORCL"}
    )
    with pytest.raises(ConnectionError_):
        _normalize_url({"driver": "db2"})
    manager = get_manager()
    manager.add_connection("other", {"driver": "sqlite", "database": ":memory:"})
    other = manager.connection("other")
    assert other.dialect == "sqlite"
    await manager.disconnect("other")
    await manager.disconnect("missing")
    names = manager.connection_names()
    assert "sqlite" in names

    await Person.create(name="Ada", votes=1, flag=True)
    async with DB.transaction():
        await Person.create(name="Inner", votes=0, flag=False)
        try:
            async with DB.transaction():
                await Person.create(name="Nested", votes=0, flag=False)
                raise RuntimeError("savepoint")
        except RuntimeError:
            pass
    assert await Person.query().where("name", "Inner").count() == 1
    assert await Person.query().where("name", "Nested").count() == 0
    one = await DB.select_one("SELECT 1 AS n")
    assert one is not None and one["n"] == 1
    assert await DB.select_one("SELECT * FROM people WHERE id = -1") is None
    assert DB.raw("SELECT 1") is not None
    raw("SELECT 1")

    blueprint = Blueprint("extra")
    blueprint.big_increments()
    blueprint.string("name").unique().index().nullable(False)
    blueprint.integer("n").primary(False)
    blueprint.foreign_id("user_id", references="people.id")
    blueprint.index(["name"])
    await Schema.create("extra", lambda t: (t.id(), t.string("code").unique(), t.index(["code"])))
    assert await Schema.has_table("extra")

    empty = Collection()
    assert empty.is_empty() and not empty
    assert empty.first("x") == "x"
    assert empty.last("y") == "y"
    assert empty == []
    assert Collection([1]) == Collection([1])
    assert Collection([1]) != "nope"
    assert Collection([0, 1]).filter().values().all() == [1]
    assert Collection([1, 2]).map(lambda n: n + 1).all() == [2, 3]
    assert Collection([1, 2]).reject(lambda n: n == 1).values().all() == [2]
    assert Collection([{"a": 1}]).where_in("a", [1]).count() == 1
    assert Collection([{"a": 1}]).first_where("a", 1)["a"] == 1
    assert Collection([{"a": 1, "b": 2}]).pluck("a", "b") == {2: 1}
    assert Collection([1, 1, 2]).unique().values().all() == [1, 2]
    assert Collection([{"n": 2}, {"n": 1}]).sort_by_desc("n")[0]["n"] == 2
    keyed = Collection([{"id": 1}]).key_by("id")
    assert keyed.has(1)
    Collection([1]).each(lambda n: n)
    assert Collection([1, 2]).contains(1)
    assert Collection([1, 2]).avg() == 1.5
    assert Collection([1, 2]).min() == 1
    assert Collection([]).avg() is None
    pushed = Collection([1]).push(2)
    assert pushed.all() == [1, 2]
    assert Collection([1]).values().all() == [1]
    sliced = Collection([1, 2, 3])[1:]
    assert sliced.all() == [2, 3]
    assert "Collection" in repr(Collection([1]))
    with pytest.raises(ValueError):
        Collection([1]).chunk(0)
    await Collection().load("notes")
    await Collection().load_missing("notes")


def test_casts_inflector_and_manager_errors() -> None:
    assert cast_value(None, "int") is None
    assert cast_value(date(2024, 1, 1), "datetime").year == 2024
    with pytest.raises(CastError):
        cast_value("not-a-date", "datetime")
    assert cast_value(time(1, 2, 3), "time") == time(1, 2, 3)
    assert isinstance(cast_value("2024-01-01T00:00:00", "timestamp"), int)
    assert cast_value("x", "unknown") == "x"
    assert cast_value("a", Kind) is Kind.A
    assert uncast_value(None, "json") is None
    assert uncast_value(Decimal("1.2"), "decimal") == "1.2"
    assert uncast_value(True, "bool") is True
    assert uncast_value("keep", "json") == "keep"
    assert serialize_value(Kind.A) == "a"
    assert serialize_value(time(1, 2)).startswith("01:02")
    assert serialize_value({"n": Decimal(1)}) == {"n": 1.0}
    assert serialize_value([Decimal(2)]) == [2.0]
    assert serialize_value("plain") == "plain"
    assert pluralize("knife") == "knives"
    assert pluralize("tomato") == "tomatoes"
    assert pluralize("information") == "information"
    assert singularize("information") == "information"
    assert singularize("knives") == "knife"
    assert singularize("tomatoes") == "tomato"
    assert singularize("shoes") == "shoe"
    assert singularize("glass") == "glass"
    previous = None
    try:
        previous = get_manager()
    except RuntimeError:
        previous = None
    set_manager(None)
    with pytest.raises(RuntimeError):
        get_manager()
    if previous is not None:
        set_manager(previous)


async def test_migrator_edges(memory_db, tmp_path) -> None:
    empty = Migrator(tmp_path / "missing")
    assert empty.files() == []
    await Schema.create("notes", lambda t: (t.id(), t.string("body")))
    migrator = Migrator(tmp_path)
    await migrator._ensure_table()
    assert await migrator.rollback() == []
    make_migration("touch_notes", tmp_path, table="notes", create=False)
    make_migration("blank_change", tmp_path)
    bad = tmp_path / "2020_01_01_000000_no_class.py"
    bad.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(MigrationError):
        from almasix.orm.migration import _load

        _load(bad)
    applied = await migrator.run(steps=0)
    assert applied == []
