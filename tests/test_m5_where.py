"""M5 — Laravel where() two-arg shortcut vs three-arg canonical form."""

from __future__ import annotations

import pytest

from almasix.orm import Model, Schema
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


class Item(Model):
    table = "items"
    timestamps = False
    fillable = ("name", "votes", "op")


async def _items(memory_db) -> None:
    await Schema.create(
        "items",
        lambda table: (
            table.id(),
            table.string("name"),
            table.integer("votes"),
            table.string("op").nullable(),
        ),
    )
    await Item.create(name="alpha", votes=1, op="=")
    await Item.create(name="beta", votes=5, op=">")
    await Item.create(name="gamma", votes=10, op="like")


async def test_three_arg_where_is_canonical(memory_db) -> None:
    await _items(memory_db)
    found = await Item.query().where("votes", ">", 4).order_by("votes").get()
    assert [item.name for item in found] == ["beta", "gamma"]


async def test_two_arg_where_is_equals_shortcut(memory_db) -> None:
    await _items(memory_db)
    found = await Item.query().where("name", "beta").first()
    assert found is not None and found.votes == 5
    also = await Item.query().where("name", "=", "beta").first()
    assert also is not None and also.is_(found)


async def test_two_arg_never_guesses_operator(memory_db) -> None:
    """where('op', '>') means op = '>', not a greater-than with a missing value."""
    await _items(memory_db)
    found = await Item.query().where("op", ">").first()
    assert found is not None and found.name == "beta"
    sql = Item.query().where("op", ">").to_raw_sql().lower()
    assert ">" in sql
    # The value is bound/literal '>', not a comparison against another column.
    assert "op" in sql


async def test_or_where_and_nested_groups(memory_db) -> None:
    await _items(memory_db)
    found = await (
        Item.query()
        .where("name", "=", "alpha")
        .or_where("name", "gamma")
        .order_by("name")
        .get()
    )
    assert [item.name for item in found] == ["alpha", "gamma"]

    nested = await Item.query().where(
        lambda query: query.where("votes", ">=", 5).where("name", "!=", "gamma")
    ).first()
    assert nested is not None and nested.name == "beta"


async def test_where_null_is_not_the_equals_shortcut(memory_db) -> None:
    await _items(memory_db)
    await Item.query().where("name", "alpha").update({"op": None})
    missing = await Item.query().where_null("op").get()
    assert [item.name for item in missing] == ["alpha"]
    # Two-arg with None still goes through `=` (SQLAlchemy compiles `=` None as IS NULL).
    also = await Item.query().where("op", None).get()
    assert [item.name for item in also] == ["alpha"]
