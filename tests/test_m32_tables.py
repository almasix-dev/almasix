"""M32 — the `*:table` commands, and the database session driver they serve.

A migration these commands write has to create the table the driver reads, so
each test runs the migration and then drives the feature against it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from almasix.console.kernel import ConsoleKernel
from almasix.session.handlers import DatabaseSessionHandler, resolve_session_handler

pytest_plugins = ["tests.orm_support"]

TABLE_COMMANDS = [
    ("cache:table", "create_cache_table", ("cache", "cache_locks")),
    ("queue:table", "create_jobs_table", ("jobs",)),
    ("queue:failed-table", "create_failed_jobs_table", ("failed_jobs",)),
    ("session:table", "create_sessions_table", ("sessions",)),
    ("notifications:table", "create_notifications_table", ("notifications",)),
]


@pytest.fixture()
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ConsoleKernel:
    monkeypatch.chdir(tmp_path)
    built = ConsoleKernel.for_cwd(tmp_path)
    built.discover_framework_commands()
    return built


@pytest.mark.parametrize(("command", "slug", "tables"), TABLE_COMMANDS)
def test_each_table_command_writes_a_migration_for_its_tables(
    kernel: ConsoleKernel,
    tmp_path: Path,
    command: str,
    slug: str,
    tables: tuple[str, ...],
) -> None:
    assert kernel.run_argv(command, []) == 0

    written = list((tmp_path / "database" / "migrations").glob(f"*_{slug}.py"))
    assert len(written) == 1
    body = written[0].read_text(encoding="utf-8")
    for table in tables:
        assert f'Schema.create("{table}"' in body
    assert "class Create" in body

    # The file has to be importable, or `smith migrate` would skip it.
    spec = importlib.util.spec_from_file_location(f"m32_{slug}", written[0])
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def test_the_sessions_migration_carries_the_columns_laravel_stores(
    kernel: ConsoleKernel,
    tmp_path: Path,
) -> None:
    assert kernel.run_argv("session:table", []) == 0
    body = next(
        (tmp_path / "database" / "migrations").glob("*_create_sessions_table.py")
    ).read_text()

    for column in ("user_id", "ip_address", "user_agent", "payload", "last_activity"):
        assert column in body


# -- the database session driver --------------------------------------------


class FakeRequest:
    """Just enough request for a session handler."""

    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.cookies = cookies or {}

    def cookie(self, key: str, default: object = None) -> object:
        return self.cookies.get(key, default)

    def ip(self) -> str:
        return "203.0.113.9"

    def user_agent(self) -> str:
        return "pytest/1.0"


class FakeResponse:
    """Records the cookies a handler sets."""

    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}

    def set_cookie(self, name: str, value: str, **_kwargs: object) -> None:
        self.cookies[name] = value


async def _sessions_table() -> None:
    from almasix.orm.schema import Schema

    await Schema.create(
        "sessions",
        lambda table: (
            table.string("id").primary(),
            table.integer("user_id").nullable(),
            table.string("ip_address", 45).nullable(),
            table.text("user_agent").nullable(),
            table.text("payload"),
            table.integer("last_activity"),
        ),
    )


async def test_a_session_round_trips_through_the_table(memory_db) -> None:
    from almasix.orm.facade import DB

    await _sessions_table()
    handler = DatabaseSessionHandler()
    response = FakeResponse()

    session_id = await handler.write(
        response,
        session_id=None,
        data={"cart": [1, 2], "login_web": {"id": 7, "email": "a@b.c"}},
        key="k" * 32,
        cookie_name="almasix_session",
        lifetime=600,
        path="/",
        secure=False,
        dirty=True,
        had_prior=False,
    )
    assert session_id

    row = await DB.table("sessions").where("id", session_id).first()
    assert row is not None
    assert json.loads(row["payload"])["cart"] == [1, 2]
    # The row is attributable: the guard's payload names the user.
    assert int(row["user_id"]) == 7

    request = FakeRequest({"almasix_session": response.cookies["almasix_session"]})
    read_id, data = await handler.read(
        request, key="k" * 32, cookie_name="almasix_session", lifetime=600
    )
    assert read_id == session_id
    assert data == {"cart": [1, 2], "login_web": {"id": 7, "email": "a@b.c"}}

    # Writing again keeps one row per session, and records the caller.
    await handler.write(
        response,
        session_id=session_id,
        data={"cart": [3]},
        key="k" * 32,
        cookie_name="almasix_session",
        lifetime=600,
        path="/",
        secure=False,
        dirty=True,
        had_prior=True,
    )
    assert await DB.table("sessions").count() == 1
    again = await DB.table("sessions").where("id", session_id).first()
    assert again["ip_address"] == "203.0.113.9"
    assert again["user_agent"] == "pytest/1.0"

    await handler.destroy(session_id)
    assert await DB.table("sessions").count() == 0


async def test_an_expired_row_is_deleted_rather_than_read(memory_db) -> None:
    import time

    from almasix.orm.facade import DB
    from almasix.session.signing import sign_payload

    await _sessions_table()
    handler = DatabaseSessionHandler()
    await DB.table("sessions").insert(
        [
            {
                "id": "old",
                "user_id": None,
                "ip_address": None,
                "user_agent": None,
                "payload": "{}",
                "last_activity": int(time.time()) - 5000,
            }
        ]
    )
    cookie = sign_payload({"id": "old"}, key="k" * 32, max_age=600)

    found, data = await handler.read(
        FakeRequest({"almasix_session": cookie}),
        key="k" * 32,
        cookie_name="almasix_session",
        lifetime=60,
    )

    assert (found, data) == ("old", None)
    assert await DB.table("sessions").count() == 0


async def test_unreadable_and_absent_cookies_start_a_new_session(memory_db) -> None:
    from almasix.orm.facade import DB
    from almasix.session.signing import sign_payload

    await _sessions_table()
    handler = DatabaseSessionHandler()
    read = lambda request: handler.read(
        request, key="k" * 32, cookie_name="almasix_session", lifetime=600
    )

    assert await read(FakeRequest()) == (None, None)
    assert await read(FakeRequest({"almasix_session": "not-a-signed-value"})) == (None, None)
    assert await read(
        FakeRequest({"almasix_session": sign_payload({}, key="k" * 32, max_age=600)})
    ) == (None, None)
    # Signed, a dictionary, and still no id to look a row up by.
    assert await read(
        FakeRequest({"almasix_session": sign_payload({"id": ""}, key="k" * 32, max_age=600)})
    ) == (None, None)
    # A cookie whose row is gone keeps the id and starts empty.
    cookie = sign_payload({"id": "vanished"}, key="k" * 32, max_age=600)
    assert await read(FakeRequest({"almasix_session": cookie})) == ("vanished", None)

    # A row holding something that is not JSON is not a session.
    await DB.table("sessions").insert(
        [
            {
                "id": "broken",
                "user_id": None,
                "ip_address": None,
                "user_agent": None,
                "payload": "{oh no",
                "last_activity": 4102444800,
            }
        ]
    )
    broken = sign_payload({"id": "broken"}, key="k" * 32, max_age=600)
    assert await read(FakeRequest({"almasix_session": broken})) == ("broken", None)


async def test_an_untouched_session_writes_nothing(memory_db) -> None:
    from almasix.orm.facade import DB

    await _sessions_table()
    handler = DatabaseSessionHandler()

    assert (
        await handler.write(
            FakeResponse(),
            session_id=None,
            data={},
            key="k" * 32,
            cookie_name="almasix_session",
            lifetime=600,
            path="/",
            secure=False,
            dirty=False,
            had_prior=False,
        )
        is None
    )
    assert await DB.table("sessions").count() == 0
    await handler.destroy(None)


def test_a_row_with_no_readable_timestamp_is_not_treated_as_expired() -> None:
    # A hand-edited row, or one migrated from another handler, should be read
    # rather than deleted for a column nothing can compare.
    from almasix.session.handlers import _expired

    assert _expired(None, 600) is False
    assert _expired("whenever", 600) is False
    assert _expired(0, 600) is True


def test_the_driver_is_chosen_by_configuration(monkeypatch) -> None:
    from almasix.config import ConfigRepository, set_repository

    repository = ConfigRepository()
    repository.set("session.driver", "database")
    repository.set("session.table", "web_sessions")
    repository.set("session.connection", "primary")
    set_repository(repository)
    try:
        handler = resolve_session_handler()
        assert isinstance(handler, DatabaseSessionHandler)
        assert handler.table == "web_sessions"
        assert handler.connection == "primary"
    finally:
        set_repository(None)
