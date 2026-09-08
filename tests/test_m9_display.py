"""Tests for Loupe pretty display (models, collections, JSON)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from almasix.console.display import (
    describe,
    dump,
    is_model,
    is_model_collection,
    render,
    serialize,
    to_json,
)


class FakeModel:
    def __init__(self, **attrs):
        self._attributes = attrs
        self._key = attrs.get("id")

    def get_key(self):
        return self._key

    def to_dict(self):
        return dict(self._attributes)


class FakeModelCollection(list):
    def model_keys(self):
        return [item.get_key() for item in self]

    def to_dict(self):
        return [item.to_dict() for item in self]


def test_serialize_model_and_collection() -> None:
    user = FakeModel(id=1, name="Ada", email="ada@example.com")
    assert is_model(user)
    assert serialize(user) == {"id": 1, "name": "Ada", "email": "ada@example.com"}
    assert "Ada" in to_json(user)

    users = FakeModelCollection([user, FakeModel(id=2, name="Grace")])
    assert is_model_collection(users)
    assert serialize(users) == [
        {"id": 1, "name": "Ada", "email": "ada@example.com"},
        {"id": 2, "name": "Grace"},
    ]
    assert describe(users).startswith("Collection[")


def test_serialize_nested_and_primitives() -> None:
    assert serialize(None) is None
    assert serialize("x") == "x"
    assert serialize({"a": FakeModel(id=1, name="A")}) == {"a": {"id": 1, "name": "A"}}
    assert serialize([1, FakeModel(id=2)]) == [1, {"id": 2}]


def test_describe_shapes() -> None:
    assert describe(FakeModel(id=9)).startswith("FakeModel")
    assert "dict" in describe({"a": 1})
    assert "list" in describe([1, 2])


def test_render_and_dump(capsys) -> None:
    user = FakeModel(id=1, name="Ada")
    render(user)
    result = dump(user, {"ok": True})
    assert result == (user, {"ok": True})
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "Ada" in text or "FakeModel" in text
    assert "ok" in text or "True" in text or "dict" in text


def test_paginator_and_fallback_to_dict() -> None:
    page = SimpleNamespace(
        items=[FakeModel(id=1)],
        to_dict=lambda: {"data": [{"id": 1}], "total": 1},
    )
    assert serialize(page) == {"data": [{"id": 1}], "total": 1}


class ToDictWantsArguments:
    """A ``to_dict`` that is not the no-argument one Loupe hopes for."""

    def to_dict(self, *, deep):  # noqa: ANN001 - the signature is the point
        raise AssertionError("never callable without arguments")


def test_a_to_dict_that_takes_arguments_falls_back_instead_of_raising() -> None:
    """Loupe prints whatever it is handed; a hostile ``to_dict`` must not stop it."""
    from almasix.support import Collection as SupportCollection

    value = ToDictWantsArguments()
    assert serialize(value) is value

    # And a value with no ``to_dict`` at all comes back as it went in.
    moment = datetime(2026, 9, 8, 10, 30)
    assert serialize(moment) is moment
    assert serialize(SupportCollection([1, [2]])) == [1, [2]]
