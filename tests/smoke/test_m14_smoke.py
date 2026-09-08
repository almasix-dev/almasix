"""Smoke — Helpers + Strings import and basic DX."""

from __future__ import annotations

from almasix.support import Arr, Number, Str, blank, collect, data_get, str_


def test_m14_helpers_strings_smoke() -> None:
    assert blank("") is True
    assert data_get({"a": {"b": 1}}, "a.b") == 1
    assert Arr.pluck([{"n": 1}, {"n": 2}], "n") == [1, 2]
    assert Str.slug("Hello Almasix") == "hello-almasix"
    assert str(str_("Foo").append("Bar")) == "FooBar"
    assert Number.ordinal(1) == "1st"
    assert collect([1, 2, 3]).avg() == 2
