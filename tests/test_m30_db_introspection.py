"""M30 — the read-only database commands: ``db:show``, ``db:table``, ``db:monitor``.

Every test runs against a real SQLite file with four tables, an index, a
cascading foreign key, and a column default, so the output is whatever the
dialect actually reports. The rest of the file holds that line: what SQLite
cannot answer — custom types, server sessions — comes back as a stated reason.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from almasix.cache.helpers import set_manager as set_cache_manager
from almasix.console.commands.db_introspection import _SESSION_COUNT_SQL, _custom_types
from almasix.console.kernel import ConsoleKernel
from almasix.orm.facade import DB, set_manager
from almasix.orm.schema import Blueprint, Schema

Build = Callable[..., ConsoleKernel]


def write_app(root: Path, *, database: str) -> None:
    """The smallest tree ``ConsoleKernel.from_cwd`` will boot as an application."""
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap").mkdir(exist_ok=True)
    (root / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    files = {
        "app.py": 'config = {"name": "M30", "env": "local", "debug": False, "providers": []}\n',
        "logging.py": "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        "database.py": (
            "config = {'default': 'sqlite', 'connections': {"
            f"'sqlite': {{'driver': 'sqlite', 'database': {database!r}}}, "
            "'archive': {'driver': 'sqlite', 'database': ':memory:'}"
            "}}\n"
        ),
    }
    for name, body in files.items():
        (root / "config" / name).write_text(body, encoding="utf-8")


def make_schema() -> None:
    """Four tables: a unique index, a cascading key, a default, and a bare log."""

    def users(table: Blueprint) -> None:
        table.id()
        table.string("email")
        table.unique("email")

    def posts(table: Blueprint) -> None:
        table.id()
        table.string("title")
        table.text("body").nullable()
        table.foreign_id("user_id").constrained("users").cascade_on_delete()

    async def build() -> None:
        await Schema.create("users", users)
        await Schema.create("posts", posts)
        await DB.statement(
            "CREATE TABLE settings (name TEXT PRIMARY KEY, value TEXT DEFAULT 'on' NOT NULL)"
        )
        await DB.statement("CREATE TABLE logs (message TEXT)")
        await DB.statement("INSERT INTO users (email) VALUES ('one@example.com')")
        await DB.statement("INSERT INTO users (email) VALUES ('two@example.com')")
        await DB.statement("INSERT INTO posts (title, user_id) VALUES ('Hello', 1)")

    asyncio.run(build())


def make_view() -> None:
    asyncio.run(DB.statement("CREATE VIEW recent_posts AS SELECT id, title FROM posts"))


def cells(output: str) -> list[list[str]]:
    """Every line as its whitespace-separated cells, so padding is not asserted."""
    return [line.split() for line in output.splitlines()]


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Build]:
    """A booted application over a temporary SQLite file.

    The teardown drops the database manager as well as the cache one: these
    tables are the only ones in the suite with rows in them, and a later test
    reflecting a model must not find this test's ``users`` table waiting.
    """

    def make(*, database: str | None = None) -> ConsoleKernel:
        write_app(tmp_path, database=database or str(tmp_path / "database" / "app.sqlite"))
        monkeypatch.chdir(tmp_path)
        return ConsoleKernel.from_cwd(tmp_path)

    yield make
    asyncio.run(DB.disconnect())
    set_manager(None)
    set_cache_manager(None)


@pytest.fixture
def kernel(build: Build) -> ConsoleKernel:
    built = build()
    make_schema()
    return built


# --- db:show --------------------------------------------------------------


def test_db_show_reports_the_driver_the_file_and_every_configured_connection(
    kernel: ConsoleKernel, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", []) == 0

    out = capsys.readouterr().out
    assert ["Name", "sqlite"] in cells(out)
    assert ["Driver", "sqlite"] in cells(out)
    assert ["Database", str(tmp_path / "database" / "app.sqlite")] in cells(out)
    assert "archive, sqlite" in out
    assert ["Tables", "4"] in cells(out)


def test_db_show_leaves_out_the_rows_a_file_database_cannot_answer(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """SQLite has no host, port, or user, so those rows are absent, not blank."""
    assert kernel.run_argv("db:show", []) == 0

    out = capsys.readouterr().out
    assert "Host" not in out
    assert "Port" not in out
    assert "Username" not in out


def test_db_show_lists_every_table_with_its_row_count(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", ["--counts"]) == 0

    rows = cells(capsys.readouterr().out)
    assert ["Table", "Rows"] in rows
    assert ["users", "2"] in rows
    assert ["posts", "1"] in rows
    assert ["settings", "0"] in rows
    assert ["logs", "0"] in rows


def test_db_show_does_not_count_rows_unless_asked(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each count is a full scan, so ``--counts`` is the only way to pay for it."""
    assert kernel.run_argv("db:show", []) == 0

    rows = cells(capsys.readouterr().out)
    assert ["Table"] in rows
    assert ["users"] in rows
    assert ["users", "2"] not in rows


def test_db_show_outputs_the_whole_overview_as_json(
    kernel: ConsoleKernel, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", ["--counts", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "sqlite"
    assert payload["driver"] == "sqlite"
    assert payload["database"] == str(tmp_path / "database" / "app.sqlite")
    assert payload["connections"] == ["archive", "sqlite"]
    assert {"table": "users", "rows": 2} in payload["tables"]
    assert "host" not in payload


def test_db_show_lists_the_views_when_asked(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    make_view()

    assert kernel.run_argv("db:show", ["--views"]) == 0

    out = capsys.readouterr().out
    assert "Views" in out
    assert "recent_posts" in out


def test_db_show_says_a_database_has_no_views_rather_than_printing_nothing(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", ["--views"]) == 0
    assert "(none)" in capsys.readouterr().out


def test_db_show_refuses_to_list_custom_types_on_sqlite(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """Only PostgreSQL's inspector reports types; the rest say so and list none."""
    assert kernel.run_argv("db:show", ["--types"]) == 0

    out = capsys.readouterr().out
    assert "--types cannot be honoured on sqlite" in out
    assert "Types" not in out


def test_db_show_records_the_types_it_could_not_list_in_its_json(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", ["--types", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert "types" not in payload
    assert "only PostgreSQL reports custom types" in payload["notes"][0]


def test_db_show_lists_the_custom_types_a_postgres_inspector_reports(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The suite has no PostgreSQL server, so its inspector is the seam.

    The reader itself still runs — only the inspector under it is a stand-in,
    shaped the way ``get_enums`` answers.
    """

    class EnumInspector:
        def get_enums(self) -> list[dict[str, str]]:
            return [{"name": "post_status"}]

    assert _custom_types(EnumInspector()) == ["post_status"]
    monkeypatch.setattr(
        "almasix.console.commands.db_introspection._custom_types",
        lambda _inspector: _custom_types(EnumInspector()),
    )

    assert kernel.run_argv("db:show", ["--types"]) == 0

    out = capsys.readouterr().out
    assert "Types" in out
    assert "post_status" in out


def test_db_show_says_when_the_database_has_no_tables(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db:show", []) == 0

    out = capsys.readouterr().out
    assert ["Tables", "0"] in cells(out)
    assert "(no tables)" in out


def test_db_show_reports_a_connection_that_is_not_configured(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", ["--database", "ghost"]) == 1
    assert "'ghost' is not configured" in capsys.readouterr().err


def test_db_show_says_which_database_name_it_could_not_read(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:show", ["--database"]) == 2
    assert "Invalid value for '--database'" in capsys.readouterr().err


def test_db_show_reports_a_database_file_it_cannot_open(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory where the database file should be is the user's to fix."""
    kernel = build(database=str(tmp_path))

    assert kernel.run_argv("db:show", []) == 1
    assert "unable to open database file" in capsys.readouterr().err


# --- db:table -------------------------------------------------------------


def test_db_table_shows_every_column_with_its_type_and_nullability(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["posts"]) == 0

    out = capsys.readouterr().out
    rows = cells(out)
    assert ["Table", "posts"] in rows
    assert ["Columns", "4"] in rows
    assert ["Primary", "Key", "id"] in rows
    assert ["id", "INTEGER", "no"] in rows
    assert ["title", "VARCHAR(255)", "yes"] in rows
    assert ["body", "TEXT", "yes"] in rows


def test_db_table_shows_the_indexes_a_table_carries(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["users"]) == 0

    rows = cells(capsys.readouterr().out)
    assert ["uq_users_email", "email", "yes"] in rows


def test_db_table_shows_the_foreign_keys_and_the_action_they_declare(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["posts"]) == 0

    rows = cells(capsys.readouterr().out)
    assert ["user_id", "users(id)", "CASCADE"] in rows


def test_db_table_says_when_a_table_has_no_indexes_and_no_foreign_keys(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["settings"]) == 0

    out = capsys.readouterr().out
    assert "(no indexes)" in out
    assert "(no foreign keys)" in out


def test_db_table_reports_the_default_a_column_was_declared_with(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["settings"]) == 0

    assert ["value", "TEXT", "no", "'on'"] in cells(capsys.readouterr().out)


def test_db_table_leaves_out_the_primary_key_row_when_the_table_has_none(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["logs"]) == 0

    assert "Primary Key" not in capsys.readouterr().out


def test_db_table_outputs_the_table_detail_as_json(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["posts", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["table"] == "posts"
    assert payload["connection"] == "sqlite"
    assert payload["primary_key"] == ["id"]
    assert {"column": "body", "type": "TEXT", "nullable": True, "default": None} in payload[
        "columns"
    ]
    assert payload["foreign_keys"] == [
        {
            "columns": ["user_id"],
            "references": "users(id)",
            "on_delete": "CASCADE",
            "on_update": None,
        }
    ]


def test_db_table_asks_which_table_to_inspect_when_none_is_named(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        "almasix.console.prompts.select",
        lambda label, options, **kwargs: asked.append((label, list(options))) or "users",
    )

    assert kernel.run_argv("db:table", []) == 0

    assert asked == [
        ("Which table would you like to inspect?", ["logs", "posts", "settings", "users"])
    ]
    assert ["Table", "users"] in cells(capsys.readouterr().out)


def test_db_table_reports_a_table_that_does_not_exist(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["comments"]) == 1

    err = capsys.readouterr().err
    assert "Table [comments] doesn't exist." in err
    assert "Available tables: logs, posts, settings, users." in err


def test_db_table_says_when_the_database_has_no_tables_to_inspect(
    build: Build, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db:table", []) == 1
    assert "The [sqlite] database has no tables to inspect." in capsys.readouterr().err


def test_db_table_reports_a_connection_that_is_not_configured(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:table", ["users", "--database", "ghost"]) == 1
    assert "'ghost' is not configured" in capsys.readouterr().err


def test_db_table_reports_a_database_file_it_cannot_open(
    build: Build, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build(database=str(tmp_path))

    assert kernel.run_argv("db:table", ["users"]) == 1
    assert "unable to open database file" in capsys.readouterr().err


# --- db:monitor -----------------------------------------------------------


def test_db_monitor_says_sqlite_keeps_no_sessions_to_count(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """There is no server behind a file, so the pool is all Almasix can see."""
    assert kernel.run_argv("db:monitor", []) == 0

    out = capsys.readouterr().out
    assert ["sqlite", "-"] in cells(out)
    assert "SQLite is a file, not a server" in out
    assert "This process holds" in out


def test_db_monitor_counts_the_sessions_the_server_reports(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Standing in a real query for the catalog one no SQLite server can answer."""
    monkeypatch.setitem(_SESSION_COUNT_SQL, "sqlite", "SELECT count(*) FROM users")

    assert kernel.run_argv("db:monitor", []) == 0

    assert ["sqlite", "2"] in cells(capsys.readouterr().out)


def test_db_monitor_reads_the_count_out_of_a_show_status_pair(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """MySQL answers ``SHOW STATUS`` with a name/value pair, not a bare count."""
    monkeypatch.setitem(
        _SESSION_COUNT_SQL,
        "sqlite",
        "SELECT 'Threads_connected' AS Variable_name, count(*) AS Value FROM users",
    )

    assert kernel.run_argv("db:monitor", []) == 0

    assert ["sqlite", "2"] in cells(capsys.readouterr().out)


def test_db_monitor_reports_no_sessions_when_the_server_answers_with_no_rows(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(
        _SESSION_COUNT_SQL, "sqlite", "SELECT count(*) FROM users WHERE 0 GROUP BY id"
    )

    assert kernel.run_argv("db:monitor", []) == 0

    assert ["sqlite", "0"] in cells(capsys.readouterr().out)


def test_db_monitor_fails_when_a_connection_is_above_the_maximum(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The exit code is the signal: Almasix has no ``DatabaseBusy`` event to fire."""
    monkeypatch.setitem(_SESSION_COUNT_SQL, "sqlite", "SELECT count(*) FROM users")

    assert kernel.run_argv("db:monitor", ["--max", "1"]) == 1

    captured = capsys.readouterr()
    assert ["sqlite", "2"] in cells(captured.out)
    assert "[sqlite] has 2 open session(s), above the maximum of 1." in captured.err


def test_db_monitor_stays_quiet_when_every_connection_is_below_the_maximum(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(_SESSION_COUNT_SQL, "sqlite", "SELECT count(*) FROM users")

    assert kernel.run_argv("db:monitor", ["--max", "10"]) == 0
    assert capsys.readouterr().err == ""


def test_db_monitor_reports_a_query_the_database_refused(
    kernel: ConsoleKernel, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(_SESSION_COUNT_SQL, "sqlite", "SELECT count(*) FROM pg_stat_activity")

    assert kernel.run_argv("db:monitor", []) == 1
    assert "[sqlite] could not be asked" in capsys.readouterr().err


def test_db_monitor_checks_every_connection_it_was_given(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:monitor", ["--databases", "sqlite,archive"]) == 0

    rows = cells(capsys.readouterr().out)
    assert ["sqlite", "-"] in rows
    assert ["archive", "-"] in rows


def test_db_monitor_reports_a_connection_that_is_not_configured(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:monitor", ["--databases", "ghost"]) == 1
    assert "'ghost' is not configured" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--max"], "Invalid value for '--max': provide a number"),
        (["--max", "lots"], "Invalid value for '--max': 'lots' is not a number."),
        (["--max", "0"], "Invalid value for '--max': 0 is not a session count."),
        (["--databases"], "Invalid value for '--databases': provide connection names"),
    ],
)
def test_db_monitor_refuses_input_it_cannot_read_as_a_threshold(
    argv: list[str], expected: str, kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("db:monitor", argv) == 2
    assert expected in capsys.readouterr().err


def test_db_monitor_can_be_called_in_process(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """``Artisan.call`` passes no options, so every flag has to be optional."""
    assert kernel.run_command("db:monitor") == 0
    assert ["sqlite", "-"] in cells(capsys.readouterr().out)
