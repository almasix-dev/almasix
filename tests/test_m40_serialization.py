"""M40 — serialization controls and the Eloquent collection surface."""

from __future__ import annotations

import json
from typing import Any

import pytest

from avalon.orm import Collection, Model, Schema, relation
from tests.orm_support import memory_db  # noqa: F401 - fixture

pytestmark = pytest.mark.asyncio


class Writer(Model):
    table = "writers"
    fillable = ("name", "email", "secret")
    hidden = ("secret",)
    appends = ("shout",)

    def get_shout_attribute(self, _value: Any = None) -> str:
        return f"{self.name}!"

    def get_initials_attribute(self, _value: Any = None) -> str:
        return (self.name or "")[:1]

    @relation
    def articles(self):
        return self.has_many(Article)


class Article(Model):
    table = "articles"
    fillable = ("title", "writer_id")

    @relation
    def writer(self):
        return self.belongs_to(Writer)


@pytest.fixture
async def schema(memory_db) -> None:  # noqa: ANN001
    await Schema.create(
        "writers",
        lambda table: (
            table.id(),
            table.string("name"),
            table.string("email").nullable(),
            table.string("secret").nullable(),
            table.timestamps(),
        ),
    )
    await Schema.create(
        "articles",
        lambda table: (
            table.id(),
            table.string("title"),
            table.foreign_id("writer_id").nullable(),
            table.timestamps(),
        ),
    )


# --- appending --------------------------------------------------------------


async def test_appends_are_included_and_respect_hidden() -> None:
    writer = Writer(name="Ada", secret="s3cret")
    data = writer.to_dict()
    assert data["shout"] == "Ada!"
    assert "secret" not in data


async def test_append_adds_accessors_for_one_instance_only() -> None:
    first = Writer(name="Ada")
    second = Writer(name="Alan")

    first.append("initials")

    assert first.to_dict()["initials"] == "A"
    assert "initials" not in second.to_dict()
    assert Writer.appends == ("shout",)


async def test_merge_appends_takes_a_list() -> None:
    writer = Writer(name="Ada").merge_appends(["initials"])
    assert set(writer.to_dict()) >= {"shout", "initials"}


async def test_set_appends_replaces_the_list() -> None:
    writer = Writer(name="Ada").set_appends(["initials"])
    data = writer.to_dict()
    assert data["initials"] == "A"
    assert "shout" not in data
    assert Writer.appends == ("shout",)


async def test_without_appends_drops_them_all() -> None:
    writer = Writer(name="Ada").without_appends()
    assert "shout" not in writer.to_dict()
    assert writer.get_appends() == ()
    assert Writer(name="Alan").get_appends() == ("shout",)


async def test_appends_respect_a_visible_allowlist() -> None:
    # Laravel: appended attributes also honor `visible`.
    writer = Writer(name="Ada").set_visible(["name"])
    data = writer.to_dict()
    assert set(data) == {"name"}

    writer.merge_visible(["shout"])
    assert set(writer.to_dict()) == {"name", "shout"}


# --- hiding and revealing ---------------------------------------------------


async def test_merge_hidden_and_merge_visible_are_per_instance() -> None:
    writer = Writer(name="Ada", email="ada@example.test", secret="s3cret")

    writer.merge_hidden(["email"])
    assert "email" not in writer.to_dict()

    other = Writer(name="Alan", email="alan@example.test")
    assert "email" in other.to_dict()

    revealed = Writer(name="Grace", secret="s3cret").merge_visible(["name"])
    assert set(revealed.to_dict()) == {"name"}


async def test_relations_respect_hidden_and_visible(schema) -> None:  # noqa: ANN001
    writer = await Writer.create(name="Ada")
    await Article.create(title="On Computing", writer_id=writer.id)

    loaded = await Writer.query().with_("articles").first()
    assert loaded is not None
    assert "articles" in loaded.to_dict()

    loaded.make_hidden("articles")
    assert "articles" not in loaded.to_dict()

    allowed = await Writer.query().with_("articles").first()
    assert allowed is not None
    allowed.set_visible(["name"])
    assert set(allowed.to_dict()) == {"name"}


async def test_to_json_forwards_options() -> None:
    writer = Writer(name="Ada")
    assert json.loads(writer.to_json())["name"] == "Ada"
    assert "\n" in writer.to_json(indent=2)


# --- collection lookups -----------------------------------------------------


@pytest.fixture
async def writers(schema) -> Collection[Writer]:  # noqa: ANN001
    for name in ("Ada", "Alan", "Grace"):
        await Writer.create(name=name)
    return await Writer.all()


async def test_collection_find_by_key_model_and_callback(writers) -> None:  # noqa: ANN001
    first = writers[0]

    assert writers.find(first.id) is first
    assert writers.find(first) is first
    assert writers.find(lambda model: model.name == "Grace").name == "Grace"
    assert writers.find(9999) is None
    assert writers.find(9999, "fallback") == "fallback"


async def test_collection_contains_accepts_keys_and_models(writers) -> None:  # noqa: ANN001
    first = writers[0]

    assert writers.contains(first.id) is True
    assert writers.contains(first) is True
    assert writers.contains(9999) is False
    assert writers.contains(lambda model: model.name == "Ada") is True
    assert writers.contains("name", "Ada") is True


async def test_collection_only_and_except_use_model_keys(writers) -> None:  # noqa: ANN001
    keys = writers.model_keys()

    assert writers.only(keys[0]).model_keys() == [keys[0]]
    assert writers.only([keys[0], keys[1]]).model_keys() == keys[:2]
    assert writers.except_(keys[0]).model_keys() == keys[1:]
    assert writers.except_([keys[0], keys[1]]).model_keys() == keys[2:]


async def test_collection_diff_intersect_and_unique_use_model_keys(writers) -> None:  # noqa: ANN001
    keys = writers.model_keys()
    subset = writers.only([keys[0]])

    assert writers.diff(subset).model_keys() == keys[1:]
    assert writers.intersect(subset).model_keys() == [keys[0]]

    duplicated = Collection([writers[0], writers[0], writers[1]])
    assert duplicated.unique().model_keys() == [keys[0], keys[1]]
    assert duplicated.unique("name").count() == 2


# --- collection serialization pass-throughs ---------------------------------


async def test_collection_visibility_helpers_apply_to_every_model(writers) -> None:  # noqa: ANN001
    writers.make_hidden("name")
    assert all("name" not in item.to_dict() for item in writers)

    writers.make_visible("name")
    assert all("name" in item.to_dict() for item in writers)

    writers.set_visible(["name"])
    assert all(set(item.to_dict()) == {"name"} for item in writers)

    writers.set_hidden(["name"])
    assert all("name" not in item.to_dict() for item in writers)


async def test_collection_append_applies_to_every_model(writers) -> None:  # noqa: ANN001
    writers.append("initials")
    assert all("initials" in item.to_dict() for item in writers)


# --- collection queries -----------------------------------------------------


async def test_collection_to_query_scopes_to_its_models(writers) -> None:  # noqa: ANN001
    keys = writers.model_keys()
    query = writers.only([keys[0]]).to_query()

    found = await query.get()
    assert found.model_keys() == [keys[0]]


async def test_to_query_rejects_an_empty_collection() -> None:
    with pytest.raises(ValueError, match="empty collection"):
        Collection([]).to_query()


async def test_collection_fresh_reloads_from_the_database(writers) -> None:  # noqa: ANN001
    writers[0].name = "Changed"
    assert writers[0].name == "Changed"

    reloaded = await writers.fresh()
    assert reloaded[0].name == "Ada"
    assert reloaded.model_keys() == writers.model_keys()


async def test_collection_fresh_may_eager_load(schema) -> None:  # noqa: ANN001
    writer = await Writer.create(name="Ada")
    await Article.create(title="On Computing", writer_id=writer.id)

    reloaded = await (await Writer.all()).fresh("articles")
    assert len(reloaded[0].articles) == 1


async def test_collection_fresh_drops_deleted_models(writers) -> None:  # noqa: ANN001
    removed = writers[0]
    await removed.delete()

    reloaded = await writers.fresh()
    assert removed.get_key() not in reloaded.model_keys()
    assert reloaded.count() == 2


async def test_collection_fresh_and_load_short_circuit_when_empty() -> None:
    empty: Collection[Any] = Collection([])
    assert await empty.fresh() is empty
    assert await empty.load("articles") is empty


# --- custom collections -----------------------------------------------------


class Sorted(Collection):
    """A custom collection, wired through `collection_class`."""

    def names(self) -> list[str]:
        return sorted(item.name for item in self)


async def test_a_model_may_return_a_custom_collection(schema) -> None:  # noqa: ANN001
    class Author(Writer):
        table = "writers"
        collection_class = Sorted

    await Author.create(name="Zoe")
    await Author.create(name="Ada")

    found = await Author.all()
    assert isinstance(found, Sorted)
    assert found.names() == ["Ada", "Zoe"]
    assert isinstance(Author.new_collection([]), Sorted)


async def test_the_default_collection_is_still_returned(writers) -> None:  # noqa: ANN001
    assert type(writers) is Collection
