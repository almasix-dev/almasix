"""M14 — Helpers + Strings (Arr, Str, Number, misc helpers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.http.exceptions import HttpException
from almasix.support import (
    Arr,
    Number,
    Str,
    Stringable,
    abort_if,
    blank,
    class_basename,
    collect,
    data_fill,
    data_forget,
    data_get,
    data_set,
    e,
    filled,
    head,
    last,
    literal,
    now,
    once,
    optional,
    preg_replace_array,
    rescue,
    retry,
    str_,
    tap,
    throw_if,
    today,
    transform,
    value,
    when,
    with_,
)


def test_arr_core_operations() -> None:
    assert Arr.accessible({"a": 1})
    assert Arr.accessible([1, 2])
    assert not Arr.accessible("nope")

    data = {"name": "Ada"}
    Arr.add(data, "role", "admin")
    Arr.add(data, "name", "ignored")
    assert data["role"] == "admin"
    assert data["name"] == "Ada"

    assert Arr.collapse([[1, 2], [3]]) == [1, 2, 3]
    assert Arr.cross_join([1, 2], ["a", "b"]) == [[1, "a"], [1, "b"], [2, "a"], [2, "b"]]
    keys, values = Arr.divide({"a": 1, "b": 2})
    assert keys == ["a", "b"]
    assert values == [1, 2]

    dotted = Arr.dot({"a": {"b": 1}, "c": [2, 3]})
    assert dotted["a.b"] == 1
    assert dotted["c.0"] == 2
    assert Arr.undot({"user.name": "Ada"}) == {"user": {"name": "Ada"}}

    assert Arr.except_({"a": 1, "b": 2}, ["b"]) == {"a": 1}
    assert Arr.only({"a": 1, "b": 2}, ["b"]) == {"b": 2}
    assert Arr.exists({"a": 1}, "a")
    assert Arr.first([1, 2, 3], lambda n: n > 1) == 2
    assert Arr.last([1, 2, 3], lambda n: n < 3) == 2
    assert Arr.flatten([1, [2, [3]]], depth=1) == [1, 2, [3]]

    nested: dict = {"a": {"b": 1, "c": 2}}
    Arr.forget(nested, "a.b")
    assert nested == {"a": {"c": 2}}
    assert Arr.get({"a": {"b": 3}}, "a.b") == 3
    assert Arr.has({"a": {"b": None}}, "a.b")
    assert Arr.has_any({"a": 1}, ["z", "a"])
    assert Arr.is_assoc({"a": 1})
    assert Arr.is_list([1, 2])
    assert Arr.join(["a", "b", "c"], ", ", ", and ") == "a, b, and c"
    assert Arr.key_by([{"id": 1}], "id")[1]["id"] == 1
    assert Arr.map([1, 2], lambda v, i: v + i) == [1, 3]
    assert Arr.map_with_keys([1, 2], lambda v, i: {v: i}) == {1: 0, 2: 1}
    assert Arr.map_spread([[1, 2], [3, 4]], lambda a, b: a + b) == [3, 7]
    assert Arr.pluck([{"n": "a"}, {"n": "b"}], "n") == ["a", "b"]
    assert Arr.prepend([2, 3], 1) == [1, 2, 3]
    assert Arr.prepend_keys_with({"a": 1}, "x_") == {"x_a": 1}
    bag = {"a": 1, "b": 2}
    assert Arr.pull(bag, "a") == 1
    assert "a" not in bag
    assert "a=1&b=2" in Arr.query({"a": 1, "b": 2})
    assert Arr.random([1]) == 1
    assert Arr.reject([1, 2, 3], lambda n: n % 2 == 0) == [1, 3]
    Arr.set(bag, "c.d", 9)
    assert bag["c"]["d"] == 9
    assert set(Arr.shuffle([1, 2])) == {1, 2}
    assert Arr.sort([3, 1, 2]) == [1, 2, 3]
    assert Arr.sort_desc([1, 2, 3]) == [3, 2, 1]
    assert Arr.sort_recursive({"b": 2, "a": {"z": 1, "y": 0}})["a"]["y"] == 0
    assert Arr.take([1, 2, 3], 2) == [1, 2]
    assert Arr.to_css_classes({"p-4": True, "hidden": False}) == "p-4"
    assert "color:red" in Arr.to_css_styles({"color": "red", "display": None})
    assert Arr.where([1, 2, 3], lambda n: n > 1) == [2, 3]
    assert Arr.where_not_null([1, None, 2]) == [1, 2]
    assert Arr.wrap(None) == []
    assert Arr.wrap(1) == [1]


def test_data_helpers_and_misc() -> None:
    target: dict = {}
    data_set(target, "user.name", "Ada")
    data_fill(target, "user.name", "ignored")
    data_fill(target, "user.role", "admin")
    assert target == {"user": {"name": "Ada", "role": "admin"}}
    data_forget(target, "user.role")
    assert target["user"] == {"name": "Ada"}
    assert data_get(target, "user.name") == "Ada"
    assert head([1, 2]) == 1
    assert last([1, 2]) == 2
    assert blank("") and blank([]) and blank(None)
    assert filled("x") and not blank(False)
    assert value(lambda: 5) == 5
    assert value(5) == 5
    assert tap(1, lambda n: None) == 1
    assert with_(2, lambda n: n * 2) == 4
    assert when(True, "yes", "no") == "yes"
    assert when(False, "yes", "no") == "no"
    assert transform("ada", str.upper) == "ADA"
    assert transform("", str.upper, "fallback") == "fallback"
    assert optional(None).missing._obj is None  # type: ignore[attr-defined]
    assert optional({"a": 1}, lambda d: d["a"]) == 1
    assert class_basename("pkg.mod.User") == "User"
    assert class_basename(Path) == "Path"
    lit = literal(a=1, b=2)
    assert lit.a == 1
    assert now().tzinfo is not None
    assert today() is not None
    assert e("<b>") == "&lt;b&gt;"
    assert preg_replace_array(r"\?", ["a", "b"], "? and ?") == "a and b"

    calls = {"n": 0}

    def boom() -> int:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("retry")
        return 7

    assert retry(5, boom, sleep=0) == 7
    assert rescue(lambda: 1 / 0, 0) == 0
    assert once(lambda: 42) == 42
    assert once(lambda: 99) == 99  # different function object — not same cache key intent
    # same callback identity
    cb = lambda: "cached"
    assert once(cb) == "cached"
    assert once(cb) == "cached"

    with pytest.raises(RuntimeError):
        throw_if(True, RuntimeError("nope"))
    with pytest.raises(HttpException):
        abort_if(True, 403, "forbidden")


def test_str_and_stringable() -> None:
    assert Str.camel("foo_bar") == "fooBar"
    assert Str.snake("FooBar") == "foo_bar"
    assert Str.kebab("FooBar") == "foo-bar"
    assert Str.slug("Hello World!") == "hello-world"
    assert Str.limit("abcdef", 3) == "abc..."
    assert Str.contains("Almasix", "mas")
    assert Str.contains_all("Almasix", ["Al", "six"])
    assert Str.starts_with("Almasix", "Alm")
    assert Str.ends_with("Almasix", "six")
    assert Str.uuid().count("-") == 4
    assert Str.is_uuid(Str.uuid())
    assert len(Str.ulid()) == 26
    assert Str.plural("child") == "children"
    assert Str.singular("children") == "child"
    assert Str.after("a/b/c", "/") == "b/c"
    assert Str.before_last("a/b/c", "/") == "a/b"
    assert Str.between("[a]", "[", "]") == "a"
    assert Str.mask("1234567890", "*", 2, 4) == "12****7890"
    assert Str.replace_first("a", "x", "a a") == "x a"
    assert Str.headline("steve_jobs") == "Steve Jobs"
    assert "<strong>" in Str.inline_markdown("**bold**")

    fluent = str_("FooBar").snake().upper()
    assert isinstance(fluent, Stringable)
    assert str(fluent) == "FOO_BAR"
    assert Str.of("hello").append("!").exactly("hello!")


def test_number_helpers() -> None:
    assert Number.clamp(15, 10, 12) == 12
    assert Number.ordinal(1) == "1st"
    assert Number.ordinal(22) == "22nd"
    assert Number.percentage(10, precision=0) == "10%"
    assert "$" in Number.currency(12.5)
    assert "KB" in Number.file_size(2048, precision=0) or "2" in Number.file_size(2048)
    assert Number.abbreviate(1500, precision=1).endswith("K")
    assert Number.spell(21) == "twenty-one"
    assert Number.pairs(10, 3) == [(1, 3), (4, 6), (7, 9), (10, 10)]
    assert Number.trim(1.0) == 1
    assert Number.with_locale("fr", lambda: Number.default_locale()) == "fr"
    assert Number.default_locale() == "en"


def test_collect_still_exported() -> None:
    assert collect([1, 2]).sum() == 3


def test_excerpt_marks_the_ends_it_trims() -> None:
    text = "This is a very long sentence about Ada and her engine designs"

    assert Str.excerpt(text, "Ada", options={"radius": 5}) == "...bout Ada and ..."
    assert Str.excerpt("Ada wrote", "Ada", options={"radius": 5}) == "Ada wrot..."
    assert Str.excerpt("written by Ada", "Ada", options={"radius": 5}) == "...n by Ada"
    assert Str.excerpt("nothing here", "missing") is None


def test_is_matches_wildcard_patterns() -> None:
    assert Str.is_("*.txt", "notes.txt") is True
    assert Str.is_("*.txt", "notes.md") is False
    assert Str.is_("notes.txt", "notes.txt") is True
    assert Str.is_(["*.md", "*.txt"], "notes.txt") is True


def test_inflecting_a_word_already_in_the_target_form_leaves_it_alone() -> None:
    assert Str.plural("person") == "people"
    assert Str.plural("people") == "people"
    assert Str.plural("person", 1) == "person"
    assert Str.singular("people") == "person"
    assert Str.singular("person") == "person"
    assert Str.singular("book") == "book"


def test_take_counts_from_the_end_when_negative() -> None:
    assert Str.take("abcdef", 2) == "ab"
    assert Str.take("abcdef", -2) == "ef"


def test_map_with_keys_accepts_a_mapping() -> None:
    users = {"a": {"email": "ada@example.com"}, "b": {"email": "bob@example.com"}}

    assert Arr.map_with_keys(users, lambda user, key: {user["email"]: key}) == {
        "ada@example.com": "a",
        "bob@example.com": "b",
    }


def test_forget_stops_at_a_segment_that_is_not_a_mapping() -> None:
    array = {"products": {"name": "Desk"}}

    Arr.forget(array, "products.name.deeper")

    assert array == {"products": {"name": "Desk"}}
