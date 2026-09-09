"""M41 part 2 — relationship existence queries."""

from __future__ import annotations

import pytest

from almasix.orm import Model, Schema, relation
from tests.orm_support import memory_db  # noqa: F401


class Author(Model):
    table = "authors"
    fillable = ("name", "country")

    @relation
    def posts(self):
        return self.has_many(Article)


class Article(Model):
    table = "articles"
    fillable = ("author_id", "title", "published")

    @relation
    def author(self):
        return self.belongs_to(Author)

    @relation
    def comments(self):
        return self.morph_many(Remark, "commentable")


class Video(Model):
    table = "videos"
    fillable = ("title", "length")

    @relation
    def comments(self):
        return self.morph_many(Remark, "commentable")


class Remark(Model):
    table = "remarks"
    fillable = ("commentable_id", "commentable_type", "body", "spam")

    @relation
    def commentable(self):
        return self.morph_to("commentable", types={"Article": Article, "Video": Video})


async def _schema() -> None:
    await Schema.create(
        "authors",
        lambda t: (t.id(), t.string("name"), t.string("country").nullable(), t.timestamps()),
    )
    await Schema.create(
        "articles",
        lambda t: (
            t.id(),
            t.foreign_id("author_id"),
            t.string("title"),
            t.integer("published").default(1),
            t.timestamps(),
        ),
    )
    await Schema.create(
        "videos",
        lambda t: (t.id(), t.string("title"), t.integer("length").default(0), t.timestamps()),
    )
    await Schema.create(
        "remarks",
        lambda t: (
            t.id(),
            t.integer("commentable_id"),
            t.string("commentable_type"),
            t.string("body"),
            t.integer("spam").default(0),
            t.timestamps(),
        ),
    )


async def _seed() -> None:
    await _schema()
    ada = await Author.create(name="Ada", country="UK")
    grace = await Author.create(name="Grace", country="US")
    await Author.create(name="Silent", country="UK")

    prose = await Article.create(author_id=ada.id, title="Prose", published=1)
    await Article.create(author_id=ada.id, title="Draft", published=0)
    await Article.create(author_id=grace.id, title="Compilers", published=1)

    video = await Video.create(title="Talk", length=45)
    await Remark.create(commentable_id=prose.id, commentable_type="Article", body="nice", spam=0)
    await Remark.create(commentable_id=video.id, commentable_type="Video", body="buy now", spam=1)


async def _titles(builder) -> list[str]:
    return [model.title for model in await builder.get()]


async def _names(builder) -> list[str]:
    return [model.name for model in await builder.get()]


# --- or variants --------------------------------------------------------------


@pytest.mark.asyncio
async def test_or_has_widens_the_result_set(memory_db) -> None:
    await _seed()

    found = await _names(Author.query().where("country", "=", "US").or_has("posts"))

    assert found == ["Ada", "Grace"]


@pytest.mark.asyncio
async def test_or_doesnt_have_widens_the_result_set(memory_db) -> None:
    await _seed()

    found = await _names(Author.query().where("name", "=", "Ada").or_doesnt_have("posts"))

    assert found == ["Ada", "Silent"]


@pytest.mark.asyncio
async def test_or_where_has_applies_the_callback(memory_db) -> None:
    await _seed()

    found = await _names(
        Author.query()
        .where("name", "=", "Silent")
        .or_where_has("posts", lambda query: query.where("title", "=", "Compilers"))
    )

    assert found == ["Grace", "Silent"]


@pytest.mark.asyncio
async def test_or_where_doesnt_have_applies_the_callback(memory_db) -> None:
    await _seed()

    found = await _names(
        Author.query()
        .where("name", "=", "Grace")
        .or_where_doesnt_have("posts", lambda query: query.where("published", "=", 0))
    )

    assert found == ["Grace", "Silent"]


@pytest.mark.asyncio
async def test_or_has_honors_an_operator_and_count(memory_db) -> None:
    await _seed()

    found = await _names(Author.query().where("name", "=", "Silent").or_has("posts", ">=", 2))

    assert found == ["Ada", "Silent"]


# --- inline existence ---------------------------------------------------------


@pytest.mark.asyncio
async def test_where_relation_filters_without_a_callback(memory_db) -> None:
    await _seed()

    found = await _names(Author.query().where_relation("posts", "published", 0))

    assert found == ["Ada"]


@pytest.mark.asyncio
async def test_where_relation_accepts_an_explicit_operator(memory_db) -> None:
    await _seed()

    found = await _titles(Article.query().where_relation("author", "name", "!=", "Ada"))

    assert found == ["Compilers"]


@pytest.mark.asyncio
async def test_or_where_relation_widens_the_result_set(memory_db) -> None:
    await _seed()

    found = await _names(
        Author.query().where("name", "=", "Silent").or_where_relation("posts", "published", 0)
    )

    assert found == ["Ada", "Silent"]


@pytest.mark.asyncio
async def test_with_where_has_filters_and_constrains_the_eager_load(memory_db) -> None:
    await _seed()

    authors = (
        await Author.query()
        .with_where_has("posts", lambda query: query.where("published", "=", 1))
        .get()
    )

    assert [author.name for author in authors] == ["Ada", "Grace"]
    # Ada's unpublished draft is filtered out of the loaded relation too.
    assert [post.title for post in authors[0].posts] == ["Prose"]


@pytest.mark.asyncio
async def test_with_where_has_without_a_callback_still_eager_loads(memory_db) -> None:
    await _seed()

    authors = await Author.query().with_where_has("posts").get()

    assert [author.name for author in authors] == ["Ada", "Grace"]
    assert len(authors[0].posts) == 2


# --- nested existence ---------------------------------------------------------


@pytest.mark.asyncio
async def test_has_walks_nested_relations(memory_db) -> None:
    await _seed()

    assert await _names(Author.query().has("posts.comments")) == ["Ada"]


@pytest.mark.asyncio
async def test_where_has_passes_the_callback_to_the_innermost_relation(memory_db) -> None:
    await _seed()

    matching = Author.query().where_has(
        "posts.comments", lambda query: query.where("body", "=", "nice")
    )
    missing = Author.query().where_has(
        "posts.comments", lambda query: query.where("body", "=", "absent")
    )

    assert await _names(matching) == ["Ada"]
    assert await _names(missing) == []


@pytest.mark.asyncio
async def test_doesnt_have_negates_the_outermost_nested_relation(memory_db) -> None:
    await _seed()

    assert await _names(Author.query().doesnt_have("posts.comments")) == ["Grace", "Silent"]


# --- morph to existence -------------------------------------------------------


@pytest.mark.asyncio
async def test_where_has_morph_accepts_model_classes(memory_db) -> None:
    await _seed()

    found = await Remark.query().where_has_morph("commentable", [Article]).get()

    assert [remark.body for remark in found] == ["nice"]


@pytest.mark.asyncio
async def test_where_has_morph_defaults_to_every_mapped_type(memory_db) -> None:
    await _seed()

    found = await Remark.query().where_has_morph("commentable").get()

    assert [remark.body for remark in found] == ["nice", "buy now"]


@pytest.mark.asyncio
async def test_where_has_morph_passes_the_type_to_the_callback(memory_db) -> None:
    await _seed()
    seen: list[str] = []

    def constrain(query, morph_type):
        seen.append(morph_type)
        if morph_type == "Video":
            query.where("length", ">", 60)

    found = await Remark.query().where_has_morph("commentable", "*", constrain).get()

    assert seen == ["Article", "Video"]
    assert [remark.body for remark in found] == ["nice"]


@pytest.mark.asyncio
async def test_where_has_morph_accepts_a_single_arg_callback(memory_db) -> None:
    await _seed()

    found = await (
        Remark.query()
        .where_has_morph("commentable", ["Article"], lambda query: query.where("id", ">", 0))
        .get()
    )

    assert [remark.body for remark in found] == ["nice"]


@pytest.mark.asyncio
async def test_where_has_morph_accepts_alias_strings_and_mappings(memory_db) -> None:
    await _seed()

    by_alias = await Remark.query().where_has_morph("commentable", ["Video"]).get()
    by_mapping = await Remark.query().where_has_morph("commentable", {"Video": Video}).get()

    assert [remark.body for remark in by_alias] == ["buy now"]
    assert [remark.body for remark in by_mapping] == ["buy now"]


@pytest.mark.asyncio
async def test_where_has_morph_accepts_a_bare_type(memory_db) -> None:
    await _seed()

    by_class = await Remark.query().where_has_morph("commentable", Video).get()
    by_string = await Remark.query().where_has_morph("commentable", "Article").get()

    assert [remark.body for remark in by_class] == ["buy now"]
    assert [remark.body for remark in by_string] == ["nice"]


@pytest.mark.asyncio
async def test_where_doesnt_have_morph_inverts_the_match(memory_db) -> None:
    await _seed()

    found = await (
        Remark.query()
        .where_doesnt_have_morph(
            "commentable", [Video], lambda query: query.where("length", ">", 60)
        )
        .get()
    )

    assert [remark.body for remark in found] == ["nice", "buy now"]


@pytest.mark.asyncio
async def test_doesnt_have_morph_finds_orphaned_rows(memory_db) -> None:
    await _seed()
    await Remark.create(commentable_id=999, commentable_type="Article", body="orphan")

    found = await Remark.query().doesnt_have_morph("commentable").get()

    assert [remark.body for remark in found] == ["orphan"]


@pytest.mark.asyncio
async def test_or_morph_variants_widen_the_result_set(memory_db) -> None:
    await _seed()

    ored = await Remark.query().where("spam", "=", 1).or_has_morph("commentable", [Article]).get()
    or_where = await (
        Remark.query()
        .where("spam", "=", 1)
        .or_where_has_morph(
            "commentable", [Article], lambda query: query.where("published", "=", 1)
        )
        .get()
    )
    or_doesnt = await (
        Remark.query().where("spam", "=", 1).or_doesnt_have_morph("commentable", [Article]).get()
    )
    or_where_doesnt = await (
        Remark.query()
        .where("body", "=", "nice")
        .or_where_doesnt_have_morph("commentable", [Article])
        .get()
    )

    assert [remark.body for remark in ored] == ["nice", "buy now"]
    assert [remark.body for remark in or_where] == ["nice", "buy now"]
    assert [remark.body for remark in or_doesnt] == ["buy now"]
    assert [remark.body for remark in or_where_doesnt] == ["nice", "buy now"]


@pytest.mark.asyncio
async def test_where_morph_relation_filters_inline(memory_db) -> None:
    await _seed()

    found = (
        await Remark.query().where_morph_relation("commentable", [Article], "title", "Prose").get()
    )
    missing = (
        await Remark.query()
        .where_morph_relation("commentable", [Article], "title", "!=", "Prose")
        .get()
    )
    ored = await (
        Remark.query()
        .where("spam", "=", 1)
        .or_where_morph_relation("commentable", [Article], "title", "Prose")
        .get()
    )

    assert [remark.body for remark in found] == ["nice"]
    assert missing == []
    assert [remark.body for remark in ored] == ["nice", "buy now"]


@pytest.mark.asyncio
async def test_morph_existence_with_no_types_matches_nothing(memory_db) -> None:
    await _seed()

    assert await Remark.query().where_has_morph("commentable", []).get() == []


@pytest.mark.asyncio
async def test_morph_existence_rejects_unmapped_types(memory_db) -> None:
    await _seed()

    with pytest.raises(LookupError, match="Unmapped morph type"):
        Remark.query().where_has_morph("commentable", ["Podcast"])

    with pytest.raises(LookupError, match="Unmapped morph type"):
        Remark.query().where_has_morph("commentable", [Author])


@pytest.mark.asyncio
async def test_morph_existence_rejects_non_morph_relations(memory_db) -> None:
    await _seed()

    with pytest.raises(TypeError, match="not a morph_to relation"):
        Author.query().where_has_morph("posts", "*")


@pytest.mark.asyncio
async def test_existence_queries_require_a_model(memory_db) -> None:
    from almasix.orm.builder import QueryBuilder

    with pytest.raises(RuntimeError, match="require a model"):
        QueryBuilder.for_table("authors").has("posts")

    with pytest.raises(RuntimeError, match="require a model"):
        QueryBuilder.for_table("remarks").where_has_morph("commentable", "*")
