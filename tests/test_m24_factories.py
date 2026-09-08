"""M24 model factories — definitions, states, sequences, relationships."""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any

import pytest

from almasix.orm import Schema
from almasix.orm.collection import Collection
from almasix.orm.factories import (
    CrossJoinSequence,
    Factory,
    FactoryError,
    Fake,
    FakeUniquenessError,
    HasFactory,
    RelationshipError,
    Sequence,
    fake,
)
from almasix.orm.model import Model, relation
from almasix.orm.soft_deletes import SoftDeletes
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.anyio


# --- the models under test ------------------------------------------------


class Author(HasFactory, Model):
    table = "authors"
    timestamps = False

    @relation
    def books(self) -> Any:
        return self.has_many(Book)

    @relation
    def profile(self) -> Any:
        return self.has_one(Profile)

    @relation
    def tags(self) -> Any:
        return self.belongs_to_many(Tag, table="author_tag").with_pivot("kind")

    @relation
    def notes(self) -> Any:
        return self.morph_many(Note, "notable")


class Profile(HasFactory, Model):
    table = "profiles"
    timestamps = False

    @relation
    def author(self) -> Any:
        return self.belongs_to(Author)


class Book(SoftDeletes, HasFactory, Model):
    table = "books"
    timestamps = False

    @relation
    def author(self) -> Any:
        return self.belongs_to(Author)


class Tag(HasFactory, Model):
    table = "tags"
    timestamps = False


class Note(HasFactory, Model):
    table = "notes"
    timestamps = False

    @relation
    def notable(self) -> Any:
        return self.morph_to("notable", {"author": Author})


# --- the factories --------------------------------------------------------


class AuthorFactory(Factory):
    model = Author

    def definition(self) -> dict[str, Any]:
        return {"name": self.fake.name(), "email": self.fake.unique().safe_email()}


class ProfileFactory(Factory):
    model = Profile

    def definition(self) -> dict[str, Any]:
        return {"bio": self.fake.sentence()}


class BookFactory(Factory):
    model = Book

    def definition(self) -> dict[str, Any]:
        return {"title": self.fake.title(), "published": True}

    def draft(self) -> Factory:
        return self.state({"published": False})


class TagFactory(Factory):
    model = Tag

    def definition(self) -> dict[str, Any]:
        return {"label": self.fake.word()}


class NoteFactory(Factory):
    model = Note

    def definition(self) -> dict[str, Any]:
        return {"body": self.fake.sentence()}


async def schema() -> None:
    await Schema.create(
        "authors",
        lambda t: (t.id(), t.string("name"), t.string("email").nullable()),
    )
    await Schema.create(
        "profiles",
        lambda t: (t.id(), t.integer("author_id").nullable(), t.string("bio")),
    )
    await Schema.create(
        "books",
        lambda t: (
            t.id(),
            t.integer("author_id").nullable(),
            t.string("title"),
            t.boolean("published").default(True),
            t.soft_deletes(),
        ),
    )
    await Schema.create("tags", lambda t: (t.id(), t.string("label")))
    await Schema.create(
        "author_tag",
        lambda t: (
            t.integer("author_id"),
            t.integer("tag_id"),
            t.string("kind").nullable(),
        ),
    )
    await Schema.create(
        "notes",
        lambda t: (t.id(), t.string("body"), t.morphs("notable")),
    )


# --- definitions, make, create --------------------------------------------


async def test_a_factory_makes_one_unsaved_model(memory_db) -> None:  # noqa: F811
    del memory_db
    author = await AuthorFactory.new().make()
    assert isinstance(author, Author)
    assert author.name and "@" in author.email
    assert not author.exists


async def test_a_factory_creates_and_persists(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()
    assert author.exists
    assert await Author.query().count() == 1


async def test_a_count_returns_a_collection(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    authors = await Author.factory().count(3).create()
    assert isinstance(authors, Collection)
    assert len(authors) == 3
    assert await Author.query().count() == 3

    assert len(await Author.factory().count(0).make()) == 0


async def test_times_and_new_are_the_two_entry_points(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    assert len(await AuthorFactory.times(2).create()) == 2
    assert (await AuthorFactory.new({"name": "Ada"}).make()).name == "Ada"


async def test_attributes_passed_to_make_and_create_win(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    assert (await Author.factory().make({"name": "Grace"})).name == "Grace"
    assert (await Author.factory().create({"name": "Grace"})).name == "Grace"


async def test_a_factory_bypasses_the_mass_assignment_guard(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    assert Author._totally_guarded()
    author = await Author.factory().create()
    assert author.name


async def test_raw_returns_attributes_without_a_model(memory_db) -> None:  # noqa: F811
    del memory_db
    single = await AuthorFactory.new().raw({"name": "Ada"})
    assert single["name"] == "Ada"

    many = await AuthorFactory.new().count(2).raw()
    assert len(many) == 2 and many[0]["email"] != many[1]["email"]


async def test_one_and_many_helpers(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    assert isinstance(await Author.factory().count(5).make_one(), Author)
    assert isinstance(await Author.factory().count(5).create_one(), Author)
    assert len(await Author.factory().make_many(2)) == 2
    assert len(await Author.factory().create_many([{"name": "A"}, {"name": "B"}])) == 2
    assert len(await Author.factory().count(3).create_many()) == 3
    assert await Author.query().count() == 6


async def test_lazy_defers_the_write(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    later = Author.factory().lazy({"name": "Ada"})
    assert await Author.query().count() == 0
    author = await later()
    assert author.name == "Ada"
    assert await Author.query().count() == 1


# --- states ---------------------------------------------------------------


async def test_a_state_can_be_a_dict_a_callable_or_a_coroutine(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()

    async def shout(attributes: dict[str, Any]) -> dict[str, Any]:
        return {"name": attributes["name"].upper()}

    author = await (
        Author.factory()
        .state({"name": "Ada"})
        .state(lambda attributes: {"email": f"{attributes['name'].lower()}@example.com"})
        .state(shout)
        .create()
    )
    assert author.name == "ADA"
    assert author.email == "ada@example.com"


async def test_a_state_callable_can_read_the_parent(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create({"name": "Ada"})
    seen: list[Any] = []

    await (
        Book.factory()
        .state(lambda attributes, parent: seen.append(parent) or {})
        .create(parent=author)
    )
    assert seen == [author]


async def test_set_is_a_one_key_state(memory_db) -> None:  # noqa: F811
    del memory_db
    assert (await Author.factory().set("name", "Ada").make()).name == "Ada"


async def test_a_state_method_reads_like_laravel(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    book = await BookFactory.new().draft().create()
    assert book.published is False


async def test_a_factory_is_immutable(memory_db) -> None:  # noqa: F811
    del memory_db
    base = Author.factory()
    named = base.state({"name": "Ada"})
    assert (await base.make()).name != "Ada"
    assert (await named.make()).name == "Ada"


# --- sequences ------------------------------------------------------------


async def test_a_sequence_cycles_through_its_states(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    books = await (
        Book.factory().count(4).sequence({"published": True}, {"published": False}).create()
    )
    assert [book.published for book in books] == [True, False, True, False]


async def test_a_sequence_step_can_read_its_index(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    books = await (
        Book.factory().count(3).sequence(lambda sequence: {"title": f"n{sequence.index}"}).create()
    )
    assert [book.title for book in books] == ["n0", "n1", "n2"]


async def test_for_each_sequence_sets_the_count(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    books = await Book.factory().for_each_sequence(
        {"title": "one"}, {"title": "two"}, {"title": "three"}
    ).create()
    assert [book.title for book in books] == ["one", "two", "three"]


async def test_a_cross_join_sequence_is_every_combination(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    books = await (
        Book.factory()
        .count(4)
        .cross_join_sequence(
            [{"title": "a"}, {"title": "b"}],
            [{"published": True}, {"published": False}],
        )
        .create()
    )
    assert [(book.title, book.published) for book in books] == [
        ("a", True),
        ("a", False),
        ("b", True),
        ("b", False),
    ]


def test_an_empty_sequence_yields_nothing() -> None:
    assert Sequence()({}) == {}
    assert CrossJoinSequence().count == 1


# --- relationships --------------------------------------------------------


async def test_has_creates_children_for_a_has_many(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().has(Book.factory().count(3)).create()
    assert await Book.query().where("author_id", "=", author.id).count() == 3


async def test_has_creates_a_child_for_a_has_one(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().has(Profile.factory(), "profile").create()
    profile = await Profile.query().where("author_id", "=", author.id).first()
    assert profile is not None


async def test_has_creates_children_for_a_morph_many(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().has(Note.factory().count(2), "notes").create()
    notes = await Note.query().where("notable_id", "=", author.id).get()
    assert len(notes) == 2
    assert {note.notable_type for note in notes} == {"Author"}


async def test_has_attached_writes_the_pivot(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await (
        Author.factory().has_attached(Tag.factory().count(2), {"kind": "topic"}, "tags").create()
    )
    tags = await author.get_relation("tags").get()
    assert len(tags) == 2
    assert {tag.pivot.kind for tag in tags} == {"topic"}


async def test_has_attached_takes_existing_models_and_a_pivot_callable(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    tags = await Tag.factory().count(2).create()
    author = await (
        Author.factory()
        .has_attached(tags, lambda tag: {"kind": tag.label}, "tags")
        .create()
    )
    attached = await author.get_relation("tags").get()
    assert {tag.pivot.kind for tag in attached} == {tag.label for tag in tags}


async def test_for_supplies_the_parent(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    book = await Book.factory().for_(Author.factory().state({"name": "Ada"})).create()
    author = await Author.find(book.author_id)
    assert author.name == "Ada"


async def test_for_accepts_a_model_and_reuses_it(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()
    books = await Book.factory().count(2).for_(author).create()
    assert {book.author_id for book in books} == {author.id}
    assert await Author.query().count() == 1


async def test_a_batch_shares_the_one_parent_for_made(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    books = await Book.factory().count(3).for_(Author.factory()).create()
    assert len({book.author_id for book in books}) == 1
    assert await Author.query().count() == 1


async def test_for_prefers_a_recycled_parent(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()
    books = await Book.factory().count(2).for_(Author.factory()).recycle(author).create()
    assert {book.author_id for book in books} == {author.id}
    assert await Author.query().count() == 1


async def test_for_a_morph_to_writes_both_columns(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()
    note = await Note.factory().for_(author, "notable").create()
    assert note.notable_id == author.id
    assert note.notable_type == "Author"


async def test_the_magic_relation_methods(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().has_books(2).create()
    assert await Book.query().where("author_id", "=", author.id).count() == 2

    author = await Author.factory().has_books(1, {"title": "Named"}).create()
    named = await Book.query().where("title", "=", "Named").first()
    assert named is not None and named.author_id == author.id

    book = await Book.factory().for_author({"name": "Grace"}).create()
    assert (await Author.find(book.author_id)).name == "Grace"


async def test_the_magic_methods_reject_what_is_not_a_relation(memory_db) -> None:  # noqa: F811
    del memory_db
    with pytest.raises(AttributeError):
        Author.factory().has_nothing  # noqa: B018 - the lookup itself is what raises
    with pytest.raises(AttributeError):
        Author.factory().not_a_relation_helper  # noqa: B018


async def test_has_and_for_report_the_wrong_relation_kind(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    with pytest.raises(RelationshipError):
        await Book.factory().has(Author.factory(), "author").create()
    with pytest.raises(RelationshipError):
        await Author.factory().for_(Author.factory(), "books").create()
    with pytest.raises(RelationshipError):
        await Author.factory().has_attached(Book.factory(), None, "books").create()


async def test_a_factory_attribute_creates_the_related_row(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()

    class NestedBookFactory(Factory):
        model = Book

        def definition(self) -> dict[str, Any]:
            return {"title": "nested", "author_id": AuthorFactory.new()}

    book = await NestedBookFactory.new().create()
    assert await Author.find(book.author_id) is not None


async def test_a_model_attribute_becomes_its_key(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()
    book = await Book.factory().create({"author_id": author})
    assert book.author_id == author.id


async def test_recycle_reuses_a_parent_instead_of_creating_one(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()

    class NestedBookFactory(Factory):
        model = Book

        def definition(self) -> dict[str, Any]:
            return {"title": "nested", "author_id": AuthorFactory.new()}

    books = await NestedBookFactory.new().count(3).recycle(author).create()
    assert {book.author_id for book in books} == {author.id}
    assert await Author.query().count() == 1

    factory = Author.factory().recycle({Author: [author]})
    assert factory.get_random_recycled_model(Author) is author
    assert factory.get_random_recycled_model(Book) is None


async def test_recycled_models_reach_children_and_parents(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().create()

    class NestedBookFactory(Factory):
        model = Book

        def definition(self) -> dict[str, Any]:
            return {"title": "nested", "author_id": AuthorFactory.new()}

    created = await Author.factory().has(NestedBookFactory.new(), "books").recycle(author).create()
    assert created.id != author.id


async def test_the_relationship_name_is_guessed_from_the_related_model(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().has(Book.factory().count(2)).has(Profile.factory()).create()
    assert await Book.query().where("author_id", "=", author.id).count() == 2
    assert await Profile.query().where("author_id", "=", author.id).count() == 1


async def test_has_can_attach_through_a_belongs_to_many(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    author = await Author.factory().has(Tag.factory().count(2), "tags").create()
    assert len(await author.get_relation("tags").get()) == 2


async def test_has_attached_takes_a_single_model(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    tag = await Tag.factory().create()
    author = await Author.factory().has_attached(tag, {"kind": "one"}, "tags").create()
    attached = await author.get_relation("tags").get()
    assert [t.id for t in attached] == [tag.id]

    with pytest.raises(FactoryError, match="nothing it could attach"):
        Author.factory().has_attached([], None, "tags")


async def test_a_callable_attribute_is_given_the_row_so_far(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()

    class DerivedFactory(Factory):
        model = Author

        def definition(self) -> dict[str, Any]:
            return {
                "name": "Ada",
                "email": lambda attributes: f"{attributes['name'].lower()}@example.com",
            }

    assert (await DerivedFactory.new().make()).email == "ada@example.com"


async def test_hooks_may_take_any_arity(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    seen: list[Any] = []

    author = await (
        Author.factory()
        .after_making(lambda *arguments: seen.append(len(arguments)))
        .state(lambda *arguments: {"name": f"n{len(arguments)}"})
        .make()
    )
    assert author.name == "n2"
    assert seen == [1]


async def test_an_empty_loaded_relation_is_dropped_before_saving(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()

    def empty_books(model: Any) -> None:
        model.set_relation("books", Author.new_collection([]))

    author = await Author.factory().after_making(empty_books).create()
    assert not author.relation_loaded("books")

    def one_book(model: Any) -> None:
        model.set_relation("books", Author.new_collection([Book()]))

    kept = await Author.factory().after_making(one_book).create()
    assert kept.relation_loaded("books")


# --- hooks, quiet writes, trashed rows ------------------------------------


async def test_after_making_and_after_creating_run(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    made: list[Any] = []
    created: list[Any] = []

    async def note_creation(model: Any, parent: Any) -> None:
        created.append((model, parent))

    author = await (
        Author.factory()
        .after_making(lambda model: made.append(model))
        .after_creating(note_creation)
        .create()
    )
    assert made == [author]
    assert created == [(author, None)]


async def test_configure_registers_hooks_up_front(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    seen: list[Any] = []

    class ConfiguredFactory(Factory):
        model = Author

        def definition(self) -> dict[str, Any]:
            return {"name": "Ada"}

        def configure(self) -> Factory:
            return self.after_creating(lambda model: seen.append(model.name))

    await ConfiguredFactory.new().create()
    assert seen == ["Ada"]


async def test_quiet_creation_skips_model_events(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    fired: list[str] = []
    Author.listen("created", lambda model: fired.append(model.name))

    await Author.factory().create()
    assert len(fired) == 1

    await Author.factory().create_quietly()
    await Author.factory().create_one_quietly()
    await Author.factory().create_many_quietly(2)
    assert len(fired) == 1
    Author._events["created"].clear()


async def test_trashed_creates_an_already_deleted_row(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    book = await Book.factory().trashed().create()
    assert book.trashed()
    assert await Book.query().count() == 0
    assert len(await Book.with_trashed().get()) == 1

    stamp = datetime(2020, 1, 1)  # noqa: DTZ001 - the column is naive, like the ORM's
    dated = await Book.factory().trashed(stamp).create()
    assert dated.get_raw_attribute("deleted_at") == stamp


async def test_a_factory_can_name_its_connection(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()

    author = await Author.factory().connection("sqlite").create()
    assert author.get_connection_name() == "sqlite"
    assert (await Author.factory().connection("sqlite").make()).get_connection_name() == "sqlite"


# --- resolution -----------------------------------------------------------


async def test_a_model_names_its_own_factory(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()

    class Explicit(HasFactory, Model):
        table = "authors"
        timestamps = False

        @classmethod
        def new_factory(cls) -> Factory:
            return AuthorFactory.new()

    assert isinstance(await Explicit.factory().make(), Author)


async def test_a_factory_guesses_its_model_from_its_name() -> None:
    class TagFactoryByName(Factory):
        def definition(self) -> dict[str, Any]:
            return {}

    class TagFactory2(Factory):
        def definition(self) -> dict[str, Any]:
            return {}

    with pytest.raises(FactoryError):
        TagFactoryByName.model_name()
    with pytest.raises(FactoryError):
        TagFactory2.model_name()

    class Tag2Factory(Factory):
        def definition(self) -> dict[str, Any]:
            return {}

    class Tag2(Model):
        table = "tags"

    assert Tag2Factory.model_name() is Tag2


async def test_a_factory_named_after_the_model_is_found_without_declaring_it() -> None:
    class Gadget(HasFactory, Model):
        table = "gadgets"

    class GadgetFactory(Factory):
        def definition(self) -> dict[str, Any]:
            return {"name": "gadget"}

    assert (await Gadget.factory().make()).name == "gadget"


async def test_model_factory_takes_a_count_a_state_or_both(memory_db) -> None:  # noqa: F811
    del memory_db
    await schema()
    assert (await Author.factory({"name": "Ada"}).make()).name == "Ada"
    made = await Author.factory(2, {"name": "Grace"}).make()
    assert [author.name for author in made] == ["Grace", "Grace"]


async def test_a_model_without_a_factory_says_so() -> None:
    class Orphan(HasFactory, Model):
        table = "orphans"

    with pytest.raises(FactoryError, match="No factory for Orphan"):
        Orphan.factory()


async def test_factories_are_imported_from_the_namespace(tmp_path, monkeypatch) -> None:
    package = tmp_path / "database" / "factories"
    package.mkdir(parents=True)
    (tmp_path / "database" / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "widget_factory.py").write_text(
        "from typing import Any\n\n"
        "from almasix.orm.factories import Factory\n"
        "from tests.test_m24_factories import Widget\n\n\n"
        "class WidgetFactory(Factory):\n"
        "    model = Widget\n\n"
        "    def definition(self) -> dict[str, Any]:\n"
        '        return {"name": "widget"}\n'
    )
    (package / "sprocket_factory.py").write_text("# a module, but no factory in it\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in [key for key in sys.modules if key.startswith("database")]:
        del sys.modules[name]

    factory = Widget.factory()
    assert (await factory.make()).name == "widget"

    with pytest.raises(FactoryError, match="^No factory for Sprocket in database.factories$"):
        Sprocket.factory()


class Widget(HasFactory, Model):
    """Resolved through `database.factories.widget_factory` in the test above."""

    table = "widgets"


class Sprocket(HasFactory, Model):
    """Its module exists but declares no factory — the error must say so."""

    table = "sprockets"


async def test_the_resolvers_can_be_replaced() -> None:
    class Unnamed(Factory):
        def definition(self) -> dict[str, Any]:
            return {}

    Factory.guess_model_names_using(lambda cls: Author)
    assert Unnamed.model_name() is Author
    Factory.guess_model_names_using(None)

    Factory.guess_factory_names_using(lambda model: AuthorFactory)
    assert isinstance(Factory.factory_for_model(Book), AuthorFactory)
    Factory.guess_factory_names_using(lambda model: None)
    assert isinstance(Factory.factory_for_model(Author), AuthorFactory)
    Factory.guess_factory_names_using(None)

    previous = Factory.namespace
    Factory.use_namespace("app.factories")
    assert Factory.namespace == "app.factories"
    Factory.use_namespace(previous)


async def test_a_factory_without_a_definition_says_so() -> None:
    class Bare(Factory):
        model = Author

    with pytest.raises(NotImplementedError):
        await Bare.new().make()


# --- the fake generator ---------------------------------------------------


def test_the_same_seed_gives_the_same_data() -> None:
    first = Fake(seed=42)
    second = Fake().seed(42)
    assert first.name() == second.name()
    assert first.email() == second.email()


def test_the_providers_produce_plausible_values() -> None:
    generator = Fake(seed=7)
    assert "@" in generator.email() and "@" in generator.safe_email()
    assert "@" in generator.free_email()
    assert generator.url().startswith("https://")
    assert generator.sentence().endswith(".")
    assert len(generator.words(3)) == 3
    assert isinstance(generator.words(2, as_text=True), str)
    assert len(generator.sentences(2)) == 2
    assert isinstance(generator.sentences(2, as_text=True), str)
    assert generator.paragraph().count(".") == 3
    assert len(generator.paragraphs(2)) == 2
    assert "\n\n" in generator.paragraphs(2, as_text=True)
    assert len(generator.text(80)) <= 80
    assert generator.title().istitle()
    assert 0 <= generator.random_digit() <= 9
    assert len(str(generator.random_number(4))) == 4
    assert 1 <= generator.number_between(1, 3) <= 3
    assert isinstance(generator.random_float(), float)
    assert generator.random_element([1]) == 1
    assert len(generator.random_elements([1, 2, 3], 2, unique=True)) == 2
    assert sorted(generator.shuffle([1, 2, 3])) == [1, 2, 3]
    assert generator.boolean(100) is True and generator.boolean(0) is False
    assert len(generator.uuid()) == 36
    assert len(generator.password(10)) == 10
    assert generator.hex_color().startswith("#")
    assert generator.currency_code() in {"KES", "TZS", "UGX", "EUR", "USD", "GBP", "JPY", "ZAR"}
    assert generator.user_name().islower()
    assert generator.job_title()
    assert generator.ipv4().count(".") == 3
    assert generator.slug(2).count("-") == 1
    assert generator.city() and generator.country() and len(generator.country_code()) == 2
    assert generator.postcode().isdigit()
    assert "," in generator.address()
    assert generator.phone_number().startswith("+254")
    assert generator.company()
    assert generator.domain_name().count(".") == 1


def test_the_time_providers_stay_inside_their_window() -> None:
    generator = Fake(seed=3)
    start = datetime(2020, 1, 1)  # noqa: DTZ001 - the ORM stores naive UTC
    end = datetime(2020, 12, 31)  # noqa: DTZ001
    when = generator.date_time_between(start, end)
    assert start <= when <= end
    assert isinstance(generator.date_time(), datetime)
    assert generator.date_time_this_month().month == datetime.now().month  # noqa: DTZ005
    assert generator.date().year >= 2000
    assert generator.time().hour <= 23


def test_unique_never_repeats_and_gives_up_honestly() -> None:
    generator = Fake(seed=1)
    values = {generator.unique().random_int(1, 50) for _ in range(20)}
    assert len(values) == 20

    generator.reset_unique()
    unique = generator.unique(retries=5)
    unique.random_int(1, 1)
    with pytest.raises(FakeUniquenessError):
        unique.random_int(1, 1)


def test_laravel_spellings_reach_the_same_providers() -> None:
    generator = Fake(seed=9)
    assert "@" in generator.safeEmail()
    assert generator.randomElement([1]) == 1
    with pytest.raises(AttributeError):
        generator.no_such_provider()


def test_the_generator_can_be_replaced_wholesale() -> None:
    class Loud(Fake):
        def name(self) -> str:
            return "LOUD"

    Fake.resolve_using(Loud)
    try:
        assert AuthorFactory.new().fake.name() == "LOUD"
    finally:
        Fake.resolve_using(None)
    assert isinstance(AuthorFactory.new().faker, Fake)
    assert fake.name()
