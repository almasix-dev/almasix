"""M41 part 4 — pivots, morph maps, touches, and relation write helpers."""

from __future__ import annotations

import pytest

from almasix.orm import (
    Model,
    Pivot,
    Schema,
    clear_morph_map,
    enforce_morph_map,
    morph_alias,
    morph_map,
    relation,
)
from tests.orm_support import memory_db  # noqa: F401


class Subscription(Pivot):
    """A custom intermediate model with behaviour of its own."""

    fillable = ("user_id", "plan_id", "tier", "created_at", "updated_at")

    @property
    def is_premium(self) -> bool:
        return self.get_raw_attribute("tier") == "gold"


class Learner(Model):
    table = "learners"
    fillable = ("name",)

    @relation
    def plans(self):
        return self.belongs_to_many(Plan).with_pivot("tier")

    @relation
    def stamped_plans(self):
        return self.belongs_to_many(Plan).with_timestamps()

    @relation
    def subscriptions(self):
        return (
            self.belongs_to_many(Plan)
            .using(Subscription)
            .as_("subscription")
            .with_pivot("tier")
        )

    @relation
    def gold_plans(self):
        return self.belongs_to_many(Plan).with_pivot("tier").where_pivot_in("tier", ["gold"])

    @relation
    def notes(self):
        return self.has_many(Note)


class Plan(Model):
    table = "plans"
    fillable = ("name", "price")

    @relation
    def learners(self):
        return self.belongs_to_many(Learner)


class Note(Model):
    table = "notes"
    fillable = ("learner_id", "body")
    touches = ("learner",)

    @relation
    def learner(self):
        return self.belongs_to(Learner)


async def _schema() -> None:
    await Schema.create("learners", lambda t: (t.id(), t.string("name"), t.timestamps()))
    await Schema.create(
        "plans",
        lambda t: (t.id(), t.string("name"), t.integer("price").default(0), t.timestamps()),
    )
    await Schema.create(
        "learner_plan",
        lambda t: (
            t.foreign_id("learner_id"),
            t.foreign_id("plan_id"),
            t.string("tier").nullable(),
            t.date_time("created_at").nullable(),
            t.date_time("updated_at").nullable(),
        ),
    )
    await Schema.create(
        "notes",
        lambda t: (t.id(), t.foreign_id("learner_id"), t.string("body"), t.timestamps()),
    )


async def _seed() -> tuple[Learner, Plan, Plan]:
    await _schema()
    learner = await Learner.create(name="Ada")
    gold = await Plan.create(name="Gold", price=90)
    basic = await Plan.create(name="Basic", price=10)
    return learner, gold, basic


# --- pivot access -------------------------------------------------------------


@pytest.mark.asyncio
async def test_pivot_columns_are_reachable_through_the_pivot_object(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.plans().attach(gold.id, {"tier": "gold"})

    plans = await learner.plans().get()

    assert plans[0].pivot.tier == "gold"
    assert plans[0].pivot.learner_id == learner.id
    assert plans[0].pivot.plan_id == gold.id


@pytest.mark.asyncio
async def test_pivot_is_hydrated_on_eager_loads_with_the_right_parent(memory_db) -> None:
    learner, gold, basic = await _seed()
    other = await Learner.create(name="Grace")
    await learner.plans().attach(gold.id, {"tier": "gold"})
    await other.plans().attach(basic.id, {"tier": "free"})

    learners = await Learner.with_relations("plans").get()

    assert learners[0].plans[0].pivot.tier == "gold"
    assert learners[0].plans[0].pivot.learner_id == learner.id
    assert learners[1].plans[0].pivot.learner_id == other.id


@pytest.mark.asyncio
async def test_as_renames_the_pivot_accessor(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.subscriptions().attach(gold.id, {"tier": "gold"})

    plans = await learner.subscriptions().get()

    assert plans[0].subscription.tier == "gold"


@pytest.mark.asyncio
async def test_using_hydrates_a_custom_pivot_model(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.subscriptions().attach(gold.id, {"tier": "gold"})
    await learner.subscriptions().attach(basic.id, {"tier": "free"})

    plans = await learner.subscriptions().get()

    assert isinstance(plans[0].subscription, Subscription)
    assert plans[0].subscription.is_premium is True
    assert plans[1].subscription.is_premium is False
    assert plans[0].subscription.get_pivot_table() == "learner_plan"


@pytest.mark.asyncio
async def test_pivot_first_hydrates_too(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.plans().attach(gold.id, {"tier": "gold"})

    assert (await learner.plans().first()).pivot.tier == "gold"
    assert await learner.gold_plans().first() is not None


@pytest.mark.asyncio
async def test_pivot_rows_can_be_saved_and_deleted(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.plans().attach(gold.id, {"tier": "free"})

    plan = await learner.plans().first()
    plan.pivot.tier = "gold"
    await plan.pivot.save()

    assert (await learner.plans().first()).pivot.tier == "gold"

    await plan.pivot.delete()
    assert await learner.plans().get() == []


# --- pivot timestamps ---------------------------------------------------------


@pytest.mark.asyncio
async def test_with_timestamps_stamps_attached_rows(memory_db) -> None:
    learner, gold, _ = await _seed()

    await learner.stamped_plans().attach(gold.id)
    plan = await learner.stamped_plans().first()

    assert plan.pivot.created_at is not None
    assert plan.pivot.updated_at is not None


@pytest.mark.asyncio
async def test_without_with_timestamps_no_stamps_are_written(memory_db) -> None:
    learner, gold, _ = await _seed()

    await learner.plans().attach(gold.id)
    rows = await learner.plans()._pivot_query().get_raw()

    assert rows[0]["created_at"] is None


@pytest.mark.asyncio
async def test_updating_a_pivot_touches_its_updated_at(memory_db) -> None:
    learner, gold, _ = await _seed()
    relation_ = learner.stamped_plans()
    await relation_.attach(gold.id)
    await relation_._pivot_query().update({"updated_at": None})

    await relation_.update_existing_pivot(gold.id, {"tier": "gold"})
    rows = await relation_._pivot_query().get_raw()

    assert rows[0]["updated_at"] is not None


@pytest.mark.asyncio
async def test_update_existing_pivot_with_nothing_to_write_is_a_no_op(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.plans().attach(gold.id)

    assert await learner.plans().update_existing_pivot(gold.id, {}) == 0


# --- pivot filtering and ordering ---------------------------------------------


@pytest.mark.asyncio
async def test_where_pivot_variants_filter_the_intermediate_table(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id, {"tier": "gold"})
    await learner.plans().attach(basic.id)

    in_ = await learner.plans().where_pivot_in("tier", ["gold"]).get()
    not_in = await learner.plans().where_pivot_not_in("tier", ["gold"]).get()
    null = await learner.plans().where_pivot_null("tier").get()
    not_null = await learner.plans().where_pivot_not_null("tier").get()

    assert [plan.name for plan in in_] == ["Gold"]
    assert [plan.name for plan in not_in] == []
    assert [plan.name for plan in null] == ["Basic"]
    assert [plan.name for plan in not_null] == ["Gold"]


@pytest.mark.asyncio
async def test_where_pivot_between_filters_a_range(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id, {"tier": "3"})
    await learner.plans().attach(basic.id, {"tier": "9"})

    found = await learner.plans().where_pivot_between("tier", "1", "5").get()

    assert [plan.name for plan in found] == ["Gold"]


@pytest.mark.asyncio
async def test_order_by_pivot_sorts_on_an_intermediate_column(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id, {"tier": "b"})
    await learner.plans().attach(basic.id, {"tier": "a"})

    ascending = await learner.plans().order_by_pivot("tier").get()
    descending = await learner.plans().order_by_pivot("tier", "desc").get()

    assert [plan.name for plan in ascending] == ["Basic", "Gold"]
    assert [plan.name for plan in descending] == ["Gold", "Basic"]


@pytest.mark.asyncio
async def test_pivot_constraints_apply_to_eager_loads(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id, {"tier": "gold"})
    await learner.plans().attach(basic.id, {"tier": "free"})

    learners = await Learner.with_relations("gold_plans").get()

    assert [plan.name for plan in learners[0].gold_plans] == ["Gold"]


# --- attach and sync ----------------------------------------------------------


@pytest.mark.asyncio
async def test_attach_accepts_per_id_attributes(memory_db) -> None:
    learner, gold, basic = await _seed()

    await learner.plans().attach({gold.id: {"tier": "gold"}, basic.id: {"tier": "free"}})
    plans = await learner.plans().order_by_pivot("tier").get()

    assert [(plan.name, plan.pivot.tier) for plan in plans] == [
        ("Basic", "free"),
        ("Gold", "gold"),
    ]


@pytest.mark.asyncio
async def test_attaching_nothing_writes_nothing(memory_db) -> None:
    learner, _, _ = await _seed()

    assert await learner.plans().attach([]) == 0


@pytest.mark.asyncio
async def test_sync_reports_updated_rows(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id, {"tier": "free"})

    result = await learner.plans().sync({gold.id: {"tier": "gold"}, basic.id: {}})

    assert result["attached"] == [basic.id]
    assert result["updated"] == [gold.id]
    assert result["detached"] == []
    assert (await learner.plans().where_pivot("tier", "=", "gold").get())[0].name == "Gold"


@pytest.mark.asyncio
async def test_sync_without_detaching_keeps_existing_rows(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id)

    result = await learner.plans().sync_without_detaching([basic.id])

    assert result["detached"] == []
    assert len(await learner.plans().get()) == 2


# --- morph maps ---------------------------------------------------------------


class Article(Model):
    table = "articles"
    fillable = ("title",)

    @relation
    def tags(self):
        return self.morph_to_many(Tag, "taggable")

    @relation
    def marks(self):
        return self.morph_many(Mark, "markable")


class Tag(Model):
    table = "tags"
    fillable = ("name",)


class Mark(Model):
    table = "marks"
    fillable = ("markable_id", "markable_type", "label")

    @relation
    def markable(self):
        return self.morph_to("markable")


@pytest.fixture
def morph_registry():
    clear_morph_map()
    yield
    clear_morph_map()


async def _morph_schema() -> None:
    await Schema.create("articles", lambda t: (t.id(), t.string("title"), t.timestamps()))
    await Schema.create("tags", lambda t: (t.id(), t.string("name"), t.timestamps()))
    await Schema.create(
        "marks",
        lambda t: (
            t.id(),
            t.integer("markable_id"),
            t.string("markable_type"),
            t.string("label"),
            t.timestamps(),
        ),
    )


@pytest.mark.asyncio
async def test_morph_alias_defaults_to_the_class_name(memory_db, morph_registry) -> None:
    assert morph_alias(Article) == "Article"


@pytest.mark.asyncio
async def test_morph_map_replaces_stored_type_names(memory_db, morph_registry) -> None:
    morph_map({"article": Article})
    await _morph_schema()
    article = await Article.create(title="Hello")

    await article.marks().create({"label": "star"})
    row = (await Mark.query().get_raw())[0]

    assert row["markable_type"] == "article"


@pytest.mark.asyncio
async def test_morph_to_resolves_through_the_registered_map(memory_db, morph_registry) -> None:
    morph_map({"article": Article})
    await _morph_schema()
    article = await Article.create(title="Hello")
    await article.marks().create({"label": "star"})

    mark = await Mark.query().first()

    assert (await mark.markable().get()).title == "Hello"


@pytest.mark.asyncio
async def test_enforced_morph_maps_reject_unmapped_models(memory_db, morph_registry) -> None:
    enforce_morph_map({"article": Article})

    assert morph_alias(Article) == "article"
    with pytest.raises(LookupError, match="missing from the enforced morph map"):
        morph_alias(Tag)


@pytest.mark.asyncio
async def test_morph_map_reads_back_and_can_replace(memory_db, morph_registry) -> None:
    morph_map({"article": Article})
    morph_map({"tag": Tag})
    assert set(morph_map()) == {"article", "tag"}

    morph_map({"only": Article}, merge=False)
    assert set(morph_map()) == {"only"}


# --- touching parents ---------------------------------------------------------


@pytest.mark.asyncio
async def test_saving_a_child_touches_the_parent(memory_db) -> None:
    learner, _, _ = await _seed()
    await Learner.query().where_key(learner.id).update({"updated_at": None})

    await learner.notes().create({"body": "first"})

    refreshed = await Learner.query().find(learner.id)
    assert refreshed.get_raw_attribute("updated_at") is not None


@pytest.mark.asyncio
async def test_without_touching_suspends_the_parent_update(memory_db) -> None:
    learner, _, _ = await _seed()
    await Learner.query().where_key(learner.id).update({"updated_at": None})

    with Model.without_touching():
        await learner.notes().create({"body": "quiet"})

    refreshed = await Learner.query().find(learner.id)
    assert refreshed.get_raw_attribute("updated_at") is None


@pytest.mark.asyncio
async def test_without_touching_on_exempts_named_models(memory_db) -> None:
    learner, _, _ = await _seed()
    await Learner.query().where_key(learner.id).update({"updated_at": None})

    with Model.without_touching_on(Note):
        await learner.notes().create({"body": "quiet"})

    refreshed = await Learner.query().find(learner.id)
    assert refreshed.get_raw_attribute("updated_at") is None


@pytest.mark.asyncio
async def test_touching_a_missing_parent_is_harmless(memory_db) -> None:
    await _schema()
    orphan = Note()
    orphan.force_fill({"learner_id": 999, "body": "orphan"})

    await orphan.save()

    assert orphan.exists is True


# --- relation write helpers ---------------------------------------------------


@pytest.mark.asyncio
async def test_make_builds_an_unsaved_child(memory_db) -> None:
    learner, _, _ = await _seed()

    note = learner.notes().make({"body": "draft"})

    assert note.exists is False
    assert note.learner_id == learner.id


@pytest.mark.asyncio
async def test_make_many_builds_several(memory_db) -> None:
    learner, _, _ = await _seed()

    notes = learner.notes().make_many([{"body": "a"}, {"body": "b"}])

    assert [note.body for note in notes] == ["a", "b"]
    assert all(note.learner_id == learner.id for note in notes)


@pytest.mark.asyncio
async def test_create_quietly_skips_events(memory_db) -> None:
    learner, _, _ = await _seed()
    seen: list[str] = []
    Note.listen("created", lambda model: seen.append(model.body))

    await learner.notes().create_quietly({"body": "silent"})
    await learner.notes().create({"body": "loud"})

    assert seen == ["loud"]


@pytest.mark.asyncio
async def test_first_or_new_returns_an_unsaved_model(memory_db) -> None:
    learner, _, _ = await _seed()
    await learner.notes().create({"body": "existing"})

    found = await learner.notes().first_or_new({"body": "existing"})
    fresh = await learner.notes().first_or_new({"body": "missing"}, {"body": "missing"})

    assert found.exists is True
    assert fresh.exists is False
    assert fresh.learner_id == learner.id


@pytest.mark.asyncio
async def test_find_or_new_falls_back_to_a_new_model(memory_db) -> None:
    learner, _, _ = await _seed()
    note = await learner.notes().create({"body": "existing"})

    assert (await learner.notes().find_or_new(note.id)).body == "existing"
    assert (await learner.notes().find_or_new(999)).exists is False


@pytest.mark.asyncio
async def test_update_or_create_updates_then_creates(memory_db) -> None:
    learner, _, _ = await _seed()
    await learner.notes().create({"body": "old"})

    updated = await learner.notes().update_or_create({"body": "old"}, {"body": "new"})
    created = await learner.notes().update_or_create({"body": "fresh"})

    assert updated.body == "new"
    assert created.exists is True
    assert len(await learner.notes().get()) == 2


class LonePivot(Pivot):
    """A pivot used directly, with no relation behind it."""

    table = "learner_plan"
    primary_key = "learner_id"
    fillable = ("learner_id", "plan_id", "tier")


@pytest.mark.asyncio
async def test_a_pivot_used_without_a_relation_behaves_like_a_model(memory_db) -> None:
    learner, gold, _ = await _seed()

    row = LonePivot()
    row.force_fill({"learner_id": learner.id, "plan_id": gold.id, "tier": "gold"})
    await row.save()

    assert len(await LonePivot.query().get()) == 1

    await row.delete()
    assert await LonePivot.query().get() == []


@pytest.mark.asyncio
async def test_hydrating_a_pivot_skips_columns_that_were_not_selected(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.plans().attach(gold.id, {"tier": "gold"})

    plan = await Plan.query().find(gold.id)
    learner.plans()._hydrate_pivot(plan)

    # `tier` was never selected, so the pivot carries only the keys.
    assert plan.pivot.get_raw_attribute("tier") is None
    assert plan.pivot.plan_id == gold.id


@pytest.mark.asyncio
async def test_sync_leaves_untouched_rows_out_of_updated(memory_db) -> None:
    learner, gold, basic = await _seed()
    await learner.plans().attach(gold.id, {"tier": "gold"})

    result = await learner.plans().sync({gold.id: {}, basic.id: {}})

    assert result["attached"] == [basic.id]
    assert result["updated"] == []


@pytest.mark.asyncio
async def test_morph_to_with_no_stored_type_resolves_to_nothing(memory_db, morph_registry) -> None:
    await _morph_schema()
    await Mark.create(markable_id=1, markable_type=None, label="loose")

    mark = await Mark.query().first()

    assert await mark.markable().get() is None


@pytest.mark.asyncio
async def test_morph_enforcement_is_introspectable(memory_db, morph_registry) -> None:
    from almasix.orm.morph import morph_enforced

    assert morph_enforced() is False
    enforce_morph_map({"article": Article})
    assert morph_enforced() is True


@pytest.mark.asyncio
async def test_sync_skips_rows_that_vanished_before_the_update(memory_db) -> None:
    learner, gold, _ = await _seed()
    await learner.plans().attach(gold.id, {"tier": "free"})

    relation_ = learner.plans()

    async def vanished(identifier, attributes):
        return 0

    relation_.update_existing_pivot = vanished
    result = await relation_.sync({gold.id: {"tier": "gold"}})

    assert result["updated"] == []
