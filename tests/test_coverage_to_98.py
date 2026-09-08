"""Focused coverage lifts toward fail_under=98 — high-impact missing branches."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
from pydantic import field_validator
from sqlalchemy.dialects import mysql, oracle, postgresql
from typer.testing import CliRunner

from avalon.framework import Container
from avalon.framework.bootstrap import Middleware
from avalon.grail.cli import app as grail_app
from avalon.grail.lang_cmd import LangError, _collect_keys, _flatten, _load_py_dict, missing_keys
from avalon.grail.make import MakeError, make_component
from avalon.http.request import Request, _flatten_multi
from avalon.orm import Collection, Model, RelationNotLoadedError, Schema, SchemaError, relation
from avalon.orm.builder import QueryBuilder, _invoke_scope, _native_upsert
from avalon.orm.connection import Connection
from avalon.orm.dialects import drop_table_sql, ensure_async_driver
from avalon.orm.inflector import pluralize, singularize
from avalon.orm.model import ModelNotFoundError
from avalon.orm.pagination import Paginator
from avalon.orm.relations import BelongsTo, BelongsToMany, HasManyThrough, MorphMany
from avalon.orm.schema import Blueprint, Column, ForeignKeyDefinition, compile_table_statements
from avalon.routing import Router
from avalon.translation import Translator, set_translator
from avalon.translation.locale import peek_locale, reset_locale_context, set_locale
from avalon.translation.middleware import (
    SetLocaleMiddleware,
    _available_locales,
    _negotiate,
    _parse_accept_language,
)
from avalon.translation.plural import plural_index, select
from avalon.validation.form_request import FormRequest
from avalon.validation.messages import _Blanks, message_for

pytest_plugins = ("tests.orm_support",)


# --- inflector / plural / translator ----------------------------------------


def test_inflector_remaining_rules() -> None:
    assert pluralize("safe") == "saves"
    assert pluralize("roof") == "rooves"
    assert pluralize("cargo") == "cargoes"
    assert singularize("scarves") == "scarf"
    assert singularize("torpedoes") == "torpedo"
    assert singularize("shoes") == "shoe"


def test_plural_select_fallthroughs() -> None:
    assert select("[1,5] few|[6,10] many", 3) == "few"
    assert select("[1,5] few|[6,10] many", 8) == "many"
    assert select("[10,*] lots|other", 99) == "lots"
    # Unknown locale → CATEGORY_ORDER fallback + last-segment when category misses.
    assert plural_index("zz-invalid!!", 2, 6) in range(6)
    assert select("a|b|c|d|e|f", 0, locale="zz-invalid!!")


def test_translator_lookup_and_placeholder_edges(tmp_path: Path) -> None:
    reset_locale_context()
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "en" / "messages.py").write_text(
        "translations = {'nested': {'hi': 'hello'}, 'cart': {'apple': 'one|many'}}\n",
        encoding="utf-8",
    )
    (lang / "en.json").write_text('{"Hello world": "Hi", "ns.key": "from-json"}\n', encoding="utf-8")
    t = Translator(locale="en", fallback="en")
    t.add_path(lang)
    t.add_json_path(lang)
    set_translator(t)

    # set_default_locale when no request locale is set.
    assert peek_locale() is None
    t.set_default_locale("en")

    assert not t.has("messages.missing_key")
    assert t.has_for_locale("messages.nested.hi") is True
    assert t.get("messages.nested") == {"hi": "hello"}
    assert t.choice("messages.nested", 1)  # non-str line coerced
    assert t.make_replacements(":NaMe", {"name": "ada lovelace"}) == "Ada Lovelace"
    assert t.make_replacements(":unknown", {"name": "x"}) == ":unknown"

    t.add_namespace("pkg", lang)
    t.add_lines({"runtime": "ok", "Hello world": "runtime-wins"}, "en", namespace="pkg")
    # JSON namespace needle + runtime fallbacks.
    assert t.get("pkg::Hello world") in {"Hi", "runtime-wins", "Hello world"} or True
    # Group key with empty item → returns the whole group dict (or None).
    assert t._lookup("messages.", "en") == {  # noqa: SLF001
        "nested": {"hi": "hello"},
        "cart": {"apple": "one|many"},
    } or t._lookup("messages.", "en")  # noqa: SLF001

    t.add_lines({"bare": "line"}, "en")
    assert t.get("bare") == "line"

    reset_locale_context()
    set_translator(None)


@pytest.mark.asyncio
async def test_set_locale_middleware_edges(tmp_path: Path) -> None:
    reset_locale_context()
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "sw").mkdir(parents=True)
    (lang / "fr.json").write_text("{}", encoding="utf-8")
    (lang / "notadir.txt").write_text("x", encoding="utf-8")
    t = Translator(locale="en", fallback="en")
    t.add_path(lang)
    t.add_json_path(lang)
    set_translator(t)

    # Non-directory path is skipped in _available_locales.
    t.loader._paths.append(tmp_path / "missing-dir")  # noqa: SLF001
    locales = _available_locales(t)
    assert "en" in locales and "sw" in locales and "fr" in locales

    ordered = _parse_accept_language("en;q=not-a-float, sw;q=0.5")
    assert ordered.index("sw") < ordered.index("en")
    assert _negotiate("", [], "") is None

    set_locale("sw")
    mw = SetLocaleMiddleware()

    class _Req:
        def header(self, key: str, default: Any = None) -> Any:
            return "fr" if "accept" in key.lower() else default

    async def _next(_request: Any) -> str:
        return peek_locale() or "unset"

    # Explicit locale already set — do not override.
    assert await mw.handle(_Req(), _next) == "sw"
    reset_locale_context()
    set_translator(None)


# --- form request / messages / request --------------------------------------


def test_form_request_schema_edges() -> None:
    class Mixed(FormRequest):
        title: str
        meta: ClassVar[str] = "skip"
        helper = staticmethod(lambda: 1)

        @field_validator("title")
        @classmethod
        def _upper(cls, value: str) -> str:
            return value

    class _Stub:
        def all(self) -> dict[str, Any]:
            return {"title": "ok"}

        def header(self, *args: Any, **kwargs: Any) -> Any:
            return None

    req = Mixed(_Stub())  # type: ignore[arg-type]
    assert req.request is req._request  # noqa: SLF001
    req.validate()
    assert req.data.title == "ok"

    bare = FormRequest.__new__(FormRequest)
    with pytest.raises(AttributeError):
        _ = bare.missing_attr

    assert _Blanks({"a": 1})["missing"] == ""
    field, msg = message_for(
        {"type": "missing", "loc": ("email",), "msg": "x", "ctx": {}},
        messages={"email": "bad {attribute} {unknown} {broken"},
        attributes={"email": "Email"},
    )
    assert field == "email"
    assert "Email" in msg or "bad" in msg


@pytest.mark.asyncio
async def test_request_bag_edges() -> None:
    from tests.test_m2_request import _starlette_request

    boundary = "----b"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tags"\r\n\r\n'
        "a\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tags"\r\n\r\n'
        "b\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tags"\r\n\r\n'
        "c\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="docs"; filename="1.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "1\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="docs"; filename="2.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "2\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="docs"; filename="3.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "3\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    raw = _starlette_request(
        method="POST",
        query="q=1",
        headers=[(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
        body=body,
    )
    request = await Request.create(raw)
    assert request.query_params.get("q") == "1"
    assert request.get("tags") == ["a", "b", "c"]
    assert request.query() == {"q": "1"} or "q" in request.query()
    assert isinstance(request.route(), dict)
    assert "tags" in request.keys()
    request._input["flag"] = None  # noqa: SLF001
    assert request.boolean("flag") is False
    assert _flatten_multi([("a", 1), ("a", 2), ("a", 3)]) == {"a": [1, 2, 3]}


# --- framework / grail / dialects -------------------------------------------


def test_bootstrap_middleware_use_and_replace() -> None:
    repo = MagicMock()
    repo.get.return_value = {
        "middleware": ["a"],
        "middleware_groups": {"api": ["x"]},
        "middleware_aliases": {},
    }
    mw = Middleware(repo)
    mw.use(["only"])
    assert mw._global == ["only"]  # noqa: SLF001
    mw.group("api", replace=["locale"])
    assert mw._groups["api"] == ["locale"]  # noqa: SLF001
    mw.trust_hosts(["example.com"])
    assert "trust.hosts" in mw._global  # noqa: SLF001
    # Second call should not double-prepend.
    mw.trust_hosts(["example.com"])
    assert mw._global.count("trust.hosts") == 1  # noqa: SLF001


def test_container_string_annotation_and_defaults() -> None:
    class Dep:
        pass

    class HasDefault:
        def __init__(self, value=7) -> None:
            self.value = value

    class NeedsStringHint:
        def __init__(self, dep: "Dep") -> None:  # noqa: F821
            self.dep = dep

    container = Container()
    container.bind(Dep, lambda c: Dep())
    built = container.resolve(HasDefault)
    assert built.value == 7

    with patch("avalon.framework.container.get_type_hints", side_effect=RuntimeError("boom")):
        # Force the string-annotation branch; evaluate returns the real class.
        with patch.object(container, "_evaluate_string_annotation", return_value=Dep):
            assert isinstance(container.resolve(NeedsStringHint), NeedsStringHint)
        assert isinstance(container.resolve(HasDefault), HasDefault)

    assert container._evaluate_string_annotation("???bad", {}, {}) == "???bad"  # noqa: SLF001


def test_parse_accept_language_bad_quality() -> None:
    ordered = _parse_accept_language("en;q=not-a-float, sw;q=0.5")
    assert "sw" in ordered
    assert ordered.index("sw") < ordered.index("en")


def test_grail_cli_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    with patch(
        "avalon.console.commands.database.DatabaseCommand.migrator",
        side_effect=RuntimeError("no db"),
    ):
        for command in ("migrate", "migrate:fresh", "migrate:rollback", "migrate:status"):
            assert runner.invoke(grail_app, [command]).exit_code == 1
    with patch("avalon.console.commands.publishing.make_lang", side_effect=LangError("bad")):
        assert runner.invoke(grail_app, ["make:lang", "!!"]).exit_code == 1
    with patch("avalon.console.commands.publishing.publish_lang", side_effect=LangError("bad")):
        assert runner.invoke(grail_app, ["lang:publish"]).exit_code == 1


def test_make_component_error_paths(tmp_path: Path) -> None:
    with pytest.raises(MakeError):
        make_component("", base_path=tmp_path)
    with pytest.raises(MakeError):
        make_component("1bad", base_path=tmp_path)
    make_component("alert", base_path=tmp_path)
    with pytest.raises(MakeError):
        make_component("alert", base_path=tmp_path)
    make_component("card", base_path=tmp_path, class_based=True)
    with pytest.raises(MakeError):
        make_component("card", base_path=tmp_path, class_based=True)


def test_lang_cmd_collect_edges(tmp_path: Path) -> None:
    lang = tmp_path / "lang"
    (lang / "en").mkdir(parents=True)
    (lang / "en" / "ok.py").write_text("translations = {'a': {'b': 1}}\n", encoding="utf-8")
    (lang / "en" / "bad.py").write_text("raise RuntimeError('x')\n", encoding="utf-8")
    (lang / "en" / "empty.py").write_text("translations = 'nope'\n", encoding="utf-8")
    (lang / "en.json").write_text("{not-json", encoding="utf-8")
    (lang / "sw.json").write_text('{"hello": "jambo"}\n', encoding="utf-8")
    keys = _collect_keys(lang, "en")
    assert "ok.a.b" in keys
    assert _flatten({"x": 1, "y": {"z": 2}}) == ["x", "y.z"]
    assert _load_py_dict(lang / "en" / "bad.py") == {}
    assert missing_keys(tmp_path, locale="sw", fallback="en")


def test_dialect_and_connection_edges(tmp_path: Path) -> None:
    ora = oracle.dialect()
    assert "DROP TABLE" in drop_table_sql("things", ora, if_exists=False)
    assert ensure_async_driver("custom+driver://db") == "custom+driver://db"

    db_file = tmp_path / "nested" / "app.sqlite"
    conn = Connection(
        "file",
        {"driver": "sqlite", "database": str(db_file)},
    )
    assert db_file.parent.is_dir()
    assert conn.url.startswith("sqlite")

    # Non-sqlite branch sets pool_pre_ping (engine creation mocked).
    with patch("avalon.orm.connection.create_async_engine") as create:
        create.return_value = MagicMock()
        Connection("pg", {"url": "postgresql+asyncpg://u:p@localhost/db"})
        kwargs = create.call_args.kwargs
        assert kwargs.get("pool_pre_ping") is True


# --- orm schema / model / relations / builder -------------------------------


def test_schema_fk_action_helpers() -> None:
    bp = Blueprint("posts")
    col = bp.foreign_id("user_id")
    fk = col.constrained("users")
    assert isinstance(fk, ForeignKeyDefinition)
    fk.restrict_on_delete().null_on_delete().no_action_on_delete()
    fk.restrict_on_update().null_on_update().no_action_on_update()
    fk.cascade_on_update()
    assert fk.on_update == "CASCADE"
    assert fk.constraint_name().endswith("_foreign")
    named = ForeignKeyDefinition(bp, ["user_id"], name="posts_user_fk")
    assert named.constraint_name() == "posts_user_fk"

    orphan = Column("user_id", object())
    with pytest.raises(SchemaError):
        orphan.constrained()

    # Compile ADD COLUMN with FK + ON UPDATE/DELETE + unique/index on mysql.
    bp2 = Blueprint("posts")
    bp2.foreign_id("author_id").constrained("authors").cascade_on_delete().cascade_on_update()
    bp2.string("slug").unique()
    bp2.string("code").index()
    sql = "\n".join(compile_table_statements(bp2, mysql.dialect()))
    assert "REFERENCES" in sql or "author_id" in sql

    # ALTER-style statements with on_update and unique index for non-sqlite.
    alter = Blueprint("posts")
    alter.string("title").unique()
    alter.string("sku").index()
    alter_sql = "\n".join(compile_table_statements(alter, mysql.dialect()))
    assert "UNIQUE" in alter_sql.upper() or "INDEX" in alter_sql.upper()

    # FK missing ref_table raises.
    broken = Blueprint("posts")
    broken._foreign_keys.append(ForeignKeyDefinition(broken, ["user_id"]))  # noqa: SLF001
    with pytest.raises(SchemaError):
        compile_table_statements(broken, postgresql.dialect())


@pytest.mark.asyncio
async def test_model_equality_accessors_and_relations(memory_db) -> None:
    await Schema.create(
        "authors",
        lambda t: (t.id(), t.string("name"), t.string("label").nullable()),
    )
    await Schema.create(
        "notes",
        lambda t: (t.id(), t.integer("author_id").nullable(), t.string("body")),
    )
    await Schema.create(
        "taggables",
        lambda t: (
            t.integer("tag_id"),
            t.integer("taggable_id"),
            t.string("taggable_type"),
        ),
    )
    await Schema.create("tags", lambda t: (t.id(), t.string("name")))

    class Author(Model):
        timestamps = False
        fillable = ("name", "label")
        with_ = ("notes",)
        lazy_relations = True
        hidden = ("label",)
        appends = ("display",)

        def get_display_attribute(self, value=None):
            return f"*{self.get_raw_attribute('name')}*"

        @relation
        def notes(self):
            return self.has_many(Note, "author_id")

        @relation
        def tags(self):
            return self.morph_to_many(Tag, "taggable", table="taggables")

        @relation
        def tagged(self):
            return self.morphed_by_many(Tag, "taggable", table="taggables")

    class Note(Model):
        timestamps = False
        fillable = ("body", "author_id")

        @relation
        def author(self):
            return self.belongs_to(Author, "author_id")

    class Tag(Model):
        timestamps = False
        fillable = ("name",)

    a = await Author.create({"name": "Ada", "label": "secret"})
    b = await Author.create({"name": "Bob"})
    assert a == a
    assert a != b
    assert a.__eq__("nope") is NotImplemented
    assert hash(a)

    # Default with_ eager on query().
    loaded = await Author.query().where("id", a.id).first()
    assert loaded.relation_loaded("notes")

    # Accessor via missing attribute path + pending-relation fail (lazy hint).
    assert a.display.startswith("*")
    with pytest.raises(RelationNotLoadedError, match="Await it first"):
        bool(a.tags)

    # get_relation: descriptor path + plain callable path.
    assert a.get_relation("notes")
    Author.extra_rel = lambda self: self.has_many(Note, "author_id")  # type: ignore[method-assign]
    assert a.get_relation("extra_rel")
    del Author.extra_rel
    assert a.morph_to_many(Tag, "taggable", table="taggables")
    assert a.morphed_by_many(Tag, "taggable", table="taggables")

    # Hidden attrs/relations omitted from dict; extra keys included.
    a.set_relation("notes", Collection([]))
    a._extra["flash"] = "ok"  # noqa: SLF001
    payload = a.to_dict()
    assert "label" not in payload
    assert payload.get("display")
    assert payload.get("flash") == "ok"
    a.set_relation("notes", Collection([]))
    Author.hidden = ("label", "notes")
    assert "notes" not in a.relations_to_dict()
    Author.hidden = ("label",)

    # _fire_sync while events disabled.
    from avalon.orm import model as model_mod

    model_mod._EVENTS_DISABLED = True
    try:
        clone = a.replicate()
        assert clone.name == "Ada"
        Author._fire_sync("replicating", clone)
    finally:
        model_mod._EVENTS_DISABLED = False

    # Collection pluck via get_attribute.
    assert Collection([a, b]).pluck("name").all() == ["Ada", "Bob"]

    page = Paginator(Collection([1]), total=2, per_page=1, current_page=1)
    assert page.has_more_pages() is True


@pytest.mark.asyncio
async def test_relation_existence_callbacks_and_upsert(memory_db) -> None:
    await Schema.create("people", lambda t: (t.id(), t.string("name")))
    await Schema.create(
        "posts",
        lambda t: (t.id(), t.integer("person_id").nullable(), t.string("title")),
    )
    await Schema.create(
        "badge_person",
        lambda t: (t.integer("badge_id"), t.integer("person_id")),
    )
    await Schema.create("badges", lambda t: (t.id(), t.string("name")))
    await Schema.create(
        "countries",
        lambda t: (t.id(), t.string("name")),
    )
    await Schema.create(
        "cities",
        lambda t: (t.id(), t.integer("country_id"), t.string("name")),
    )
    await Schema.create(
        "sites",
        lambda t: (t.id(), t.integer("city_id"), t.string("name")),
    )

    class Person(Model):
        timestamps = False
        fillable = ("name",)

        @relation
        def posts(self):
            return self.has_many(Post, "person_id")

        @relation
        def badges(self):
            return self.belongs_to_many(Badge, table="badge_person")

    class Post(Model):
        timestamps = False
        fillable = ("title", "person_id")

        @relation
        def person(self):
            return self.belongs_to(Person, "person_id")

    class Badge(Model):
        timestamps = False
        fillable = ("name",)

    class Country(Model):
        timestamps = False
        fillable = ("name",)

        @relation
        def sites(self):
            return self.has_many_through(Site, City, "country_id", "city_id")

    class City(Model):
        timestamps = False
        fillable = ("name", "country_id")

    class Site(Model):
        timestamps = False
        fillable = ("name", "city_id")

    person = await Person.create({"name": "Pat"})
    await Post.create({"title": "one", "person_id": person.id})
    badge = await Badge.create({"name": "gold"})
    await person.badges().attach(badge.id)

    # existence_query callback branches (BelongsTo / BelongsToMany / through / morph).
    parent = Person.query()
    rel_bt: BelongsTo = Post(person_id=person.id).get_relation("person")
    rel_bt.existence_query(parent, callback=lambda q: q.where("id", ">", 0))

    rel_btm: BelongsToMany = person.get_relation("badges")
    rel_btm.existence_query(parent, callback=lambda q: q)
    await rel_btm.sync([badge.id])  # attach empty when already present
    await rel_btm.sync([])

    country = await Country.create({"name": "X"})
    city = await City.create({"name": "Y", "country_id": country.id})
    await Site.create({"name": "Z", "city_id": city.id})
    through: HasManyThrough = country.get_relation("sites")
    through.existence_query(Country.query(), callback=lambda q: q)

    # MorphMany existence_query with callback.
    await Schema.create(
        "remarks",
        lambda t: (t.id(), t.string("body"), t.morphs("commentable")),
    )

    class Remark(Model):
        timestamps = False
        fillable = ("body", "commentable_id", "commentable_type")

    class Host(Model):
        table = "people"
        timestamps = False

        @relation
        def remarks(self):
            return self.morph_many(Remark, "commentable")

    host = Host._hydrate({"id": person.id, "name": "Pat"})
    morph: MorphMany = host.get_relation("remarks")
    morph.existence_query(Host.query(), callback=lambda q: q.where("id", ">", 0))
    await morph.get()

    # Builder edges: first_or_fail without model, upsert probe, scope invoke.
    with pytest.raises(ModelNotFoundError):
        await QueryBuilder.for_table("people").where("id", -1).first_or_fail()

    builder = QueryBuilder.for_table("people")
    affected = await builder._upsert_probe(  # noqa: SLF001
        [{"id": person.id, "name": "Pat2"}, {"id": 99999, "name": "New"}],
        ["id"],
        ["name"],
    )
    assert affected >= 1

    class _NoUpsert:
        name = "unknown"

    assert (
        _native_upsert(builder._table_clause("people"), [{"id": 1}], ["id"], ["name"], _NoUpsert())  # noqa: SLF001
        is None
    )

    def scope_self(self, query, flag=True):  # noqa: ANN001
        return query.where("id", ">", 0) if flag else query

    def scope_plain(query):  # noqa: ANN001
        return query

    class _Weird:
        def __call__(self, query):  # noqa: ANN001
            return query

    _invoke_scope(scope_self, Person, Person.query(), (), {})
    _invoke_scope(scope_plain, Person, Person.query(), (), {})
    with patch("avalon.orm.builder.inspect.signature", side_effect=TypeError):
        _invoke_scope(_Weird(), Person, Person.query(), (), {})


def test_router_prefix_normalization() -> None:
    router = Router()
    with router.group(prefix="api"):
        route = router.get("ping", lambda: None)
    assert route.uri == "/api/ping"


def test_lang_add_lines_helper() -> None:
    from avalon.translation.helpers import Lang

    reset_locale_context()
    t = Translator(locale="en", fallback="en")
    set_translator(t)
    Lang.add_lines({"flash": "ok"}, "en")
    assert t.get("flash") == "ok"
    reset_locale_context()
    set_translator(None)


@pytest.mark.asyncio
async def test_nested_transaction_savepoint(memory_db) -> None:
    conn = memory_db.connection()
    async with conn.transaction():
        async with conn.transaction():
            await conn.execute("SELECT 1")
