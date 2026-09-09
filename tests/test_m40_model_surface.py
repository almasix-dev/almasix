"""M40 — UUID/ULID keys, strictness, quiet writes, pruning, and chunking."""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest

from almasix.orm import (
    DiscardedAttributeError,
    HasUlids,
    HasUuids,
    MassAssignmentError,
    MassPrunable,
    MissingAttributeError,
    Model,
    Prunable,
    Schema,
    SoftDeletes,
    ordered_uuid,
    ulid,
)
from almasix.orm import model as model_mod
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


class Note(Model):
    table = "notes"
    fillable = ("title", "body")


class UuidDoc(HasUuids, Model):
    table = "uuid_docs"
    fillable = ("title",)


class UlidDoc(HasUlids, Model):
    table = "ulid_docs"
    fillable = ("title",)


class TwoIds(HasUuids, Model):
    table = "two_ids"
    fillable = ("title",)

    def unique_ids(self) -> tuple[str, ...]:
        return ("id", "public_id")


@pytest.fixture(autouse=True)
def _reset_global_state() -> Any:
    yield
    Model.should_be_strict(False)
    Model.reguard()
    model_mod._EVENTS_DISABLED = False


@pytest.fixture
async def schema(memory_db) -> None:
    await Schema.create(
        "notes",
        lambda table: (
            table.id(),
            table.string("title"),
            table.string("body").nullable(),
            table.timestamps(),
        ),
    )
    for name, _model in (("uuid_docs", UuidDoc), ("ulid_docs", UlidDoc)):
        await Schema.create(
            name,
            lambda table: (
                table.string("id").primary(),
                table.string("title"),
                table.timestamps(),
            ),
        )
    await Schema.create(
        "two_ids",
        lambda table: (
            table.string("id").primary(),
            table.string("public_id").nullable(),
            table.string("title"),
            table.timestamps(),
        ),
    )


# --- UUID / ULID keys -------------------------------------------------------


async def test_ordered_uuid_is_a_version_7_uuid() -> None:
    first = ordered_uuid()
    second = ordered_uuid()

    assert first.version == 7
    assert first.variant == uuid.RFC_4122
    assert first != second
    # Only the 48-bit millisecond prefix is ordered; the rest is random.
    assert second.hex[:8] >= first.hex[:8]


async def test_ulid_is_26_crockford_characters() -> None:
    value = ulid()
    assert len(value) == 26
    assert re.fullmatch(r"[0-9ABCDEFGHJKMNPQRSTVWXYZ]{26}", value)
    assert ulid() != value
    # Only the 48-bit time prefix is ordered; the rest is random.
    assert ulid()[:8] >= value[:8]


async def test_uuid_keys_are_filled_on_insert(schema) -> None:
    doc = await UuidDoc.create(title="On Computing")

    assert isinstance(doc.id, str)
    assert uuid.UUID(doc.id).version == 7
    assert UuidDoc.incrementing is False
    assert UuidDoc.key_type == "string"

    found = await UuidDoc.find(doc.id)
    assert found is not None
    assert found.title == "On Computing"


async def test_ulid_keys_are_filled_on_insert(schema) -> None:
    doc = await UlidDoc.create(title="On Computing")
    assert len(doc.id) == 26
    assert await UlidDoc.find(doc.id) is not None


async def test_an_explicit_key_is_respected(schema) -> None:
    doc = UuidDoc(title="Fixed")
    doc.id = "fixed-key"
    await doc.save()
    assert doc.id == "fixed-key"


async def test_unique_ids_may_cover_several_columns(schema) -> None:
    row = await TwoIds.create(title="Both")
    assert uuid.UUID(row.id).version == 7
    assert uuid.UUID(row.public_id).version == 7
    assert row.id != row.public_id


async def test_integer_keys_are_untouched(schema) -> None:
    note = await Note.create(title="Plain")
    assert note.id == 1


# --- strictness -------------------------------------------------------------


async def test_discarded_attributes_may_raise() -> None:
    Model.prevent_silently_discarding_attributes()

    with pytest.raises(DiscardedAttributeError, match=r"Add \[extra\] to fillable"):
        Note(title="ok", extra="dropped")


async def test_discarded_attributes_are_dropped_by_default() -> None:
    note = Note(title="ok", extra="dropped")
    assert note.title == "ok"
    assert note.get_raw_attribute("extra") is None


async def test_missing_attributes_may_raise(schema) -> None:
    await Note.create(title="Partial", body="text")
    Model.prevent_accessing_missing_attributes()

    partial = await Note.query().select("id", "title").first()
    assert partial is not None
    assert partial.title == "Partial"

    with pytest.raises(MissingAttributeError, match="Note.body was not retrieved"):
        _ = partial.body


async def test_get_attribute_raises_in_strict_mode(schema) -> None:
    await Note.create(title="Partial", body="text")
    Model.prevent_accessing_missing_attributes()

    partial = await Note.query().select("id", "title").first()
    assert partial is not None
    with pytest.raises(MissingAttributeError, match="Note.body was not retrieved"):
        partial.get_attribute("body")


async def test_unique_string_id_base_demands_a_generator() -> None:
    from almasix.orm import HasUniqueStringIds

    class Bare(HasUniqueStringIds, Model):
        table = "notes"

    with pytest.raises(NotImplementedError):
        Bare().new_unique_id()


async def test_chunk_by_id_handles_an_empty_table(schema) -> None:
    seen: list[Any] = []
    assert await Note.query().chunk_by_id(3, lambda rows: seen.extend(rows)) is True
    assert seen == []


async def test_each_by_id_awaits_async_callbacks(many) -> None:
    seen: list[str] = []

    async def visit(row: Any) -> None:
        seen.append(row.title)

    assert await Note.query().each_by_id(visit, size=3) is True
    assert len(seen) == 7


async def test_missing_attributes_stay_lenient_with_a_default(schema) -> None:
    await Note.create(title="Partial")
    Model.prevent_accessing_missing_attributes()

    partial = await Note.query().select("id").first()
    assert partial is not None
    assert partial.get_attribute("body", "fallback") == "fallback"


async def test_strictness_does_not_apply_to_unsaved_models() -> None:
    Model.should_be_strict()
    # A model you are building has nothing loaded yet, so reads stay lenient.
    assert Note().get_attribute("body") is None


async def test_should_be_strict_toggles_both_checks() -> None:
    Model.should_be_strict()
    assert model_mod._STRICT_DISCARDING is True
    assert model_mod._STRICT_MISSING is True

    Model.should_be_strict(False)
    assert model_mod._STRICT_DISCARDING is False
    assert model_mod._STRICT_MISSING is False


# --- unguarding -------------------------------------------------------------


class Locked(Model):
    table = "notes"


async def test_guarded_models_raise_by_default() -> None:
    with pytest.raises(MassAssignmentError):
        Locked(title="nope")


async def test_unguarded_allows_mass_assignment() -> None:
    with Model.unguarded():
        model = Locked(title="allowed")
        assert model.title == "allowed"
        assert Locked.is_fillable("anything") is True

    with pytest.raises(MassAssignmentError):
        Locked(title="nope")


async def test_unguard_and_reguard_are_explicit() -> None:
    Model.unguard()
    assert Locked(title="allowed").title == "allowed"

    Model.reguard()
    with pytest.raises(MassAssignmentError):
        Locked(title="nope")


async def test_unguarded_restores_a_nested_state() -> None:
    Model.unguard()
    with Model.unguarded():
        pass
    assert model_mod._UNGUARDED is True


# --- timestamps -------------------------------------------------------------


async def test_without_timestamps_suspends_them(schema) -> None:
    note = await Note.create(title="Stamped")
    original = note.get_raw_attribute("updated_at")

    with Note.without_timestamps():
        note.title = "Changed"
        await note.save()

    assert note.get_raw_attribute("updated_at") == original
    assert note.title == "Changed"

    later = original.replace(year=original.year + 1)
    note._fresh_timestamp = lambda: later  # type: ignore[method-assign]
    note.title = "Changed again"
    await note.save()
    assert note.get_raw_attribute("updated_at") == later


async def test_without_timestamps_also_stops_touch(schema) -> None:
    note = await Note.create(title="Stamped")
    with Note.without_timestamps():
        assert await note.touch() is False


async def test_without_timestamps_is_scoped_to_the_model(schema) -> None:
    note = await Note.create(title="Stamped")
    with UuidDoc.without_timestamps():
        note.title = "Changed"
        await note.save()
    assert note.get_raw_attribute("updated_at") is not None


# --- quiet writes -----------------------------------------------------------


class Watched(SoftDeletes, Model):
    table = "watched"
    fillable = ("title",)


@pytest.fixture
async def watched_schema(memory_db) -> None:
    await Schema.create(
        "watched",
        lambda table: (
            table.id(),
            table.string("title"),
            table.soft_deletes(),
            table.timestamps(),
        ),
    )
    Watched._events = {event: [] for event in Watched._events}


async def test_save_quietly_fires_no_events(watched_schema) -> None:
    seen: list[str] = []
    for event in ("saving", "saved", "creating", "created", "updating", "updated"):
        Watched.listen(event, lambda _model, name=event: seen.append(name))

    model = Watched(title="Quiet")
    assert await model.save_quietly() is True
    assert seen == []

    model.title = "Loud"
    assert await model.save() is True
    assert "saved" in seen


async def test_delete_and_restore_quietly_fire_no_events(watched_schema) -> None:
    seen: list[str] = []
    for event in ("deleting", "deleted", "restoring", "restored"):
        Watched.listen(event, lambda _model, name=event: seen.append(name))

    model = await Watched.create(title="Quiet")
    assert await model.delete_quietly() is True
    assert await model.restore_quietly() is True
    assert seen == []

    await model.delete()
    assert "deleted" in seen


async def test_force_delete_quietly_fires_no_events(watched_schema) -> None:
    seen: list[str] = []
    Watched.listen("deleted", lambda _model: seen.append("deleted"))

    model = await Watched.create(title="Quiet")
    assert await model.force_delete_quietly() is True
    assert seen == []


async def test_muting_is_restored_even_when_a_write_fails(watched_schema) -> None:
    model = await Watched.create(title="Quiet")

    async def boom(_model: Any) -> None:
        raise RuntimeError("listener exploded")

    Watched.listen("saved", boom)
    with pytest.raises(RuntimeError):
        model.title = "Changed"
        await model.save()
    assert model._muted is False


async def test_without_events_mutes_a_block(watched_schema) -> None:
    seen: list[str] = []
    Watched.listen("created", lambda _model: seen.append("created"))

    with Model.without_events():
        await Watched.create(title="Silent")
    assert seen == []

    await Watched.create(title="Heard")
    assert seen == ["created"]


async def test_without_trashed_states_the_default(watched_schema) -> None:
    model = await Watched.create(title="Here")
    await model.delete()

    assert await Watched.without_trashed().count() == 0
    assert await Watched.with_trashed().count() == 1


# --- pruning ----------------------------------------------------------------


class Stale(Prunable, Model):
    table = "notes"
    fillable = ("title", "body")
    pruned_hooks: list[str] = []

    def prunable(self) -> Any:
        return self.query().where("title", "like", "old%")

    async def pruning(self) -> None:
        type(self).pruned_hooks.append(self.title)


class MassStale(MassPrunable, Model):
    table = "notes"
    fillable = ("title", "body")

    def prunable(self) -> Any:
        return self.query().where("title", "like", "old%")


class NotDeclared(Prunable, Model):
    table = "notes"


async def test_prunable_deletes_and_calls_the_hook(schema) -> None:
    Stale.pruned_hooks.clear()
    for title in ("old-1", "old-2", "keep"):
        await Stale.create(title=title)

    assert await Stale.prune() == 2
    assert sorted(Stale.pruned_hooks) == ["old-1", "old-2"]
    assert await Stale.query().count() == 1


async def test_prunable_walks_several_chunks(schema) -> None:
    Stale.pruned_hooks.clear()
    for index in range(5):
        await Stale.create(title=f"old-{index}")

    assert await Stale.prune(chunk_size=2) == 5
    assert await Stale.query().count() == 0


async def test_mass_prunable_deletes_without_loading(schema) -> None:
    for title in ("old-1", "old-2", "keep"):
        await MassStale.create(title=title)

    assert await MassStale.prune() == 2
    assert await MassStale.query().count() == 1


async def test_mass_prunable_walks_several_chunks(schema) -> None:
    for index in range(5):
        await MassStale.create(title=f"old-{index}")

    assert await MassStale.prune(chunk_size=2) == 5
    assert await MassStale.query().count() == 0


async def test_prune_returns_zero_when_nothing_matches(schema) -> None:
    await Stale.create(title="keep")
    assert await Stale.prune() == 0
    assert await MassStale.prune() == 0


async def test_a_prunable_model_must_declare_prunable() -> None:
    with pytest.raises(NotImplementedError, match="does not implement prunable"):
        NotDeclared.prunable_query()


# --- chunking and cursors ---------------------------------------------------


@pytest.fixture
async def many(schema) -> None:
    for index in range(1, 8):
        await Note.create(title=f"note-{index}")


async def test_chunk_by_id_walks_every_row(many) -> None:
    seen: list[str] = []
    assert await Note.query().chunk_by_id(3, lambda rows: seen.extend(r.title for r in rows))
    assert seen == [f"note-{index}" for index in range(1, 8)]


async def test_chunk_by_id_stops_when_the_callback_returns_false(many) -> None:
    seen: list[str] = []

    def take_one(rows: Any) -> bool:
        seen.extend(row.title for row in rows)
        return False

    assert await Note.query().chunk_by_id(2, take_one) is False
    assert seen == ["note-1", "note-2"]


async def test_chunk_by_id_does_not_skip_rows_the_callback_updates(many) -> None:
    # Offset paging loses rows here; keyset paging does not.
    seen: list[str] = []

    async def rename(rows: Any) -> None:
        for row in rows:
            seen.append(row.title)
            row.title = f"seen-{row.id}"
            await row.save()

    await Note.query().chunk_by_id(2, rename)
    assert len(seen) == 7


async def test_chunk_by_id_accepts_an_explicit_column(many) -> None:
    seen: list[str] = []
    await Note.query().chunk_by_id(3, lambda rows: seen.extend(r.title for r in rows), "id")
    assert len(seen) == 7


async def test_each_by_id_visits_one_row_at_a_time(many) -> None:
    seen: list[str] = []
    assert await Note.query().each_by_id(lambda row: seen.append(row.title), size=2)
    assert len(seen) == 7


async def test_each_by_id_stops_on_false(many) -> None:
    seen: list[str] = []

    def stop(row: Any) -> bool:
        seen.append(row.title)
        return False

    assert await Note.query().each_by_id(stop, size=3) is False
    assert seen == ["note-1"]


async def test_lazy_yields_every_row(many) -> None:
    seen = [row.title async for row in Note.query().order_by("id").lazy(size=3)]
    assert seen == [f"note-{index}" for index in range(1, 8)]


async def test_lazy_stops_cleanly_on_an_empty_table(schema) -> None:
    assert [row async for row in Note.query().lazy()] == []


async def test_lazy_by_id_pages_by_key(many) -> None:
    seen = [row.title async for row in Note.query().lazy_by_id(size=2)]
    assert seen == [f"note-{index}" for index in range(1, 8)]


async def test_lazy_by_id_handles_an_empty_table(schema) -> None:
    assert [row async for row in Note.query().lazy_by_id()] == []


async def test_lazy_by_id_accepts_an_explicit_column(many) -> None:
    seen = [row.title async for row in Note.query().lazy_by_id(size=3, column="id")]
    assert len(seen) == 7


async def test_cursor_streams_models(many) -> None:
    seen = [row.title async for row in Note.query().order_by("id").cursor()]
    assert seen == [f"note-{index}" for index in range(1, 8)]


async def test_cursor_streams_plain_rows_without_a_model(many) -> None:
    from almasix.orm import DB

    rows = [row async for row in DB.table("notes").order_by("id").cursor()]
    assert [row["title"] for row in rows] == [f"note-{index}" for index in range(1, 8)]


async def test_cursor_applies_query_time_casts(many) -> None:
    rows = [row async for row in Note.query().with_casts({"title": "string"}).cursor()]
    assert all(isinstance(row.title, str) for row in rows)


async def test_keyset_paging_falls_back_to_id_without_a_model(many) -> None:
    from almasix.orm import DB

    seen: list[Any] = []
    await DB.table("notes").chunk_by_id(3, lambda rows: seen.extend(rows))
    assert len(seen) == 7
