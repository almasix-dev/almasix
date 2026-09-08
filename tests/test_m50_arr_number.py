"""M50 part 1 — the Arr and Number gaps."""

from __future__ import annotations

import pytest

from avalon.support import Arr, Number, data_get, data_set
from avalon.support.collection import ItemNotFoundError, MultipleItemsFoundError


@pytest.fixture
def config() -> dict:
    return {
        "name": "Joe",
        "languages": ["python", "sql"],
        "available": True,
        "age": 30,
        "rate": 1.5,
    }


# --- typed reads --------------------------------------------------------------


def test_typed_reads_return_the_value(config: dict) -> None:
    assert Arr.array(config, "languages") == ["python", "sql"]
    assert Arr.boolean(config, "available") is True
    assert Arr.integer(config, "age") == 30
    assert Arr.float(config, "rate") == 1.5
    assert Arr.string(config, "name") == "Joe"


def test_typed_reads_raise_on_the_wrong_type(config: dict) -> None:
    with pytest.raises(TypeError, match="not a list"):
        Arr.array(config, "name")
    with pytest.raises(TypeError, match="not a boolean"):
        Arr.boolean(config, "age")
    with pytest.raises(TypeError, match="not a string"):
        Arr.string(config, "age")
    with pytest.raises(TypeError, match="not a float"):
        Arr.float(config, "age")


def test_a_boolean_is_not_an_integer(config: dict) -> None:
    """Python's bool subclasses int, which would otherwise slip through."""
    with pytest.raises(TypeError, match="not an integer"):
        Arr.integer(config, "available")


def test_typed_reads_use_dot_notation() -> None:
    assert Arr.string({"user": {"name": "Ada"}}, "user.name") == "Ada"


# --- from ---------------------------------------------------------------------


def test_from_converts_what_it_is_given() -> None:
    assert Arr.from_({"a": 1}) == {"a": 1}
    assert Arr.from_([1, 2]) == [1, 2]
    assert Arr.from_((1, 2)) == [1, 2]
    assert Arr.from_(None) == []
    assert Arr.from_("ada") == ["ada"]


def test_from_uses_a_conversion_method_when_there_is_one() -> None:
    from avalon.support import collect

    assert Arr.from_(collect([1, 2])) == [1, 2]

    class Row:
        def to_dict(self):
            return {"id": 1}

    assert Arr.from_(Row()) == {"id": 1}


def test_from_falls_back_to_an_objects_attributes() -> None:
    class Point:
        def __init__(self) -> None:
            self.x = 1
            self.y = 2

    assert Arr.from_(Point()) == {"x": 1, "y": 2}


def test_from_is_also_spelled_the_laravel_way() -> None:
    assert getattr(Arr, "from")([1]) == [1]


# --- predicates and selection -------------------------------------------------


def test_has_all_requires_every_key(config: dict) -> None:
    assert Arr.has_all(config, ["name", "age"]) is True
    assert Arr.has_all(config, ["name", "missing"]) is False
    assert Arr.has_all(config, "name") is True
    assert Arr.has_all(config, []) is False
    assert Arr.hasAll(config, ["name"]) is True


def test_every_and_some() -> None:
    assert Arr.every([1, 2, 3], lambda i: i > 0) is True
    assert Arr.every([1, 2, 3], lambda i: i > 2) is False
    assert Arr.some([1, 2, 3], lambda i: i > 2) is True
    assert Arr.some([1, 2, 3], lambda i: i > 9) is False
    assert Arr.every([], lambda i: False) is True


def test_sole_insists_on_exactly_one_match() -> None:
    assert Arr.sole(["Desk", "Table"], lambda value: value == "Desk") == "Desk"
    assert Arr.sole(["Desk"]) == "Desk"

    with pytest.raises(ItemNotFoundError):
        Arr.sole(["Desk"], lambda value: value == "Chair")
    with pytest.raises(MultipleItemsFoundError, match="2 items"):
        Arr.sole(["Desk", "Desk"], lambda value: value == "Desk")


def test_partition_splits_on_a_predicate() -> None:
    under, over = Arr.partition([1, 2, 3, 4, 5, 6], lambda i: i < 3)

    assert under == [1, 2]
    assert over == [3, 4, 5, 6]


def test_select_keeps_only_the_given_keys() -> None:
    rows = [
        {"id": 1, "name": "Desk", "price": 200},
        {"id": 2, "name": "Table", "price": 150},
    ]

    assert Arr.select(rows, ["name", "price"]) == [
        {"name": "Desk", "price": 200},
        {"name": "Table", "price": 150},
    ]
    assert Arr.select(rows, "name") == [{"name": "Desk"}, {"name": "Table"}]


def test_only_values_and_except_values() -> None:
    items = ["foo", "bar", "baz", "qux"]

    assert Arr.only_values(items, ["foo", "baz"]) == ["foo", "baz"]
    assert Arr.except_values(items, ["foo", "baz"]) == ["bar", "qux"]
    assert Arr.onlyValues(items, ["foo"]) == ["foo"]
    assert Arr.exceptValues(items, ["foo"]) == ["bar", "baz", "qux"]


def test_push_appends_at_a_dot_key() -> None:
    array: dict = {}

    Arr.push(array, "office.furniture", "Desk")
    Arr.push(array, "office.furniture", "Chair", "Lamp")

    assert array == {"office": {"furniture": ["Desk", "Chair", "Lamp"]}}


def test_push_returns_the_array_it_was_given() -> None:
    array: dict = {"tags": ["a"]}

    assert Arr.push(array, "tags", "b") is array
    assert array["tags"] == ["a", "b"]


# --- Number -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "first"),
        (2, "second"),
        (3, "third"),
        (4, "fourth"),
        (5, "fifth"),
        (8, "eighth"),
        (9, "ninth"),
        (12, "twelfth"),
        (13, "thirteenth"),
        (20, "twentieth"),
        (21, "twenty-first"),
        (22, "twenty-second"),
        (30, "thirtieth"),
        (40, "fortieth"),
        (100, "one hundredth"),
    ],
)
def test_spell_ordinal(number: int, expected: str) -> None:
    assert Number.spell_ordinal(number) == expected
    assert Number.spellOrdinal(number) == expected


def test_parse_int_discards_the_fraction() -> None:
    assert Number.parse_int("10.123") == 10
    assert Number.parse_int("10") == 10
    # A comma groups in English, so this is ten thousand one hundred and so on.
    assert Number.parse_int("10,123") == 10123
    assert Number.parseInt("5") == 5


def test_parse_float_ignores_grouping() -> None:
    assert Number.parse_float("10") == 10.0
    assert Number.parse_float("1,234.5") == 1234.5
    assert Number.parse_float(" 42 ") == 42.0
    assert Number.parseFloat("1.5") == 1.5


def test_parsing_follows_the_locale_for_the_decimal_separator() -> None:
    # In French a comma is the decimal separator, not a group separator.
    assert Number.parse_float("10,5", locale="fr") == 10.5
    assert Number.parse_int("10,123", locale="fr") == 10
    assert Number.parse_float("1.234,5", locale="de") == 1234.5


# --- parity gaps the docs rewrite turned up ----------------------------------


def test_data_set_writes_into_a_list_rather_than_replacing_it() -> None:
    users = {"users": [{"name": "Ada"}, {"name": "Linus"}]}

    data_set(users, "users.0.name", "Grace")

    assert users == {"users": [{"name": "Grace"}, {"name": "Linus"}]}


def test_data_set_grows_a_list_to_reach_the_index_it_was_given() -> None:
    users = {"users": [{"name": "Ada"}]}

    data_set(users, "users.2.name", "Alan")

    assert users == {"users": [{"name": "Ada"}, None, {"name": "Alan"}]}


def test_data_set_refuses_a_name_where_a_list_wants_an_index() -> None:
    with pytest.raises(TypeError, match="Cannot use 'name' as an index into a list"):
        data_set({"tags": ["x"]}, "tags.name", "y")


def test_data_get_fans_out_over_a_wildcard() -> None:
    data = {"users": [{"name": "Ada", "roles": [{"id": 1}]}, {"name": "Linus"}]}

    assert data_get(data, "users.*.name") == ["Ada", "Linus"]
    assert data_get(data, "users.*") == data["users"]
    assert data_get({"a": {"x": 1, "y": 2}}, "a.*") == [1, 2]
    assert data_get(data, "missing.*.name", "fallback") == "fallback"


def test_a_second_wildcard_collapses_one_level() -> None:
    data = {"users": [{"roles": [{"id": 1}, {"id": 2}]}, {"roles": [{"id": 3}]}]}

    assert data_get(data, "users.*.roles.*.id") == [1, 2, 3]


def test_to_css_styles_takes_properties_or_switched_styles() -> None:
    assert Arr.to_css_styles({"background-color": "blue"}) == "background-color:blue"
    assert Arr.to_css_styles({"display: none": True, "color: red": False}) == "display: none"
    assert Arr.to_css_styles(["display: none;", "color: red"]) == "display: none;color: red"
    assert Arr.to_css_styles({"color": None, "margin": 0}) == "margin:0"


def test_data_set_builds_a_mapping_through_an_index_a_list_has_not_reached() -> None:
    data: dict = {"users": []}

    data_set(data, "users.1.name", "Ada")

    assert data == {"users": [None, {"name": "Ada"}]}
