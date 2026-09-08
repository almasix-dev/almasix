"""M42 — the clauses each engine spells differently.

SQLite can run most of the query builder, so most tests run real queries.
These clauses cannot all be run here: MySQL's `MATCH ... AGAINST`, pgvector's
`<=>`, and PostgreSQL's `JSONB` operators need those engines in front of us.
What can be checked without them is that each dialect compiles to the SQL its
engine reads, and that an engine which cannot do the work says so instead of
compiling something that quietly means something else.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import mssql, mysql, postgresql, sqlite

from almasix.orm import DB
from almasix.orm.builder import QueryBuilder
from almasix.orm.grammar import UnsupportedByDialectError

MARIADB = mysql.dialect(is_mariadb=True)


def sql(query: QueryBuilder, dialect: object) -> str:
    return str(query.to_select().compile(dialect=dialect, compile_kwargs={"literal_binds": True}))


def users() -> QueryBuilder:
    return DB.table("users")


# --- JSON containment -------------------------------------------------------


def test_json_containment_per_engine() -> None:
    query = users().where_json_contains("options->languages", "en")
    assert "json_each" in sql(query, sqlite.dialect())
    assert 'JSON_CONTAINS(users.options, \'"en"\', \'$."languages"\')' in sql(query, mysql.dialect())
    assert "#> '{languages}'" in sql(query, postgresql.dialect())
    assert "@> CAST" in sql(query, postgresql.dialect())


def test_json_containment_at_the_document_root_on_postgres() -> None:
    query = users().where_json_contains("options", "en")
    compiled = sql(query, postgresql.dialect())
    assert "#>" not in compiled
    assert "CAST(users.options AS JSONB) @> CAST" in compiled


def test_json_key_existence_per_engine() -> None:
    query = users().where_json_contains_key("options->dining->meal")
    assert "JSON_TYPE" in sql(query, sqlite.dialect())
    assert "JSON_CONTAINS_PATH" in sql(query, mysql.dialect())
    assert "JSONB_PATH_EXISTS" in sql(query, postgresql.dialect())


def test_json_array_length_per_engine() -> None:
    query = users().where_json_length("options->languages", ">", 1)
    assert "JSON_ARRAY_LENGTH" in sql(query, sqlite.dialect())
    assert "JSON_LENGTH" in sql(query, mysql.dialect())
    assert "JSONB_ARRAY_LENGTH" in sql(query, postgresql.dialect())
    root = users().where_json_length("options", ">", 1)
    assert "#>" not in sql(root, postgresql.dialect())


def test_a_json_update_is_written_in_the_engine_s_own_function() -> None:
    def update(dialect: object) -> str:
        import sqlalchemy as sa

        from almasix.orm.builder import _json_set

        column = sa.column("options")
        expression = _json_set(column, [(["colour"], "blue")])
        return str(expression.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))

    assert "JSON_SET(options, '$.\"colour\"', JSON('\"blue\"'))" == update(sqlite.dialect())
    assert "CAST('\"blue\"' AS JSON)" in update(mysql.dialect())
    assert "JSONB_SET(CAST(options AS JSONB), '{colour}'" in update(postgresql.dialect())


# --- full text --------------------------------------------------------------


def test_full_text_search_in_each_mode_mysql_reads() -> None:
    natural = users().where_full_text(["title", "body"], "cat")
    assert "MATCH (users.title, users.body) AGAINST ('cat' IN NATURAL LANGUAGE MODE)" in sql(
        natural, mysql.dialect()
    )
    boolean = users().where_full_text("body", "+cat -dog", mode="boolean")
    assert "IN BOOLEAN MODE" in sql(boolean, mysql.dialect())
    assert "IN NATURAL LANGUAGE MODE WITH QUERY EXPANSION" in sql(
        users().where_full_text("body", "cat", mode="expanded"), mysql.dialect()
    )


def test_full_text_search_in_each_mode_postgres_reads() -> None:
    plain = users().where_full_text(["title", "body"], "cat")
    compiled = sql(plain, postgresql.dialect())
    assert "TO_TSVECTOR('english', users.title) || TO_TSVECTOR('english', users.body)" in compiled
    assert "PLAINTO_TSQUERY('english', 'cat')" in compiled
    assert "PHRASETO_TSQUERY" in sql(
        users().where_full_text("body", "cat", mode="phrase"), postgresql.dialect()
    )
    assert "WEBSEARCH_TO_TSQUERY" in sql(
        users().where_full_text("body", "cat", mode="websearch"), postgresql.dialect()
    )
    assert "TO_TSVECTOR('french'" in sql(
        users().where_full_text("body", "chat", language="french"), postgresql.dialect()
    )


def test_or_where_full_text_joins_with_or() -> None:
    query = users().where("id", 1).or_where_full_text("body", "cat")
    assert " OR MATCH" in sql(query, mysql.dialect())


def test_an_engine_without_a_full_text_index_says_so() -> None:
    with pytest.raises(UnsupportedByDialectError, match="full-text search"):
        sql(users().where_full_text("body", "cat"), sqlite.dialect())


# --- vectors ----------------------------------------------------------------


def test_vector_distance_on_pgvector_and_mariadb() -> None:
    query = users().where_vector_similar_to("embedding", [0.1, 0.2], min_similarity=0.8)
    compiled = sql(query, postgresql.dialect())
    assert "users.embedding <=> CAST('[0.1,0.2]' AS VECTOR)" in compiled
    assert "ORDER BY" in compiled
    assert "VEC_DISTANCE_COSINE" in sql(query, MARIADB)


def test_a_vector_search_need_not_order_by_distance() -> None:
    query = users().where_vector_similar_to("embedding", [0.1, 0.2], order=False)
    assert "ORDER BY" not in sql(query, postgresql.dialect())


def test_a_vector_may_arrive_already_written_out() -> None:
    query = users().select_vector_distance("embedding", "[0.1,0.2]", alias="d")
    assert "AS d" in sql(query, postgresql.dialect())


def test_distance_can_be_selected_bounded_and_ordered_by() -> None:
    bounded = users().where_vector_distance_less_than("embedding", [0.1], 0.25)
    assert "<=> CAST('[0.1]' AS VECTOR)) < 0.25" in sql(bounded, postgresql.dialect())
    ordered = users().order_by_vector_distance("embedding", [0.1], direction="desc")
    assert "DESC" in sql(ordered, postgresql.dialect())
    assert "ASC" in sql(users().order_by_vector_distance("embedding", [0.1]), postgresql.dialect())


def test_engines_without_vectors_say_so() -> None:
    query = users().order_by_vector_distance("embedding", [0.1])
    with pytest.raises(UnsupportedByDialectError, match="vector distance"):
        sql(query, sqlite.dialect())
    with pytest.raises(UnsupportedByDialectError, match="MySQL"):
        sql(query, mysql.dialect())


# --- case-sensitive like ----------------------------------------------------


def test_case_sensitivity_is_only_mysql_s_to_ask_for() -> None:
    query = users().where_like("name", "Ada%", case_sensitive=True)
    assert "users.name LIKE BINARY" in sql(query, mysql.dialect())
    assert "users.name LIKE " in sql(query, postgresql.dialect())
    negated = users().where_not_like("name", "Ada%", case_sensitive=True)
    assert "NOT LIKE BINARY" in sql(negated, mysql.dialect())
    assert "NOT LIKE 'Ada%'" in sql(negated, sqlite.dialect())


# --- writes that differ ------------------------------------------------------


def test_truncate_is_a_delete_on_sqlite_and_a_truncate_elsewhere() -> None:
    from almasix.orm.builder import _truncate_sql

    assert _truncate_sql("users", sqlite.dialect()) == ['DELETE FROM "users"']
    assert _truncate_sql("users", postgresql.dialect()) == [
        'TRUNCATE TABLE "users" RESTART IDENTITY CASCADE'
    ]
    assert _truncate_sql("users", mysql.dialect()) == ["TRUNCATE TABLE `users`"]
    assert _truncate_sql("users", mssql.dialect()) == ["TRUNCATE TABLE [users]"]


def test_insert_or_ignore_needs_an_engine_that_knows_conflicts() -> None:
    import sqlalchemy as sa

    from almasix.orm.builder import _ignoring_insert

    table = sa.table("users", sa.column("id"))
    payload = [{"id": 1}]
    assert "ON CONFLICT DO NOTHING" in str(_ignoring_insert(table, payload, "sqlite"))
    assert "IGNORE" in str(_ignoring_insert(table, payload, "mysql"))
    assert "ON CONFLICT DO NOTHING" in str(_ignoring_insert(table, payload, "postgresql"))
    with pytest.raises(UnsupportedByDialectError, match="insert-or-ignore"):
        _ignoring_insert(table, payload, "mssql")


# --- path splitting ----------------------------------------------------------


def test_a_json_path_is_read_the_way_laravel_writes_one() -> None:
    from almasix.orm.grammar import is_json_path, split_json_path

    assert split_json_path("options->dining->meal") == ("options", ["dining", "meal"])
    assert split_json_path("options") == ("options", [])
    assert split_json_path("options->") == ("options", [])
    assert is_json_path("options->meal") is True
    assert is_json_path("options") is False
    assert is_json_path(None) is False


def test_engines_without_json_functions_say_so() -> None:
    for query in (
        users().where_json_contains("options->languages", "en"),
        users().where_json_contains_key("options->meal"),
        users().where_json_length("options->languages", ">", 1),
    ):
        with pytest.raises(UnsupportedByDialectError, match="JSON"):
            sql(query, mssql.dialect())

    import sqlalchemy as sa

    from almasix.orm.builder import _json_set

    expression = _json_set(sa.column("options"), [(["colour"], "blue")])
    with pytest.raises(UnsupportedByDialectError, match="JSON update"):
        expression.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": True})


def test_a_json_read_is_typed_by_what_it_is_compared_against() -> None:
    import sqlalchemy as sa

    from almasix.orm.grammar import json_value

    column = sa.column("options")
    assert json_value(column, ["votes"], 1).type.python_type is int
    assert json_value(column, ["enabled"], True).type.python_type is bool
    assert json_value(column, ["ratio"], 1.5).type.python_type is float
    assert json_value(column, ["meal"], "salad").type.python_type is str
    assert "options" in str(json_value(column, ["dining", "meal"], "salad"))


def test_the_error_names_the_operation_and_the_engine() -> None:
    error = UnsupportedByDialectError("vector distance", "sqlite")
    assert str(error) == "sqlite has no vector distance support."
    assert (error.operation, error.dialect) == ("vector distance", "sqlite")
