"""M42 — the database layer under the query builder.

Read/write splitting, listening, pretending, and transactions opened by hand:
the parts of Laravel's Database chapter that are about the connection rather
than the query.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from almasix.orm import DB, DatabaseManager, Schema, set_manager
from almasix.orm.connection import (
    Connection,
    ConnectionError_,
    PretendResult,
    QueryExecuted,
    _quote_binding,
    reset_total_query_duration,
)
from tests.orm_support import memory_db  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _people() -> None:
    await Schema.create("people", lambda table: (table.id(), table.string("name")))


@pytest.fixture(autouse=True)
async def _quiet_listeners(memory_db):
    reset_total_query_duration()
    yield
    memory_db.flush_listeners()
    reset_total_query_duration()


# --- running statements ------------------------------------------------------


async def test_the_facade_runs_each_kind_of_statement(memory_db) -> None:
    await _people()
    assert await DB.insert("insert into people (name) values ('Ada')") is True
    assert await DB.statement("insert into people (name) values ('Grace')") == 1
    assert await DB.scalar("select count(*) from people") == 2
    assert (await DB.select("select name from people order by name"))[0]["name"] == "Ada"
    assert (await DB.select_one("select name from people order by name"))["name"] == "Ada"
    assert await DB.update("update people set name = 'Ada L.' where name = 'Ada'") == 1
    assert await DB.delete("delete from people where name = 'Grace'") == 1
    assert await DB.scalar("select count(*) from people") == 1


async def test_unprepared_runs_sql_a_driver_would_refuse_to_prepare(memory_db) -> None:
    assert await DB.unprepared("create table settings (id integer primary key)") is True
    assert await DB.scalar("select count(*) from settings") == 0


async def test_scalar_of_nothing_is_nothing(memory_db) -> None:
    await _people()
    assert await DB.scalar("select name from people") is None
    assert await DB.select_one("select name from people") is None


async def test_a_connection_streams_rows_without_buffering_them(memory_db) -> None:
    await _people()
    await DB.table("people").insert([{"name": "Ada"}, {"name": "Grace"}])
    seen = [row["name"] async for row in DB.connection().stream("select name from people")]
    assert seen == ["Ada", "Grace"]


# --- read / write splitting ---------------------------------------------------


def _split_manager(**extra: object) -> DatabaseManager:
    return DatabaseManager(
        {
            "default": "split",
            "connections": {
                "split": {
                    "driver": "sqlite",
                    "database": ":memory:",
                    "read": {"database": ":memory:"},
                    "write": {"database": ":memory:"},
                    **extra,
                }
            },
        }
    )


async def test_a_read_block_gives_reads_an_engine_of_their_own() -> None:
    connection = _split_manager().connection()
    assert connection.read_engine is not connection.engine
    await connection.disconnect()


async def test_a_connection_without_a_read_block_has_one_engine(memory_db) -> None:
    connection = DB.connection()
    assert connection.read_engine is connection.engine


async def test_sticky_sends_a_writer_s_own_reads_to_the_write_engine() -> None:
    manager = _split_manager(sticky=True)
    set_manager(manager)
    try:
        connection = manager.connection()
        assert connection.read_engine is not connection.engine
        await connection.execute("create table t (id integer)")
        assert connection.read_engine is connection.engine
    finally:
        await manager.disconnect()
        set_manager(None)


async def test_a_connection_name_that_is_not_configured_says_so(memory_db) -> None:
    with pytest.raises(ConnectionError_, match="not configured"):
        DB.connection("nowhere")


# --- listening ----------------------------------------------------------------


async def test_a_listener_hears_every_statement(memory_db) -> None:
    await _people()
    heard: list[QueryExecuted] = []
    DB.listen(heard.append)
    await DB.table("people").insert({"name": "Ada"})
    await DB.table("people").where("name", "Ada").get()

    assert len(heard) == 2
    assert heard[0].connection_name == "sqlite"
    assert "INSERT INTO people" in heard[0].sql
    assert heard[0].bindings == ["Ada"]
    assert heard[1].time >= 0.0


async def test_an_event_can_write_its_own_bindings_back_in() -> None:
    event = QueryExecuted(
        sql="select * from people where name = ? and votes > ? and active = ? and note = ?",
        bindings=["O'Hara", 10, True, None],
        time=1.0,
        connection_name="sqlite",
    )
    assert event.to_raw_sql().endswith("name = 'O''Hara' and votes > 10 and active = true and note = null")
    assert _quote_binding(1.5) == "1.5"
    assert _quote_binding(False) == "false"


async def test_a_slow_context_is_reported_once_it_passes_the_budget(memory_db) -> None:
    await _people()
    reports: list[tuple[str, str]] = []
    DB.when_querying_for_longer_than(
        0, lambda connection, event: reports.append((connection.name, event.sql))
    )
    await DB.table("people").get()
    assert reports and reports[0][0] == "sqlite"
    assert DB.total_query_duration() > 0

    DB.reset_total_query_duration()
    assert DB.total_query_duration() == 0.0


async def test_a_generous_budget_reports_nothing(memory_db) -> None:
    await _people()
    reports: list[str] = []
    DB.when_querying_for_longer_than(60_000, lambda _connection, event: reports.append(event.sql))
    await DB.table("people").get()
    assert reports == []


async def test_listeners_can_be_forgotten(memory_db) -> None:
    await _people()
    heard: list[QueryExecuted] = []
    DB.listen(heard.append)
    memory_db.flush_listeners()
    await DB.table("people").get()
    assert heard == []


async def test_an_uncompilable_statement_is_still_described(memory_db) -> None:
    await _people()
    heard: list[QueryExecuted] = []
    DB.listen(heard.append)
    await DB.connection().execute(sa.text("select :n as n"), {"n": 1})
    assert heard[-1].bindings == [1]

    # A listener must never be the reason a query fails, even when whatever
    # ran cannot be compiled for reading.
    class Unreadable:
        def __str__(self) -> str:
            return "something the compiler cannot read"

    described = DB.connection()._describe(Unreadable(), None, 2.5)
    assert described.sql == "something the compiler cannot read"
    assert described.bindings == []
    assert described.time == 2.5


# --- pretending ----------------------------------------------------------------


async def test_pretend_collects_the_queries_instead_of_running_them(memory_db) -> None:
    await _people()

    async def work() -> None:
        await DB.table("people").insert({"name": "Ada"})
        await DB.unprepared("delete from people")

    queries = await DB.pretend(work)
    assert [query.sql.split()[0] for query in queries] == ["INSERT", "delete"]
    assert queries[0].bindings == ["Ada"]
    assert await DB.table("people").count() == 0


async def test_pretend_hands_the_connection_to_a_callback_that_wants_it(memory_db) -> None:
    await _people()
    queries = await DB.pretend(lambda connection: connection.execute("delete from people"))
    assert queries[0].sql == "delete from people"


async def test_pretend_takes_a_callback_that_is_not_a_coroutine(memory_db) -> None:
    await _people()
    assert await DB.pretend(lambda: None) == []


async def test_a_pretended_result_answers_like_an_empty_one() -> None:
    result = PretendResult()
    assert result.rowcount == 0
    assert result.lastrowid is None
    assert result.mappings().all() == []
    assert result.scalar() is None


# --- transactions ---------------------------------------------------------------


async def test_a_transaction_block_commits_and_rolls_back(memory_db) -> None:
    await _people()
    async with DB.transaction():
        await DB.table("people").insert({"name": "Ada"})
    assert await DB.table("people").count() == 1

    with pytest.raises(RuntimeError, match="no"):
        async with DB.transaction():
            await DB.table("people").insert({"name": "Grace"})
            raise RuntimeError("no")
    assert await DB.table("people").count() == 1


async def test_a_transaction_callback_runs_and_gives_back_what_it_returns(memory_db) -> None:
    await _people()

    async def work() -> str:
        await DB.table("people").insert({"name": "Ada"})
        return "done"

    assert await DB.transaction(work) == "done"
    assert await DB.table("people").count() == 1


async def test_a_transaction_callback_need_not_be_a_coroutine(memory_db) -> None:
    await _people()
    assert await DB.transaction(lambda: "plain") == "plain"


async def test_a_transaction_callback_may_take_the_handle(memory_db) -> None:
    await _people()

    async def work(handle) -> int:
        await handle.execute(sa.text("insert into people (name) values ('Ada')"))
        return DB.transaction_level()

    assert await DB.transaction(work) == 1


async def test_a_deadlock_is_retried_and_then_given_up_on(memory_db) -> None:
    await _people()
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("Deadlock found when trying to get lock")
        return "through"

    assert await DB.transaction(flaky, attempts=5) == "through"
    assert attempts == 3

    async def always() -> None:
        raise RuntimeError("deadlock detected")

    with pytest.raises(RuntimeError, match="deadlock detected"):
        await DB.transaction(always, attempts=2)


async def test_an_ordinary_failure_is_not_retried(memory_db) -> None:
    await _people()
    attempts = 0

    async def broken() -> None:
        nonlocal attempts
        attempts += 1
        raise ValueError("not a deadlock")

    with pytest.raises(ValueError):
        await DB.transaction(broken, attempts=5)
    assert attempts == 1


async def test_a_transaction_awaited_without_a_callback_says_what_is_missing(memory_db) -> None:
    with pytest.raises(TypeError, match="needs a callback"):
        await DB.transaction()


async def test_transactions_opened_by_hand_are_closed_by_hand(memory_db) -> None:
    await _people()
    assert DB.transaction_level() == 0
    await DB.begin_transaction()
    assert DB.transaction_level() == 1
    await DB.table("people").insert({"name": "Ada"})
    await DB.rollback()
    assert DB.transaction_level() == 0
    assert await DB.table("people").count() == 0

    await DB.begin_transaction()
    await DB.table("people").insert({"name": "Grace"})
    await DB.commit()
    assert await DB.table("people").count() == 1


async def test_hand_opened_transactions_nest_with_savepoints(memory_db) -> None:
    await _people()
    await DB.begin_transaction()
    await DB.table("people").insert({"name": "Ada"})
    await DB.begin_transaction()
    assert DB.transaction_level() == 2
    await DB.table("people").insert({"name": "Grace"})
    await DB.rollback()
    await DB.commit()
    assert list(await DB.table("people").pluck("name")) == ["Ada"]


async def test_a_nested_hand_opened_transaction_commits_into_the_outer_one(memory_db) -> None:
    await _people()
    await DB.begin_transaction()
    await DB.begin_transaction()
    await DB.table("people").insert({"name": "Ada"})
    await DB.commit()
    assert DB.transaction_level() == 1
    await DB.commit()
    assert list(await DB.table("people").pluck("name")) == ["Ada"]


async def test_a_hand_opened_transaction_inside_a_block_is_a_savepoint(memory_db) -> None:
    await _people()
    async with DB.transaction():
        await DB.table("people").insert({"name": "Ada"})
        await DB.begin_transaction()
        await DB.table("people").insert({"name": "Grace"})
        await DB.rollback()
        await DB.table("people").insert({"name": "Linus"})
    assert sorted(await DB.table("people").pluck("name")) == ["Ada", "Linus"]


async def test_a_block_transaction_after_a_hand_opened_one_still_defers(memory_db) -> None:
    await _people()
    ran: list[str] = []
    await DB.begin_transaction()
    await DB.commit()

    async with DB.transaction():
        DB.after_commit(lambda: ran.append("sent"))
        assert ran == []
    assert ran == ["sent"]


async def test_committing_nothing_says_there_is_nothing(memory_db) -> None:
    with pytest.raises(RuntimeError, match="no transaction"):
        await DB.commit()
    with pytest.raises(RuntimeError, match="no transaction"):
        await DB.rollback()


async def test_a_nested_block_transaction_is_a_savepoint(memory_db) -> None:
    await _people()
    async with DB.transaction():
        await DB.table("people").insert({"name": "Ada"})
        with pytest.raises(RuntimeError):
            async with DB.transaction():
                await DB.table("people").insert({"name": "Grace"})
                raise RuntimeError("undo the inner one")
    assert list(await DB.table("people").pluck("name")) == ["Ada"]


async def test_in_transaction_says_whether_one_is_open(memory_db) -> None:
    connection = DB.connection()
    assert connection.in_transaction() is False
    async with DB.transaction():
        assert connection.in_transaction() is True


# --- after commit -----------------------------------------------------------------


async def test_after_commit_waits_for_the_commit(memory_db) -> None:
    await _people()
    ran: list[str] = []
    async with DB.transaction():
        DB.after_commit(lambda: ran.append("sent"))
        assert ran == []
    assert ran == ["sent"]


async def test_after_commit_outside_a_transaction_runs_now(memory_db) -> None:
    ran: list[str] = []
    DB.after_commit(lambda: ran.append("sent"))
    assert ran == ["sent"]


async def test_a_rollback_throws_the_deferred_work_away(memory_db) -> None:
    await _people()
    ran: list[str] = []
    with pytest.raises(RuntimeError):
        async with DB.transaction():
            DB.after_commit(lambda: ran.append("sent"))
            raise RuntimeError("no")
    assert ran == []


async def test_deferred_work_survives_a_hand_opened_commit(memory_db) -> None:
    await _people()
    ran: list[str] = []
    await DB.begin_transaction()
    DB.after_commit(lambda: ran.append("sent"))
    await DB.commit()
    assert ran == ["sent"]

    await DB.begin_transaction()
    DB.after_commit(lambda: ran.append("never"))
    await DB.rollback()
    assert ran == ["sent"]


# --- pooled connections -------------------------------------------------------------


def _pooled_manager() -> DatabaseManager:
    return DatabaseManager(
        {
            "default": "pgbouncer",
            "connections": {
                "pgbouncer": {
                    "driver": "pgsql",
                    "host": "pooler.example.com",
                    "port": 6543,
                    "database": "app",
                    "username": "app",
                    "password": "secret",
                    "pooled": True,
                    "direct": {"host": "db.example.com", "port": 5432},
                },
                "plain": {"driver": "sqlite", "database": ":memory:"},
            },
        }
    )


async def test_a_pooled_connection_has_a_direct_twin_for_schema_work() -> None:
    manager = _pooled_manager()
    assert manager.direct_name() == "pgbouncer::direct"
    assert manager.direct_name("plain") == "plain"
    assert manager.direct_name("pgbouncer::direct") == "pgbouncer::direct"

    direct = manager._definition("pgbouncer::direct")
    assert (direct["host"], direct["port"]) == ("db.example.com", 5432)
    assert direct["database"] == "app"
    assert "direct" not in direct


async def test_the_pooled_definition_itself_still_points_at_the_pooler() -> None:
    manager = _pooled_manager()
    assert manager._definition("pgbouncer")["host"] == "pooler.example.com"
    with pytest.raises(ConnectionError_, match="not configured"):
        manager._definition("missing::direct")


# --- manager plumbing -----------------------------------------------------------------


async def test_a_connection_built_by_hand_records_nothing_and_still_runs() -> None:
    from almasix.orm import facade

    previous = facade._manager
    facade._manager = None
    connection = Connection("standalone", {"driver": "sqlite", "database": ":memory:"})
    try:
        await connection.execute("create table t (id integer)")
        assert await connection.scalar("select count(*) from t") == 0
    finally:
        await connection.disconnect()
        facade._manager = previous


async def test_the_facade_refuses_to_guess_at_a_manager() -> None:
    from almasix.orm import facade

    previous = facade._manager
    set_manager(None)
    try:
        with pytest.raises(RuntimeError, match="not configured"):
            facade.get_manager()
    finally:
        facade._manager = previous


async def test_raw_sql_passes_straight_through(memory_db) -> None:
    await _people()
    await DB.table("people").insert({"name": "Ada"})
    rows = await DB.table("people").select(DB.raw("upper(name) as shout")).get()
    assert rows[0]["shout"] == "ADA"
