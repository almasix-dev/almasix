"""M42 — the where clauses Laravel's Query Builder page documents.

Every test runs against real SQLite rather than asserting on compiled SQL:
a clause that reads correctly and matches the wrong rows is still wrong.
The clauses SQLite cannot run at all live in `test_m42_dialects.py`.
"""

from __future__ import annotations

import datetime
import json

import pytest

from almasix.orm import DB, Schema
from almasix.orm.builder import QueryBuilder
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _people(**overrides: object) -> None:
    """Two people, one of everything worth filtering on."""
    await Schema.create(
        "people",
        lambda table: (
            table.id(),
            table.string("name"),
            table.string("email"),
            table.integer("votes"),
            table.text("options").nullable(),
            table.string("due_at").nullable(),
            table.integer("floor"),
            table.integer("ceiling"),
            table.string("nickname").nullable(),
        ),
    )
    await DB.table("people").insert(
        [
            {
                "id": 1,
                "name": "Ada",
                "email": "ada@example.com",
                "votes": 120,
                "options": json.dumps(
                    {"languages": ["en", "fr"], "dining": {"meal": "salad"}, "enabled": True}
                ),
                "due_at": "2020-01-01 10:00:00",
                "floor": 50,
                "ceiling": 150,
                "nickname": None,
            },
            {
                "id": 2,
                "name": "Grace",
                "email": "grace@navy.mil",
                "votes": 40,
                "options": json.dumps(
                    {"languages": ["de"], "dining": {"meal": "pasta"}, "enabled": False}
                ),
                "due_at": "2999-01-01 10:00:00",
                "floor": 10,
                "ceiling": 20,
                "nickname": "Amazing",
            },
        ]
    )


def people() -> QueryBuilder:
    return DB.table("people")


async def names(query: QueryBuilder) -> list[str]:
    return sorted(row["name"] for row in await query.get())


# --- the basics ----------------------------------------------------------


async def test_where_takes_a_mapping_or_a_list_of_triples(memory_db) -> None:
    await _people()
    assert await names(people().where({"name": "Ada", "votes": 120})) == ["Ada"]
    assert await names(people().where([["name", "=", "Ada"], ["votes", ">", 100]])) == ["Ada"]


async def test_where_not_negates_a_whole_group(memory_db) -> None:
    await _people()
    excluded = people().where_not(lambda query: query.where("votes", "<", 100))
    assert await names(excluded) == ["Ada"]
    assert await names(people().where_not("name", "Ada")) == ["Grace"]


async def test_where_not_with_nothing_to_negate_changes_nothing(memory_db) -> None:
    await _people()
    assert await names(people().where_not(lambda query: query)) == ["Ada", "Grace"]


async def test_or_where_not_widens_rather_than_narrows(memory_db) -> None:
    await _people()
    query = people().where("votes", ">", 1000).or_where_not("name", "Ada")
    assert await names(query) == ["Grace"]


async def test_any_all_and_none_apply_one_constraint_to_several_columns(memory_db) -> None:
    await _people()
    assert await names(people().where_any(["name", "email"], "like", "%ada%")) == ["Ada"]
    assert await names(people().where_all(["name", "email"], "like", "%a%")) == ["Ada", "Grace"]
    assert await names(people().where_none(["name", "email"], "like", "%ada%")) == ["Grace"]


async def test_the_or_forms_of_any_all_and_none(memory_db) -> None:
    await _people()
    impossible = people().where("votes", ">", 1000)
    assert await names(impossible.clone().or_where_any(["name"], "like", "Ada")) == ["Ada"]
    assert await names(impossible.clone().or_where_all(["name"], "like", "Ada")) == ["Ada"]
    assert await names(impossible.clone().or_where_none(["name"], "like", "Ada")) == ["Grace"]


async def test_a_constraint_across_no_columns_at_all_is_no_constraint(memory_db) -> None:
    await _people()
    assert await names(people().where_any([], "like", "%")) == ["Ada", "Grace"]


# --- membership ----------------------------------------------------------


async def test_in_and_not_in_accept_a_query_as_well_as_a_list(memory_db) -> None:
    await _people()
    loud = people().select("id").where("votes", ">", 100)
    assert await names(people().where_in("id", loud)) == ["Ada"]
    assert await names(people().where_not_in("id", loud)) == ["Grace"]
    assert await names(people().where_in("id", [2])) == ["Grace"]
    assert await names(people().or_where_in("id", [2])) == ["Grace"]
    assert await names(people().where("votes", ">", 1000).or_where_not_in("id", [1])) == ["Grace"]


async def test_integer_lists_can_be_inlined_rather_than_bound(memory_db) -> None:
    await _people()
    assert await names(people().where_integer_in_raw("id", [1])) == ["Ada"]
    assert await names(people().where_integer_not_in_raw("id", [1])) == ["Grace"]
    assert await names(people().where("id", 2).or_where_integer_in_raw("id", [1])) == ["Ada", "Grace"]
    assert await names(people().where("id", 1).or_where_integer_not_in_raw("id", [1])) == ["Ada", "Grace"]


async def test_an_inlined_list_with_nothing_in_it_matches_nothing(memory_db) -> None:
    await _people()
    assert await names(people().where_integer_in_raw("id", [])) == []
    assert await names(people().where_integer_not_in_raw("id", [])) == ["Ada", "Grace"]


async def test_inlining_refuses_anything_that_is_not_an_integer(memory_db) -> None:
    await _people()
    with pytest.raises(ValueError, match="invalid literal"):
        people().where_integer_in_raw("id", ["1); drop table people; --"])


# --- null ----------------------------------------------------------------


async def test_null_and_the_null_safe_comparison(memory_db) -> None:
    await _people()
    assert await names(people().where_null("nickname")) == ["Ada"]
    assert await names(people().where_not_null("nickname")) == ["Grace"]
    assert await names(people().where("id", 0).or_where_null("nickname")) == ["Ada"]
    assert await names(people().where("id", 0).or_where_not_null("nickname")) == ["Grace"]
    assert await names(people().where_null_safe_equals("nickname", None)) == ["Ada"]
    assert await names(people().where("id", 0).or_where_null_safe_equals("nickname", "Amazing")) == [
        "Grace"
    ]


# --- ranges --------------------------------------------------------------


async def test_between_takes_two_arguments_or_one_pair(memory_db) -> None:
    await _people()
    assert await names(people().where_between("votes", 1, 100)) == ["Grace"]
    assert await names(people().where_between("votes", [1, 100])) == ["Grace"]
    assert await names(people().where_not_between("votes", [1, 100])) == ["Ada"]
    assert await names(people().where("id", 0).or_where_between("votes", [1, 100])) == ["Grace"]
    assert await names(people().where("id", 0).or_where_not_between("votes", [1, 100])) == ["Ada"]


async def test_between_two_columns_of_the_same_row(memory_db) -> None:
    await _people()
    bounds = ["floor", "ceiling"]
    assert await names(people().where_between_columns("votes", bounds)) == ["Ada"]
    assert await names(people().where_not_between_columns("votes", bounds)) == ["Grace"]
    assert await names(people().where("id", 0).or_where_between_columns("votes", bounds)) == ["Ada"]
    assert await names(people().where("id", 0).or_where_not_between_columns("votes", bounds)) == [
        "Grace"
    ]


async def test_a_value_between_two_columns(memory_db) -> None:
    await _people()
    bounds = ["floor", "ceiling"]
    assert await names(people().where_value_between(100, bounds)) == ["Ada"]
    assert await names(people().where_value_not_between(100, bounds)) == ["Grace"]
    assert await names(people().where("id", 0).or_where_value_between(100, bounds)) == ["Ada"]
    assert await names(people().where("id", 0).or_where_value_not_between(100, bounds)) == ["Grace"]


async def test_comparing_one_column_against_another(memory_db) -> None:
    await _people()
    assert await names(people().where_column("votes", ">", "ceiling")) == ["Grace"]
    assert await names(people().where("id", 0).or_where_column("votes", "<", "ceiling")) == ["Ada"]


# --- pattern matching -----------------------------------------------------


async def test_like_is_case_insensitive_unless_told_otherwise(memory_db) -> None:
    await _people()
    assert await names(people().where_like("name", "%ADA%")) == ["Ada"]
    assert await names(people().where_not_like("name", "%ADA%")) == ["Grace"]
    assert await names(people().where("id", 0).or_where_like("name", "%ada%")) == ["Ada"]
    assert await names(people().where("id", 0).or_where_not_like("name", "%ada%")) == ["Grace"]


async def test_a_case_sensitive_like_compiles_for_the_engine(memory_db) -> None:
    await _people()
    # SQLite's LIKE is case-insensitive for ASCII whatever we ask, so this
    # asserts the clause runs and matches; the SQL each engine gets is in
    # test_m42_dialects.py.
    assert await names(people().where_like("name", "Ada", case_sensitive=True)) == ["Ada"]
    assert await names(people().where_not_like("name", "Ada", case_sensitive=True)) == ["Grace"]
    assert await names(people().where("id", 0).or_where_like("name", "Ada", True)) == ["Ada"]
    assert await names(people().where("id", 0).or_where_not_like("name", "Ada", True)) == ["Grace"]


# --- dates and times -------------------------------------------------------


async def test_the_date_part_family(memory_db) -> None:
    await _people()
    assert await names(people().where_year("due_at", 2020)) == ["Ada"]
    assert await names(people().where_month("due_at", 1)) == ["Ada", "Grace"]
    assert await names(people().where_day("due_at", 1)) == ["Ada", "Grace"]
    assert await names(people().where_date("due_at", "2020-01-01")) == ["Ada"]
    assert await names(people().where_time("due_at", "10:00:00")) == ["Ada", "Grace"]


async def test_the_or_forms_of_the_date_part_family(memory_db) -> None:
    await _people()
    none = people().where("id", 0)
    assert await names(none.clone().or_where_year("due_at", 2020)) == ["Ada"]
    assert await names(none.clone().or_where_month("due_at", 1)) == ["Ada", "Grace"]
    assert await names(none.clone().or_where_day("due_at", 1)) == ["Ada", "Grace"]
    assert await names(none.clone().or_where_date("due_at", "2020-01-01")) == ["Ada"]
    assert await names(none.clone().or_where_time("due_at", "10:00:00")) == ["Ada", "Grace"]


async def test_dates_and_times_may_be_given_as_objects(memory_db) -> None:
    await _people()
    assert await names(people().where_date("due_at", datetime.date(2020, 1, 1))) == ["Ada"]
    when = datetime.datetime(2020, 1, 1, 10, 0, 0)  # noqa: DTZ001 - a stored naive timestamp
    assert await names(people().where_date("due_at", when)) == ["Ada"]
    assert await names(people().where_time("due_at", when)) == ["Ada", "Grace"]
    assert await names(people().where_time("due_at", datetime.time(10, 0, 0))) == ["Ada", "Grace"]


async def test_past_and_future_read_the_applications_clock(memory_db) -> None:
    await _people()
    assert await names(people().where_past("due_at")) == ["Ada"]
    assert await names(people().where_future("due_at")) == ["Grace"]
    assert await names(people().where_now_or_past("due_at")) == ["Ada"]
    assert await names(people().where_now_or_future("due_at")) == ["Grace"]
    none = people().where("id", 0)
    assert await names(none.clone().or_where_past("due_at")) == ["Ada"]
    assert await names(none.clone().or_where_future("due_at")) == ["Grace"]
    assert await names(none.clone().or_where_now_or_past("due_at")) == ["Ada"]
    assert await names(none.clone().or_where_now_or_future("due_at")) == ["Grace"]


async def test_today_and_the_days_either_side_of_it(memory_db) -> None:
    await _people()
    assert await names(people().where_today("due_at")) == []
    assert await names(people().where_before_today("due_at")) == ["Ada"]
    assert await names(people().where_after_today("due_at")) == ["Grace"]
    assert await names(people().where_today_or_before("due_at")) == ["Ada"]
    assert await names(people().where_today_or_after("due_at")) == ["Grace"]
    none = people().where("id", 0)
    assert await names(none.clone().or_where_today("due_at")) == []
    assert await names(none.clone().or_where_before_today("due_at")) == ["Ada"]
    assert await names(none.clone().or_where_after_today("due_at")) == ["Grace"]
    assert await names(none.clone().or_where_today_or_before("due_at")) == ["Ada"]
    assert await names(none.clone().or_where_today_or_after("due_at")) == ["Grace"]


async def test_a_frozen_clock_moves_what_past_and_future_mean(memory_db) -> None:
    from almasix.testing.time import travel_back, travel_to

    await _people()
    travel_to(datetime.datetime(3000, 1, 1, tzinfo=datetime.UTC))
    try:
        assert await names(people().where_past("due_at")) == ["Ada", "Grace"]
        assert await names(people().where_future("due_at")) == []
    finally:
        travel_back()


# --- JSON -----------------------------------------------------------------


async def test_a_json_path_reads_the_value_it_is_compared_against(memory_db) -> None:
    await _people()
    assert await names(people().where("options->dining->meal", "salad")) == ["Ada"]
    assert await names(people().where("options->enabled", True)) == ["Ada"]
    assert await names(people().where("options->enabled", False)) == ["Grace"]
    assert await names(people().where_in("options->dining->meal", ["salad", "sushi"])) == ["Ada"]


async def test_json_containment_and_its_negation(memory_db) -> None:
    await _people()
    assert await names(people().where_json_contains("options->languages", "fr")) == ["Ada"]
    assert await names(people().where_json_doesnt_contain("options->languages", "fr")) == ["Grace"]
    none = people().where("id", 0)
    assert await names(none.clone().or_where_json_contains("options->languages", "fr")) == ["Ada"]
    assert await names(none.clone().or_where_json_doesnt_contain("options->languages", "fr")) == [
        "Grace"
    ]


async def test_asking_whether_a_key_is_there_at_all(memory_db) -> None:
    await _people()
    assert await names(people().where_json_contains_key("options->dining->meal")) == ["Ada", "Grace"]
    assert await names(people().where_json_contains_key("options->missing")) == []
    assert await names(people().where_json_doesnt_contain_key("options->missing")) == ["Ada", "Grace"]
    none = people().where("id", 0)
    assert await names(none.clone().or_where_json_contains_key("options->enabled")) == ["Ada", "Grace"]
    assert await names(none.clone().or_where_json_doesnt_contain_key("options->missing")) == [
        "Ada",
        "Grace",
    ]


async def test_how_long_a_json_array_is(memory_db) -> None:
    await _people()
    assert await names(people().where_json_length("options->languages", ">", 1)) == ["Ada"]
    assert await names(people().where_json_length("options->languages", 1)) == ["Grace"]
    assert await names(people().where("id", 0).or_where_json_length("options->languages", 1)) == [
        "Grace"
    ]


async def test_a_json_column_can_be_ordered_by_a_path(memory_db) -> None:
    await _people()
    ordered = await people().order_by("options->dining->meal").pluck("name")
    assert list(ordered) == ["Grace", "Ada"]


# --- existence and subqueries ---------------------------------------------


async def _orders(memory_db) -> None:
    await _people()
    await Schema.create(
        "orders",
        lambda table: (table.id(), table.integer("person_id"), table.integer("total")),
    )
    await DB.table("orders").insert([{"id": 1, "person_id": 1, "total": 50}])


async def test_exists_correlates_with_the_outer_query(memory_db) -> None:
    await _orders(memory_db)
    correlated = DB.table("orders").select_raw("1").where_column("orders.person_id", "people.id")
    assert await names(people().where_exists(correlated)) == ["Ada"]
    assert await names(people().where_not_exists(correlated)) == ["Grace"]
    none = people().where("people.id", 0)
    assert await names(none.clone().or_where_exists(correlated)) == ["Ada"]
    assert await names(none.clone().or_where_not_exists(correlated)) == ["Grace"]


async def test_a_query_may_stand_where_a_value_or_a_column_does(memory_db) -> None:
    await _people()
    average = DB.table("people").select_raw("avg(votes)")
    assert await names(people().where("votes", ">", average)) == ["Ada"]
    assert await names(people().where(average, "<", 100)) == ["Ada", "Grace"]


async def test_exists_also_takes_a_plain_select(memory_db) -> None:
    import sqlalchemy as sa

    await _orders(memory_db)
    statement = DB.table("orders").where_column("orders.person_id", "people.id").to_select()
    assert await names(people().where_exists(sa.select(sa.literal(1)).select_from(statement.subquery()))) == [
        "Ada",
        "Grace",
    ]


# --- raw ------------------------------------------------------------------


async def test_raw_where_clauses_bind_their_values(memory_db) -> None:
    await _people()
    assert await names(people().where_raw("votes > :floor", bindings={"floor": 100})) == ["Ada"]
    widened = people().where("id", 0).or_where_raw("votes > :floor", {"floor": 100})
    assert await names(widened) == ["Ada"]
    assert await names(people().or_where_raw("votes > 100")) == ["Ada"]


async def test_an_unknown_operator_is_refused_rather_than_guessed(memory_db) -> None:
    await _people()
    with pytest.raises(ValueError, match="Unsupported operator"):
        people().where("votes", "≈", 100)
