"""Opt-in awaitable lazy relations (``Model.lazy_relations``)."""

from __future__ import annotations

import pytest

from almasix.orm import Collection, Model, RelationNotLoadedError, relation
from tests.orm_support import memory_db  # noqa: F401


class Author(Model):
    table = "authors"
    fillable = ("name",)


class Book(Model):
    table = "books"
    fillable = ("title", "author_id")
    lazy_relations = True

    @relation
    def author(self):
        return self.belongs_to(Author)


class StrictBook(Model):
    table = "books"
    fillable = ("title", "author_id")
    lazy_relations = False

    @relation
    def author(self):
        return self.belongs_to(Author)


async def _schema(db) -> None:
    from almasix.orm import Schema

    await Schema.create(
        "authors",
        lambda t: (t.id(), t.string("name"), t.timestamps()),
    )
    await Schema.create(
        "books",
        lambda t: (
            t.id(),
            t.string("title"),
            t.foreign_id("author_id"),
            t.timestamps(),
        ),
    )


@pytest.mark.asyncio
async def test_lazy_relations_await_loads(memory_db) -> None:
    await _schema(memory_db)
    author = await Author.create(name="Ada")
    book = await Book.create(title="Notes", author_id=author.id)

    pending = book.author
    assert "lazy" in repr(pending)
    with pytest.raises(RelationNotLoadedError, match="Await it first"):
        bool(pending)

    loaded = await book.author
    assert loaded.id == author.id
    assert book.relation_loaded("author")
    # Second access returns the cached relation value (not PendingRelation).
    assert book.author.id == author.id


@pytest.mark.asyncio
async def test_lazy_relations_disabled_await_still_errors(memory_db) -> None:
    await _schema(memory_db)
    author = await Author.create(name="Grace")
    book = await StrictBook.create(title="Cobol", author_id=author.id)

    with pytest.raises(RelationNotLoadedError, match="lazy_relations = True"):
        await book.author

    await book.load("author")
    assert book.author.name == "Grace"


@pytest.mark.asyncio
async def test_lazy_relations_call_still_builds_query(memory_db) -> None:
    await _schema(memory_db)
    author = await Author.create(name="Edsger")
    book = await Book.create(title="Discipline", author_id=author.id)
    related = await book.author().first()
    assert related is not None
    assert related.name == "Edsger"
    assert isinstance(await Book.query().with_("author").get(), Collection)
