"""M42 — joins, unions, ordering, writes, and debugging on the query builder."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa

from almasix.orm import DB, Model, Schema
from almasix.orm.builder import ModelNotFoundError, MultipleRecordsFoundError, QueryBuilder
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _shop() -> None:
    await Schema.create(
        "customers",
        lambda table: (table.id(), table.string("name"), table.string("city")),
    )
    await Schema.create(
        "orders",
        lambda table: (table.id(), table.integer("customer_id"), table.integer("total")),
    )
    await DB.table("customers").insert(
        [
            {"id": 1, "name": "Ada", "city": "London"},
            {"id": 2, "name": "Grace", "city": "New York"},
            {"id": 3, "name": "Linus", "city": "Helsinki"},
        ]
    )
    await DB.table("orders").insert(
        [
            {"id": 1, "customer_id": 1, "total": 50},
            {"id": 2, "customer_id": 1, "total": 70},
            {"id": 3, "customer_id": 2, "total": 10},
        ]
    )


def customers() -> QueryBuilder:
    return DB.table("customers")


# --- joins ----------------------------------------------------------------


async def test_a_join_may_be_built_by_a_callable(memory_db) -> None:
    await _shop()
    query = customers().join(
        "orders",
        lambda join: join.on("customers.id", "=", "orders.customer_id").where(
            "orders.total", ">", 20
        ),
    )
    rows = await query.select("customers.name", "orders.total").get()
    assert [(row["name"], row["total"]) for row in rows] == [("Ada", 50), ("Ada", 70)]


async def test_a_join_clause_takes_or_on_and_nested_groups(memory_db) -> None:
    await _shop()
    query = customers().join(
        "orders",
        lambda join: join.on("customers.id", "=", "orders.customer_id").or_on(
            "customers.id", "=", "orders.id"
        ),
    )
    assert len(await query.get()) == 5

    grouped = customers().join(
        "orders",
        lambda join: join.on(
            lambda nested: nested.where_column("customers.id", "=", "orders.customer_id")
        ),
    )
    assert len(await grouped.get()) == 3


async def test_a_join_with_no_condition_at_all_says_so(memory_db) -> None:
    await _shop()
    with pytest.raises(ValueError, match="has no condition"):
        customers().join("orders", lambda join: join)
    with pytest.raises(ValueError, match="has no condition"):
        customers().join("orders", lambda join: join.on(lambda nested: nested))


async def test_left_and_right_joins_take_callables_too(memory_db) -> None:
    await _shop()
    left = customers().left_join(
        "orders", lambda join: join.on("customers.id", "=", "orders.customer_id")
    )
    assert len(await left.get()) == 4
    right = customers().right_join("orders", "customers.id", "=", "orders.customer_id")
    assert len(await right.get()) == 3


async def test_an_unknown_join_type_is_refused(memory_db) -> None:
    await _shop()
    with pytest.raises(ValueError, match="Unsupported join type"):
        customers().join("orders", "customers.id", "=", "orders.customer_id", kind="sideways")


async def test_a_subquery_can_be_joined_under_a_name(memory_db) -> None:
    await _shop()
    totals = (
        DB.table("orders")
        .select("customer_id")
        .select_raw("sum(total) as spent")
        .group_by("customer_id")
    )
    query = customers().join_sub(totals, "totals", "totals.customer_id", "=", "customers.id")
    rows = await query.select("customers.name", "totals.spent").order_by("customers.name").get()
    assert [(row["name"], row["spent"]) for row in rows] == [("Ada", 120), ("Grace", 10)]


async def test_the_left_right_and_cross_forms_of_a_subquery_join(memory_db) -> None:
    await _shop()

    def totals() -> QueryBuilder:
        return DB.table("orders").select("customer_id", "total")

    left = customers().left_join_sub(totals(), "t", "t.customer_id", "=", "customers.id")
    assert len(await left.get()) == 4
    right = customers().right_join_sub(totals(), "t", "t.customer_id", "=", "customers.id")
    assert len(await right.get()) == 3
    crossed = customers().where("customers.id", 1).cross_join_sub(totals(), "t")
    assert len(await crossed.get()) == 3


async def test_a_lateral_join_may_read_the_outer_row(memory_db) -> None:
    # SQLite has no LATERAL, so this one is read rather than run.
    from sqlalchemy.dialects import postgresql

    await _shop()

    def latest() -> QueryBuilder:
        return (
            DB.table("orders")
            .select("total")
            .where_column("orders.customer_id", "customers.id")
            .order_by_desc("orders.total")
            .limit(1)
        )

    left = customers().left_join_lateral(latest(), "top").select("customers.name", "top.total")
    sql = str(left.to_select().compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN LATERAL" in sql
    assert "WHERE orders.customer_id = customers.id" in sql
    inner = customers().join_lateral(latest(), "top")
    assert "JOIN LATERAL" in str(inner.to_select().compile(dialect=postgresql.dialect()))


async def test_a_query_can_select_from_a_subquery(memory_db) -> None:
    await _shop()
    big = DB.table("orders").select("customer_id", "total").where("total", ">", 20)
    query = DB.table("orders").from_sub(big, "big").where("big.total", "<", 60)
    assert [row["total"] for row in await query.get()] == [50]


async def test_a_column_the_subquery_did_not_select_is_named_as_written(memory_db) -> None:
    await _shop()
    query = DB.table("orders").from_sub(DB.table("orders").select("total"), "t")
    assert "t.customer_id" in query.where("t.customer_id", 1).to_sql()


async def test_a_subquery_can_be_a_selected_column_or_an_ordering(memory_db) -> None:
    await _shop()
    spent = (
        DB.table("orders")
        .select_raw("sum(total)")
        .where_column("orders.customer_id", "customers.id")
    )
    rows = await customers().select("name").select_sub(spent, "spent").order_by("name").get()
    assert [(row["name"], row["spent"]) for row in rows] == [
        ("Ada", 120),
        ("Grace", 10),
        ("Linus", None),
    ]
    ordered = list(await customers().order_by_sub(spent, "desc").pluck("name"))
    assert ordered == ["Ada", "Grace", "Linus"]
    added = (
        await customers().select("name").add_select_sub(spent, "spent").where("name", "Ada").first()
    )
    assert added["spent"] == 120


# --- unions ---------------------------------------------------------------


async def test_a_union_combines_two_queries_and_orders_the_result(memory_db) -> None:
    await _shop()
    query = (
        customers().where("name", "Ada").union(customers().where("name", "Linus")).order_by("name")
    )
    assert [row["name"] for row in await query.get()] == ["Ada", "Linus"]


async def test_union_all_keeps_the_duplicates_a_union_would_drop(memory_db) -> None:
    await _shop()
    assert len(await customers().union(customers()).get()) == 3
    assert len(await customers().union_all(customers()).get()) == 6


async def test_a_union_can_be_ordered_by_something_unnameable(memory_db) -> None:
    await _shop()
    query = customers().union(customers()).order_by_raw("name desc")
    assert [row["name"] for row in await query.get()] == ["Linus", "Grace", "Ada"]


# --- locking --------------------------------------------------------------


async def test_locking_compiles_and_can_be_taken_back(memory_db) -> None:
    from sqlalchemy.dialects import postgresql

    await _shop()
    pg = postgresql.dialect()
    assert "FOR UPDATE" in str(customers().lock_for_update().to_select().compile(dialect=pg))
    assert "FOR SHARE" in str(customers().shared_lock().to_select().compile(dialect=pg))
    assert "FOR UPDATE" in str(customers().lock().to_select().compile(dialect=pg))
    assert "FOR" not in str(
        customers().lock_for_update().lock(False).to_select().compile(dialect=pg)
    )
    assert "FOR SHARE" in str(customers().lock("share").to_select().compile(dialect=pg))
    # SQLite has no row locks, so the clause is dropped rather than failing.
    assert len(await customers().lock_for_update().get()) == 3


# --- ordering, grouping, having --------------------------------------------


async def test_raw_ordering_and_grouping(memory_db) -> None:
    await _shop()
    ordered = await customers().order_by_raw("name desc").pluck("name")
    assert list(ordered) == ["Linus", "Grace", "Ada"]
    grouped = DB.table("orders").group_by_raw("customer_id").select_raw("count(*) as n")
    assert sorted(row["n"] for row in await grouped.get()) == [1, 2]


async def test_reorder_desc_replaces_what_came_before(memory_db) -> None:
    await _shop()
    assert list(await customers().order_by("name").reorder_desc("name").pluck("name")) == [
        "Linus",
        "Grace",
        "Ada",
    ]


async def test_the_having_family(memory_db) -> None:
    await _shop()

    def spend() -> QueryBuilder:
        return (
            DB.table("orders")
            .group_by("customer_id")
            .select("customer_id")
            .select_raw("sum(total) as spent")
        )

    assert [
        row["customer_id"] for row in await spend().having_between("spent", [100, 200]).get()
    ] == [1]
    assert len(await spend().having_raw("sum(total) > 100").get()) == 1
    assert len(await spend().having("customer_id", 1).or_having("customer_id", 2).get()) == 2
    assert (
        len(await spend().having_raw("sum(total) > 500").or_having_raw("sum(total) > 5").get()) == 2
    )
    assert len(await spend().having_between("spent", 100, 200).get()) == 1
    assert (
        len(await spend().having("customer_id", 0).or_having_between("spent", [1, 20]).get()) == 1
    )
    assert len(await spend().having_not_null("spent").get()) == 2
    assert len(await spend().having_null("spent").get()) == 0
    assert len(await spend().having(sa.text("sum(total) > 100")).get()) == 1


async def test_having_still_refuses_a_missing_value(memory_db) -> None:
    await _shop()
    with pytest.raises(TypeError, match="having"):
        DB.table("orders").having("total")


# --- writes ---------------------------------------------------------------


async def _widgets() -> None:
    await Schema.create(
        "widgets",
        lambda table: (
            table.id(),
            table.string("sku").unique(),
            table.integer("stock").default(0),
            table.integer("sold").default(0),
            table.text("meta").nullable(),
        ),
    )


async def test_insert_or_ignore_lets_a_collision_fall_on_the_floor(memory_db) -> None:
    await _widgets()
    assert await DB.table("widgets").insert_or_ignore({"sku": "A", "stock": 1}) == 1
    assert await DB.table("widgets").insert_or_ignore({"sku": "A", "stock": 9}) == 0
    assert await DB.table("widgets").insert_or_ignore([]) == 0
    assert await DB.table("widgets").where("sku", "A").value("stock") == 1


async def test_insert_using_fills_a_table_from_another_query(memory_db) -> None:
    await _widgets()
    await Schema.create("spares", lambda table: (table.id(), table.string("sku")))
    await DB.table("widgets").insert([{"sku": "A"}, {"sku": "B"}])
    assert await DB.table("spares").insert_using(["sku"], DB.table("widgets").select("sku")) == 2
    assert sorted(await DB.table("spares").pluck("sku")) == ["A", "B"]


async def test_update_or_insert_writes_either_way(memory_db) -> None:
    await _widgets()
    assert await DB.table("widgets").update_or_insert({"sku": "A"}, {"stock": 5}) is True
    assert await DB.table("widgets").update_or_insert({"sku": "A"}, {"stock": 9}) is True
    assert await DB.table("widgets").where("sku", "A").value("stock") == 9
    assert await DB.table("widgets").count() == 1


async def test_update_or_insert_with_nothing_to_update(memory_db) -> None:
    await _widgets()
    assert await DB.table("widgets").update_or_insert({"sku": "B"}) is True
    assert await DB.table("widgets").update_or_insert({"sku": "B"}) is True
    assert await DB.table("widgets").count() == 1


async def test_several_columns_can_move_in_one_statement(memory_db) -> None:
    await _widgets()
    await DB.table("widgets").insert({"sku": "A", "stock": 10, "sold": 1})
    await DB.table("widgets").increment_each({"stock": 5, "sold": 2})
    row = await DB.table("widgets").first()
    assert (row["stock"], row["sold"]) == (15, 3)
    await DB.table("widgets").decrement_each({"stock": 5}, sold=0)
    row = await DB.table("widgets").first()
    assert (row["stock"], row["sold"]) == (10, 0)


async def test_a_json_column_can_be_edited_in_place(memory_db) -> None:
    await _widgets()
    await DB.table("widgets").insert(
        {"sku": "A", "meta": json.dumps({"colour": "red", "tags": ["new"]})}
    )
    await DB.table("widgets").update({"meta->colour": "blue", "meta->tags": ["new", "sale"]})
    stored = json.loads(await DB.table("widgets").value("meta"))
    assert stored == {"colour": "blue", "tags": ["new", "sale"]}
    await DB.table("widgets").update({"meta->live": True, "sku": "B"})
    stored = json.loads(await DB.table("widgets").value("meta"))
    assert stored["live"] is True
    assert await DB.table("widgets").value("sku") == "B"


async def test_truncate_empties_the_table_and_restarts_the_ids(memory_db) -> None:
    await _widgets()
    await DB.table("widgets").insert([{"sku": "A"}, {"sku": "B"}])
    await DB.table("widgets").truncate()
    assert await DB.table("widgets").count() == 0
    await DB.table("widgets").insert({"sku": "C"})
    assert list(await DB.table("widgets").pluck("id")) == [1]


async def test_truncate_resets_an_autoincrementing_table_s_counter(memory_db) -> None:
    await DB.unprepared("create table tickets (id integer primary key autoincrement, tag text)")
    await DB.table("tickets").insert([{"tag": "a"}, {"tag": "b"}])
    await DB.table("tickets").truncate()
    await DB.table("tickets").insert({"tag": "c"})
    assert list(await DB.table("tickets").pluck("id")) == [1]


async def test_delete_takes_a_key_as_well_as_a_where(memory_db) -> None:
    await _widgets()
    await DB.table("widgets").insert([{"id": 1, "sku": "A"}, {"id": 2, "sku": "B"}])
    assert await DB.table("widgets").delete(1) == 1
    assert list(await DB.table("widgets").pluck("sku")) == ["B"]


# --- reads ----------------------------------------------------------------


async def test_sole_insists_on_exactly_one_row(memory_db) -> None:
    await _shop()
    assert (await customers().where("name", "Ada").sole())["name"] == "Ada"
    with pytest.raises(MultipleRecordsFoundError, match="not one"):
        await customers().sole()
    with pytest.raises(ModelNotFoundError):
        await customers().where("name", "Nobody").sole()


async def test_implode_joins_one_column_into_a_string(memory_db) -> None:
    await _shop()
    assert await customers().order_by("name").implode("name", ", ") == "Ada, Grace, Linus"
    await DB.table("customers").insert({"id": 4, "name": "Zed", "city": None})
    assert await customers().where("id", 4).implode("city") == ""


async def test_average_is_the_name_laravel_also_gives_avg(memory_db) -> None:
    await _shop()
    assert await DB.table("orders").average("total") == pytest.approx(130 / 3)


# --- reusable components and debugging ------------------------------------


async def test_tap_keeps_the_builder_and_pipe_gives_back_what_it_makes(memory_db) -> None:
    await _shop()

    def londoners(query: QueryBuilder) -> None:
        query.where("city", "London")

    assert await names_of(customers().tap(londoners)) == ["Ada"]
    assert await customers().tap(londoners).pipe(lambda query: query.count()) == 1


async def names_of(query: QueryBuilder) -> list[str]:
    return [row["name"] for row in await query.get()]


async def test_to_sql_leaves_placeholders_and_to_raw_sql_fills_them_in(memory_db) -> None:
    await _shop()
    query = customers().where("city", "London").where("id", ">", 0)
    assert "?" in query.to_sql()
    assert "London" not in query.to_sql()
    assert "'London'" in query.to_raw_sql()
    assert query.get_bindings() == ["London", 0]


async def test_dump_prints_the_query_and_keeps_building(memory_db, capsys) -> None:
    await _shop()
    query = customers().where("city", "London").dump().where("id", ">", 0)
    assert await names_of(query) == ["Ada"]
    assert query.dump_raw_sql() is query
    printed = capsys.readouterr()
    assert "London" in printed.out + printed.err


async def test_dd_prints_the_query_and_stops(memory_db, capsys) -> None:
    from almasix.debug import DumpAndDie

    await _shop()
    with pytest.raises(DumpAndDie):
        customers().where("city", "London").dd()
    with pytest.raises(DumpAndDie):
        customers().where("city", "London").dd_raw_sql()
    printed = capsys.readouterr()
    assert "London" in printed.out + printed.err


# --- scoped relationships ---------------------------------------------------


class Feature(Model):
    table = "features"
    timestamps = False
    fillable = ("name", "kind", "product_id")


class Product(Model):
    table = "products"
    timestamps = False
    fillable = ("name",)

    def features(self):
        return self.has_many(Feature, "product_id").with_attributes({"kind": "feature"})

    def bugs(self):
        return self.has_many(Feature, "product_id").with_attributes({"kind": "bug"})


async def _catalogue() -> None:
    await Schema.create("products", lambda table: (table.id(), table.string("name")))
    await Schema.create(
        "features",
        lambda table: (
            table.id(),
            table.string("name"),
            table.string("kind"),
            table.integer("product_id"),
        ),
    )


async def test_a_scoped_relation_creates_what_it_would_find(memory_db) -> None:
    await _catalogue()
    product = await Product.create(name="Smith")
    await product.features().create({"name": "Dark mode"})
    await product.bugs().create({"name": "Crash"})

    assert [f.name for f in await product.features().get()] == ["Dark mode"]
    assert [f.name for f in await product.bugs().get()] == ["Crash"]
    assert product.features().make({"name": "Draft"}).kind == "feature"


async def test_pending_attributes_seed_the_builders_own_creators(memory_db) -> None:
    await _catalogue()
    query = Feature.query().with_attributes({"kind": "bug"})
    assert query.pending_attributes() == {"kind": "bug"}
    made = await query.first_or_create({"name": "Crash"})
    assert made.kind == "bug"
    unsaved = await Feature.query().with_attributes({"kind": "bug"}).first_or_new({"name": "Draft"})
    assert unsaved.kind == "bug"
    upserted = (
        await Feature.query().with_attributes({"kind": "bug"}).update_or_create({"name": "Freeze"})
    )
    assert upserted.kind == "bug"


async def test_attributes_can_be_seeded_without_filtering(memory_db) -> None:
    await _catalogue()
    query = Feature.query().with_attributes({"kind": "bug"}, as_conditions=False)
    assert query.pending_attributes() == {"kind": "bug"}
    assert query.to_sql().count("?") == 0
