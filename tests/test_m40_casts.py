"""M40 — casting overhaul: Attribute objects, custom casts, and new built-ins."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

import pytest

from avalon.encryption.encrypter import Encrypter
from avalon.encryption.facade import Crypt
from avalon.hashing import Hash
from avalon.orm import Schema
from avalon.orm.attributes import Attribute, MethodAttribute, attribute
from avalon.orm.casts import (
    CastError,
    CastsAttributes,
    CastsInboundAttributes,
    EnumCollection,
    cast_format,
    cast_value,
    prepare_for_storage,
    resolve_cast,
    serialize_value,
    uncast_value,
)
from avalon.orm.model import Model
from tests.orm_support import memory_db  # noqa: F401 - fixture

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def _encrypter() -> Any:
    Crypt.set_encrypter(Encrypter("m40-testing-key-not-a-secret"))
    yield
    Crypt.set_encrypter(None)


class Status(str, Enum):
    ACTIVE = "active"
    OFF = "off"


class Upper(CastsAttributes):
    """A symmetric custom cast."""

    def get(self, model: Any, key: str, value: Any, attributes: Any) -> Any:
        return str(value).upper()

    def set(self, model: Any, key: str, value: Any, attributes: Any) -> Any:
        return str(value).lower()


class Coords(CastsAttributes):
    """A value-object cast spanning two columns."""

    def get(self, model: Any, key: str, value: Any, attributes: Any) -> Any:
        return (attributes.get("lat"), attributes.get("lng"))

    def set(self, model: Any, key: str, value: Any, attributes: Any) -> Any:
        lat, lng = value
        return {"lat": lat, "lng": lng}


class Tagged(CastsInboundAttributes):
    def set(self, model: Any, key: str, value: Any, attributes: Any) -> Any:
        return f"in:{value}"


class Castable:
    """Laravel's ``Castable`` — a class that names its own cast."""

    @classmethod
    def cast_using(cls) -> type[CastsAttributes]:
        return Upper


class CastableInstance:
    @classmethod
    def cast_using(cls) -> CastsAttributes:
        return Upper()


# --- Attribute objects ------------------------------------------------------


class Person(Model):
    table = "people"
    fillable = ("name", "email", "first", "last")

    name = Attribute(
        get=lambda value: (value or "").title(),
        set=lambda value: str(value).strip(),
    )
    email = Attribute(get=lambda value, attributes: f"{value} <{attributes.get('name')}>")

    @attribute
    def full_name(self) -> Attribute:
        return Attribute(
            get=lambda _value, attributes: f"{attributes.get('first')} {attributes.get('last')}"
        )


async def test_attribute_object_wraps_get_and_set() -> None:
    person = Person(name="  ada lovelace ")
    assert person.get_raw_attribute("name") == "ada lovelace"
    assert person.name == "Ada Lovelace"


async def test_attribute_get_may_take_the_attribute_mapping() -> None:
    person = Person(name="ada", email="ada@example.test")
    assert person.email == "ada@example.test <ada>"


async def test_attribute_method_style_matches_laravel() -> None:
    person = Person(first="Ada", last="Lovelace")
    assert person.full_name == "Ada Lovelace"
    assert isinstance(type(person).__dict__["full_name"], MethodAttribute)


async def test_attribute_assignment_routes_through_the_setter() -> None:
    person = Person()
    person.name = "  grace hopper  "
    assert person.get_raw_attribute("name") == "grace hopper"


async def test_attribute_on_the_class_returns_the_descriptor() -> None:
    assert isinstance(Person.__dict__["name"], Attribute)
    assert Person.name is Person.__dict__["name"]


async def test_attribute_make_is_the_constructor() -> None:
    made = Attribute.make(get=lambda value: value, cache=True)
    assert made.cache is True
    assert Attribute(get=lambda value: value).with_caching().cache is True


async def test_attribute_caches_when_asked() -> None:
    calls: list[int] = []

    class Cached(Model):
        table = "cached"
        fillable = ("value",)
        doubled = Attribute(get=lambda value: calls.append(1) or value, cache=True)

    model = Cached()
    model._attributes["doubled"] = 2
    assert model.doubled == 2
    assert model.doubled == 2
    assert len(calls) == 1

    model.doubled = 5  # a write clears the cached read
    assert len(calls) == 1


async def test_attribute_setter_may_write_several_columns() -> None:
    class Point(Model):
        table = "points"
        fillable = ("position",)
        position = Attribute(
            get=lambda _v, attributes: (attributes.get("x"), attributes.get("y")),
            set=lambda value: {"x": value[0], "y": value[1]},
        )

    model = Point(position=(3, 4))
    assert model.get_raw_attribute("x") == 3
    assert model.get_raw_attribute("y") == 4
    assert model.position == (3, 4)


async def test_attribute_without_a_getter_returns_the_raw_value() -> None:
    class Plain(Model):
        table = "plain"
        fillable = ("code",)
        code = Attribute(set=lambda value: str(value).strip())

    model = Plain(code=" x ")
    assert model.code == "x"


async def test_attribute_callbacks_may_take_no_arguments() -> None:
    class Fixed(Model):
        table = "fixed"
        stamp = Attribute(get=lambda: "always")

    assert Fixed().stamp == "always"


async def test_attribute_methods_must_return_an_attribute() -> None:
    class Broken(Model):
        table = "broken"

        @attribute
        def oops(self) -> Attribute:
            return "not an attribute"  # type: ignore[return-value]

    with pytest.raises(TypeError, match="must return an Attribute"):
        _ = Broken().oops


async def test_attribute_casters_are_inherited() -> None:
    class Child(Person):
        table = "children"

    child = Child(name="ada")
    assert child.name == "Ada"


# --- casts() and cast merging ----------------------------------------------


async def test_casts_may_be_declared_as_a_classmethod() -> None:
    class Flagged(Model):
        table = "flagged"
        fillable = ("flag",)

        @classmethod
        def casts(cls) -> dict[str, Any]:
            return {"flag": "bool"}

    model = Flagged(flag="yes")
    assert model.flag is True
    assert Flagged.class_casts() == {"flag": "bool"}


async def test_casts_may_be_declared_as_a_plain_method() -> None:
    class Plainly(Model):
        table = "plainly"
        fillable = ("total",)

        def casts(self) -> dict[str, Any]:
            return {"total": "int"}

    assert Plainly(total="7").total == 7


async def test_merge_casts_and_has_cast_are_per_instance() -> None:
    class Loose(Model):
        table = "loose"
        fillable = ("value",)

    first = Loose(value="3")
    second = Loose(value="3")
    first.merge_casts({"value": "int"})

    assert first.has_cast("value") is True
    assert second.has_cast("value") is False
    assert first.get_casts() == {"value": "int"}
    assert Loose.class_casts() == {}


async def test_with_casts_applies_casts_for_one_query(memory_db) -> None:  # noqa: ANN001
    class Reading(Model):
        table = "readings"
        fillable = ("amount",)

    await Schema.create(
        "readings", lambda table: (table.id(), table.string("amount"), table.timestamps())
    )
    await Reading.create(amount="42")

    plain = await Reading.first()
    assert plain is not None
    assert plain.amount == "42"

    cast = await Reading.query().with_casts({"amount": "int"}).first()
    assert cast is not None
    assert cast.amount == 42
    assert cast.get_casts() == {"amount": "int"}

    # The cast rides along on clones.
    chained = await Reading.query().with_casts({"amount": "int"}).where("id", ">", 0).first()
    assert chained is not None
    assert chained.amount == 42


# --- new built-in casts -----------------------------------------------------


class Vault(Model):
    table = "vaults"
    fillable = ("token", "payload", "password", "status", "labels", "amount")
    casts = {
        "token": "encrypted",
        "payload": "encrypted:array",
        "password": "hashed",
        "status": Status,
        "labels": EnumCollection.of(Status),
        "amount": "decimal:2",
    }


async def test_encrypted_cast_round_trips() -> None:
    vault = Vault(token="s3cret")
    stored = vault.get_raw_attribute("token")
    assert stored != "s3cret"
    assert vault.token == "s3cret"
    assert Crypt.decrypt_string(stored) == "s3cret"


async def test_encrypted_array_cast_round_trips() -> None:
    vault = Vault(payload={"pin": 1234})
    assert vault.payload == {"pin": 1234}
    assert "1234" not in vault.get_raw_attribute("payload")


async def test_encrypted_array_cast_accepts_a_json_string() -> None:
    vault = Vault(payload=json.dumps({"pin": 1}))
    assert vault.payload == {"pin": 1}


async def test_encrypted_cast_reports_undecodable_payloads() -> None:
    with pytest.raises(CastError, match="Cannot decode encrypted"):
        cast_value(Crypt.encrypt_string("not json"), "encrypted:array")


async def test_hashed_cast_hashes_on_write_and_never_rehashes() -> None:
    vault = Vault(password="hunter2")
    digest = vault.get_raw_attribute("password")
    assert digest != "hunter2"
    assert Hash.check("hunter2", digest)

    vault.password = digest
    assert vault.get_raw_attribute("password") == digest
    assert vault.password == digest


async def test_enum_cast_and_enum_collection_cast() -> None:
    vault = Vault(status="active", labels=[Status.ACTIVE, "off"])
    assert vault.status is Status.ACTIVE
    assert vault.labels == [Status.ACTIVE, Status.OFF]
    assert json.loads(vault.get_raw_attribute("labels")) == ["active", "off"]


async def test_enum_collection_handles_none_and_raw_json() -> None:
    caster = EnumCollection.of(Status)
    assert caster.get(None, "labels", None, {}) is None
    assert caster.set(None, "labels", None, {}) is None
    assert caster.get(None, "labels", ["active"], {}) == [Status.ACTIVE]
    assert caster.get(None, "labels", [Status.OFF], {}) == [Status.OFF]
    assert caster.set(None, "labels", '["active"]', {}) == '["active"]'


async def test_enum_collection_rejects_non_sequences() -> None:
    with pytest.raises(CastError, match="expects a sequence"):
        EnumCollection.of(Status).set(None, "labels", 7, {})


async def test_decimal_cast_quantizes() -> None:
    assert Vault(amount="10.005").amount == Decimal("10.00")
    assert cast_value("1.5", "decimal") == Decimal("1.5")


async def test_immutable_date_casts_are_aliases() -> None:
    # Python's date/datetime are already immutable, so these are aliases.
    assert cast_value("2026-09-08T01:02:03", "immutable_datetime") == datetime(2026, 9, 8, 1, 2, 3)
    assert cast_value("2026-09-08", "immutable_date") == date(2026, 9, 8)


# --- date serialization -----------------------------------------------------


async def test_cast_format_drives_serialization() -> None:
    class Event(Model):
        table = "events"
        fillable = ("day", "at")
        casts = {"day": "date:%d/%m/%Y", "at": "datetime:%Y-%m-%d %H:%M"}

    event = Event(day="1815-12-10", at="2026-09-08T01:02:03")
    data = event.to_dict()
    assert data["day"] == "10/12/1815"
    assert data["at"] == "2026-09-08 01:02"


async def test_date_format_attribute_sets_the_default() -> None:
    class Dated(Model):
        table = "dated"
        fillable = ("at",)
        casts = {"at": "datetime"}
        date_format = "%Y-%m-%d"

    assert Dated(at="2026-09-08T01:02:03").to_dict()["at"] == "2026-09-08"


async def test_serialize_date_may_be_overridden() -> None:
    class Custom(Model):
        table = "custom"
        fillable = ("at",)
        casts = {"at": "date"}

        def serialize_date(self, value: date) -> str:
            return f"day {value.day}"

    assert Custom(at="2026-09-08").to_dict()["at"] == "day 8"


async def test_dates_serialize_to_iso_by_default() -> None:
    class Basic(Model):
        table = "basic"
        fillable = ("at",)
        casts = {"at": "datetime"}

    assert Basic(at="2026-09-08T01:02:03").to_dict()["at"] == "2026-09-08T01:02:03"


async def test_cast_format_reads_only_date_casts() -> None:
    assert cast_format("date:%Y") == "%Y"
    assert cast_format("datetime") is None
    assert cast_format("decimal:2") is None
    assert cast_format(Status) is None
    assert cast_format(Upper()) is None


# --- custom cast classes ----------------------------------------------------


async def test_custom_cast_class_transforms_both_directions() -> None:
    class Coded(Model):
        table = "coded"
        fillable = ("code",)
        casts = {"code": Upper}

    model = Coded(code="AbC")
    assert model.get_raw_attribute("code") == "abc"
    assert model.code == "ABC"


async def test_custom_cast_may_be_an_instance() -> None:
    class Coded(Model):
        table = "coded2"
        fillable = ("code",)
        casts = {"code": Upper()}

    assert Coded(code="x").code == "X"


async def test_value_object_cast_spans_columns() -> None:
    class Place(Model):
        table = "places"
        fillable = ("point",)
        casts = {"point": Coords}

    place = Place(point=(1.5, 2.5))
    assert place.get_raw_attribute("lat") == 1.5
    assert place.get_raw_attribute("lng") == 2.5
    assert place.point == (1.5, 2.5)


async def test_inbound_only_cast_passes_reads_through() -> None:
    class Noted(Model):
        table = "noted"
        fillable = ("note",)
        casts = {"note": Tagged}

    model = Noted(note="hello")
    assert model.get_raw_attribute("note") == "in:hello"
    assert model.note == "in:hello"


async def test_castable_classes_name_their_own_cast() -> None:
    class Owned(Model):
        table = "owned"
        fillable = ("code", "other")
        casts = {"code": Castable, "other": CastableInstance}

    model = Owned(code="ab", other="cd")
    assert model.code == "AB"
    assert model.other == "CD"


async def test_resolve_cast_passes_unknown_declarations_through() -> None:
    assert resolve_cast("int") == "int"
    assert resolve_cast(Status) is Status
    assert isinstance(resolve_cast(Upper), Upper)
    assert isinstance(resolve_cast(Upper()), Upper)
    assert resolve_cast(dict) is dict


async def test_class_casts_are_left_to_the_model_in_the_helpers() -> None:
    caster = Upper()
    assert cast_value("x", caster) == "x"
    assert uncast_value("x", caster) == "x"


# --- write preparation ------------------------------------------------------


async def test_prepare_for_storage_round_trips_symmetric_casts() -> None:
    assert prepare_for_storage("yes", "bool") is True
    assert prepare_for_storage({"a": 1}, "json") == '{"a": 1}'
    assert prepare_for_storage("1.005", "decimal:2") == "1.00"


async def test_prepare_for_storage_only_writes_one_way_casts() -> None:
    stored = prepare_for_storage("s3cret", "encrypted")
    assert Crypt.decrypt_string(stored) == "s3cret"
    assert Hash.is_hashed(prepare_for_storage("pw", "hashed"))


async def test_prepare_for_storage_defers_class_and_enum_casts() -> None:
    assert prepare_for_storage(Status.ACTIVE, Status) == "active"
    assert prepare_for_storage("x", Upper()) == "x"


async def test_none_is_never_cast() -> None:
    assert cast_value(None, "int") is None
    assert uncast_value(None, "int") is None
    assert prepare_for_storage(None, "encrypted") is None


# --- serialize_value --------------------------------------------------------


async def test_serialize_value_handles_every_shape() -> None:
    assert serialize_value(Status.ACTIVE) == "active"
    assert serialize_value(Decimal("1.50")) == 1.5
    assert serialize_value(datetime(2026, 9, 8, 1, 2)) == "2026-09-08T01:02:00"
    assert serialize_value(date(2026, 9, 8)) == "2026-09-08"
    assert serialize_value(time(1, 2)) == "01:02:00"
    assert serialize_value({"at": date(2026, 9, 8)}) == {"at": "2026-09-08"}
    assert serialize_value([date(2026, 9, 8)]) == ["2026-09-08"]
    assert serialize_value((1, 2)) == [1, 2]
    assert serialize_value("plain") == "plain"


async def test_serialize_value_applies_a_cast_format_to_times() -> None:
    assert serialize_value(date(2026, 9, 8), "date:%Y") == "2026"
    assert serialize_value("text", "date:%Y") == "text"


# --- unchanged behavior -----------------------------------------------------


async def test_scalar_casts_still_work() -> None:
    class Mixed(Model):
        table = "mixed"
        fillable = ("i", "f", "s", "b", "j", "t", "ts")
        casts = {
            "i": "int",
            "f": "float",
            "s": "string",
            "b": "bool",
            "j": "json",
            "t": "time",
            "ts": "timestamp",
        }

    model = Mixed(i="3", f="1.5", s=7, b="off", j=[1, 2], t="01:02:03", ts="2026-09-08T00:00:00")
    assert model.i == 3
    assert model.f == 1.5
    assert model.s == "7"
    assert model.b is False
    assert model.j == [1, 2]
    assert model.t == time(1, 2, 3)
    assert isinstance(model.ts, int)


async def test_bad_values_raise_cast_errors() -> None:
    with pytest.raises(CastError, match="to json"):
        cast_value("{not json", "json")
    with pytest.raises(CastError, match="to datetime"):
        cast_value("not a date", "datetime")


async def test_magic_accessors_and_mutators_still_win_where_declared() -> None:
    class Legacy(Model):
        table = "legacy"
        fillable = ("title",)

        def get_title_attribute(self, value: Any) -> Any:
            return f"<{value}>"

        def set_title_attribute(self, value: Any) -> Any:
            return str(value).strip()

    model = Legacy(title="  hi  ")
    assert model.get_raw_attribute("title") == "hi"
    assert model.title == "<hi>"


# --- edges ------------------------------------------------------------------


async def test_arity_falls_back_when_a_signature_is_unavailable() -> None:
    from avalon.orm.attributes import _arity

    assert _arity(object()) == 2  # not introspectable
    assert _arity(lambda *args: args) == 2  # *args accepts anything
    assert _arity(lambda: None) == 0
    assert _arity(lambda value, attributes, extra=None: None) == 2
    assert _arity(lambda value, *, extra=None: None) == 1  # keyword-only is skipped


async def test_method_attribute_supports_a_setter() -> None:
    class Slugged(Model):
        table = "slugged"
        fillable = ("slug",)

        @attribute
        def slug(self) -> Attribute:
            return Attribute(set=lambda value: str(value).replace(" ", "-"))

    model = Slugged(slug="hello world")
    assert model.get_raw_attribute("slug") == "hello-world"


async def test_custom_cast_base_class_demands_an_implementation() -> None:
    caster = CastsAttributes()
    with pytest.raises(NotImplementedError):
        caster.get(None, "k", "v", {})
    with pytest.raises(NotImplementedError):
        caster.set(None, "k", "v", {})


async def test_a_declared_cast_on_a_missing_key_returns_the_default() -> None:
    class Sparse(Model):
        table = "sparse"
        casts = {"absent": "int"}

    model = Sparse()
    assert model.get_attribute("absent") is None
    assert model.get_attribute("absent", 7) == 7
