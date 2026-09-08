"""M41 part 5 — the last sections of Laravel's Relationships page.

`push`, dynamic relations, and per-type loading behind a `morph_to`.
"""

from __future__ import annotations

import pytest

from almasix.orm import Collection, Model, Schema, relation
from tests.orm_support import memory_db  # noqa: F401


class Shop(Model):
    table = "shops"
    fillable = ("name",)

    @relation
    def items(self):
        return self.has_many(Item)

    @relation
    def chaperoned_items(self):
        return self.has_many(Item).chaperone("shop")


class Item(Model):
    table = "items"
    fillable = ("shop_id", "title", "price")

    @relation
    def shop(self):
        return self.belongs_to(Shop)

    @relation
    def notes(self):
        return self.morph_many(Note, "notable")


class Video(Model):
    table = "videos"
    fillable = ("title",)

    @relation
    def notes(self):
        return self.morph_many(Note, "notable")

    @relation
    def clips(self):
        return self.has_many(Clip)


class Clip(Model):
    table = "clips"
    fillable = ("video_id", "seconds")


class Note(Model):
    table = "notes"
    fillable = ("notable_id", "notable_type", "body")

    @relation
    def notable(self):
        return self.morph_to("notable", types={"Item": Item, "Video": Video})


async def _schema() -> None:
    await Schema.create("shops", lambda t: (t.id(), t.string("name"), t.timestamps()))
    await Schema.create(
        "items",
        lambda t: (
            t.id(),
            t.foreign_id("shop_id").nullable(),
            t.string("title"),
            t.integer("price").default(0),
            t.timestamps(),
        ),
    )
    await Schema.create("videos", lambda t: (t.id(), t.string("title"), t.timestamps()))
    await Schema.create(
        "clips",
        lambda t: (t.id(), t.foreign_id("video_id"), t.integer("seconds"), t.timestamps()),
    )
    await Schema.create(
        "notes",
        lambda t: (
            t.id(),
            t.integer("notable_id"),
            t.string("notable_type"),
            t.string("body"),
            t.timestamps(),
        ),
    )


# --- push ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_push_saves_the_model_and_its_loaded_relations(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    await shop.items().create({"title": "Kettle", "price": 10})
    await shop.items().create({"title": "Mug", "price": 5})

    loaded = await Shop.with_relations("items").first()
    loaded.name = "Corner Store"
    for item in loaded.items:
        item.price = item.price * 2

    assert await loaded.push() is True

    fresh = await Shop.with_relations("items").first()
    assert fresh.name == "Corner Store"
    assert [item.price for item in fresh.items] == [20, 10]


@pytest.mark.asyncio
async def test_push_reaches_nested_relations(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    item = await shop.items().create({"title": "Kettle"})
    await item.notes().create({"body": "chipped"})

    loaded = await Shop.query().with_("items.notes").first()
    loaded.items[0].notes[0].body = "mended"

    await loaded.push()

    assert (await Note.query().first()).body == "mended"


@pytest.mark.asyncio
async def test_push_survives_a_chaperoned_cycle(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    await shop.items().create({"title": "Kettle"})

    # The child holds the parent, which holds the child.
    loaded = await Shop.with_relations("chaperoned_items").first()
    assert loaded.chaperoned_items[0].shop is loaded

    assert await loaded.push() is True


@pytest.mark.asyncio
async def test_push_stops_when_a_save_is_cancelled(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    await shop.items().create({"title": "Kettle"})
    Item.listen("saving", lambda model: False)

    loaded = await Shop.with_relations("items").first()
    try:
        assert await loaded.push() is False
    finally:
        Item._events = {}


@pytest.mark.asyncio
async def test_push_ignores_relations_that_are_not_models(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    shop.set_relation("items", Collection([]))
    shop.set_relation("missing", None)

    assert await shop.push() is True


# --- dynamic relations --------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_relation_using_defines_a_relation_from_outside(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    await shop.items().create({"title": "Kettle"})

    Shop.resolve_relation_using("stock", lambda model: model.has_many(Item))
    try:
        found = await shop.stock().get()
        assert [item.title for item in found] == ["Kettle"]

        # It eager loads and reads back like any declared relation.
        loaded = await Shop.query().with_("stock").first()
        assert [item.title for item in loaded.stock] == ["Kettle"]
    finally:
        Shop._dynamic_relations = {}


@pytest.mark.asyncio
async def test_unloaded_dynamic_relations_still_refuse_to_lazy_load(memory_db) -> None:
    from almasix.orm import RelationNotLoadedError

    await _schema()
    shop = await Shop.create(name="Corner")
    Shop.resolve_relation_using("stock", lambda model: model.has_many(Item))
    try:
        with pytest.raises(RelationNotLoadedError):
            len(shop.stock)
    finally:
        Shop._dynamic_relations = {}


@pytest.mark.asyncio
async def test_unknown_relations_still_raise(memory_db) -> None:
    await _schema()
    shop = await Shop.create(name="Corner")

    with pytest.raises(AttributeError, match="has no relation"):
        shop.get_relation("nowhere")


# --- where_belongs_to ---------------------------------------------------------


@pytest.mark.asyncio
async def test_where_belongs_to_guesses_the_relation(memory_db) -> None:
    await _schema()
    corner = await Shop.create(name="Corner")
    other = await Shop.create(name="Other")
    await corner.items().create({"title": "Kettle"})
    await other.items().create({"title": "Mug"})

    found = await Item.query().where_belongs_to(corner).get()

    assert [item.title for item in found] == ["Kettle"]


@pytest.mark.asyncio
async def test_where_belongs_to_accepts_many_parents_and_a_name(memory_db) -> None:
    await _schema()
    corner = await Shop.create(name="Corner")
    other = await Shop.create(name="Other")
    await corner.items().create({"title": "Kettle"})
    await other.items().create({"title": "Mug"})

    parents = await Shop.query().get()
    found = await Item.query().where_belongs_to(parents, "shop").order_by("title").get()

    assert [item.title for item in found] == ["Kettle", "Mug"]


@pytest.mark.asyncio
async def test_or_where_belongs_to_widens_the_match(memory_db) -> None:
    await _schema()
    corner = await Shop.create(name="Corner")
    other = await Shop.create(name="Other")
    await corner.items().create({"title": "Kettle"})
    await other.items().create({"title": "Mug"})

    found = await (
        Item.query().where("title", "=", "Mug").or_where_belongs_to(corner).order_by("title").get()
    )

    assert [item.title for item in found] == ["Kettle", "Mug"]


@pytest.mark.asyncio
async def test_where_belongs_to_complains_when_it_cannot_guess(memory_db) -> None:
    await _schema()
    video = await Video.create(title="Unboxing")

    with pytest.raises(RuntimeError, match="no belongs_to relation"):
        Item.query().where_belongs_to(video)

    with pytest.raises(ValueError, match="at least one parent"):
        Item.query().where_belongs_to([])

    from almasix.orm.builder import QueryBuilder

    with pytest.raises(RuntimeError, match="require a model"):
        QueryBuilder.for_table("items").where_belongs_to(video)


# --- morph to loading ---------------------------------------------------------


async def _seed_notes() -> None:
    await _schema()
    shop = await Shop.create(name="Corner")
    item = await shop.items().create({"title": "Kettle"})
    video = await Video.create(title="Unboxing")
    await Clip.create(video_id=video.id, seconds=30)
    await Clip.create(video_id=video.id, seconds=45)
    await Note.create(notable_id=item.id, notable_type="Item", body="on the item")
    await Note.create(notable_id=video.id, notable_type="Video", body="on the video")


@pytest.mark.asyncio
async def test_load_morph_loads_a_different_relation_per_type(memory_db) -> None:
    await _seed_notes()

    notes = await Note.query().get()
    await notes.load_morph("notable", {Item: ["shop"], Video: ["clips"]})

    by_body = {note.body: note for note in notes}
    assert by_body["on the item"].notable.shop.name == "Corner"
    assert len(by_body["on the video"].notable.clips) == 2


@pytest.mark.asyncio
async def test_load_morph_accepts_type_names(memory_db) -> None:
    await _seed_notes()

    note = await Note.query().where("notable_type", "=", "Video").first()
    await note.load_morph("notable", {"Video": ["clips"]})

    assert len(note.notable.clips) == 2


@pytest.mark.asyncio
async def test_load_morph_count_works_on_a_single_model(memory_db) -> None:
    await _seed_notes()

    note = await Note.query().where("notable_type", "=", "Video").first()
    await note.load_morph_count("notable", {Video: ["clips"]})

    assert note.notable.clips_count == 2


@pytest.mark.asyncio
async def test_load_morph_count_skips_types_the_spec_omits(memory_db) -> None:
    await _seed_notes()

    notes = await Note.query().get()
    await notes.load_morph_count("notable", {Video: ["clips"]})

    item_note = next(note for note in notes if note.body == "on the item")
    assert "notes_count" not in item_note.notable.to_dict()


@pytest.mark.asyncio
async def test_load_morph_count_counts_per_type(memory_db) -> None:
    await _seed_notes()

    notes = await Note.query().get()
    await notes.load_morph_count("notable", {Item: ["notes"], Video: ["clips"]})

    by_body = {note.body: note for note in notes}
    assert by_body["on the video"].notable.clips_count == 2
    assert by_body["on the item"].notable.notes_count == 1


@pytest.mark.asyncio
async def test_load_morph_leaves_unlisted_types_alone(memory_db) -> None:
    await _seed_notes()

    notes = await Note.query().get()
    await notes.load_morph("notable", {Video: ["clips"]})

    item_note = next(note for note in notes if note.body == "on the item")
    assert item_note.notable.relation_loaded("shop") is False


@pytest.mark.asyncio
async def test_morph_loading_on_an_empty_set_does_nothing(memory_db) -> None:
    from almasix.orm.eager import load_morph, load_morph_aggregate

    await _seed_notes()
    empty = await Note.query().where("body", "=", "absent").get()

    assert await empty.load_morph("notable", {Video: ["clips"]}) is empty
    assert await empty.load_morph_count("notable", {Video: ["clips"]}) is empty
    assert await load_morph([], "notable", {}) is None
    assert await load_morph_aggregate([], "notable", {}) is None


@pytest.mark.asyncio
async def test_morph_loading_skips_rows_pointing_nowhere(memory_db) -> None:
    await _seed_notes()
    await Note.create(notable_id=999, notable_type="Item", body="orphan")

    notes = await Note.query().get()
    await notes.load_morph("notable", {Item: ["shop"]})

    orphan = next(note for note in notes if note.body == "orphan")
    assert orphan.notable is None
