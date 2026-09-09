"""M42 — ``db``, which hands you the engine's own client.

The command never opens a shell here: what is worth testing is the argv it
builds for each driver, the environment it puts the password in, and what it
says when the client is missing or the driver has none.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from almasix.console.commands.db import _client_command
from almasix.console.kernel import ConsoleKernel

Build = Callable[..., ConsoleKernel]

DATABASE_CONFIG = """
config = {
    'default': 'sqlite',
    'connections': {
        'sqlite': {'driver': 'sqlite', 'database': 'database/app.sqlite'},
        'mysql': {
            'driver': 'mysql',
            'host': 'db.example.com',
            'port': 3306,
            'database': 'shop',
            'username': 'root',
            'password': 'secret',
            'read': {'host': 'replica.example.com'},
            'write': {'host': 'primary.example.com'},
        },
        'pooled': {
            'driver': 'pgsql',
            'host': 'pooler.example.com',
            'port': 6543,
            'database': 'app',
            'username': 'app',
            'pooled': True,
            'direct': {'host': 'db.example.com', 'port': 5432},
        },
        'redis': {'driver': 'redis', 'database': 0},
    },
}
"""


def write_app(root: Path) -> None:
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "bootstrap").mkdir(exist_ok=True)
    (root / "bootstrap" / "app.py").write_text("# stub\n", encoding="utf-8")
    (root / "config" / "app.py").write_text(
        'config = {"name": "M42", "env": "local", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (root / "config" / "logging.py").write_text(
        "config = {'default': 'null', 'channels': {'null': {'driver': 'null'}}}\n",
        encoding="utf-8",
    )
    (root / "config" / "database.py").write_text(DATABASE_CONFIG, encoding="utf-8")


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Build]:
    def make() -> ConsoleKernel:
        write_app(tmp_path)
        monkeypatch.chdir(tmp_path)
        return ConsoleKernel.from_cwd(tmp_path)

    yield make


@pytest.fixture
def spy(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Catch the client Almasix would have run instead of running it."""
    calls: list[dict[str, object]] = []

    class Completed:
        returncode = 0

    def fake_run(argv, env=None, check=False):
        calls.append({"argv": argv, "env": env})
        return Completed()

    monkeypatch.setattr(
        "almasix.console.commands.db.shutil.which", lambda binary: f"/usr/bin/{binary}"
    )
    monkeypatch.setattr("almasix.console.commands.db.subprocess.run", fake_run)
    return calls


# --- what the command runs ----------------------------------------------------


def test_db_opens_the_default_connection_s_client(
    build: Build, spy: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db", []) == 0

    argv = spy[0]["argv"]
    assert argv[0] == "/usr/bin/sqlite3"
    assert argv[1].endswith("database/app.sqlite")
    assert "Connecting to [sqlite] with sqlite3." in capsys.readouterr().out


def test_db_opens_the_connection_it_is_named(build: Build, spy: list[dict[str, object]]) -> None:
    kernel = build()

    assert kernel.run_argv("db", ["mysql"]) == 0

    argv = spy[0]["argv"]
    assert argv[:3] == ["/usr/bin/mysql", "--database", "shop"]
    assert "db.example.com" in argv
    assert spy[0]["env"]["MYSQL_PWD"] == "secret"


def test_the_read_and_write_halves_can_be_asked_for_by_name(
    build: Build, spy: list[dict[str, object]]
) -> None:
    kernel = build()

    assert kernel.run_argv("db", ["mysql", "--read"]) == 0
    assert "replica.example.com" in spy[0]["argv"]

    assert kernel.run_argv("db", ["mysql", "--write"]) == 0
    assert "primary.example.com" in spy[1]["argv"]


def test_a_pooled_connection_opens_its_direct_twin_unless_told_otherwise(
    build: Build, spy: list[dict[str, object]]
) -> None:
    kernel = build()

    assert kernel.run_argv("db", ["pooled"]) == 0
    assert "db.example.com" in spy[0]["argv"]

    assert kernel.run_argv("db", ["pooled", "--pooled"]) == 0
    assert "pooler.example.com" in spy[1]["argv"]


def test_the_client_s_exit_status_is_the_command_s(
    build: Build, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Completed:
        returncode = 3

    monkeypatch.setattr("almasix.console.commands.db.shutil.which", lambda binary: f"/bin/{binary}")
    monkeypatch.setattr("almasix.console.commands.db.subprocess.run", lambda *a, **k: Completed())
    kernel = build()

    assert kernel.run_argv("db", []) == 3


# --- what it says instead ------------------------------------------------------


def test_db_says_which_client_it_looked_for(
    build: Build, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("almasix.console.commands.db.shutil.which", lambda _binary: None)
    kernel = build()

    assert kernel.run_argv("db", []) == 1
    assert "'sqlite3' is not installed" in capsys.readouterr().err


def test_db_says_when_a_driver_has_no_client(
    build: Build, spy: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db", ["redis"]) == 2
    assert "no command-line client for the 'redis' driver" in capsys.readouterr().err
    assert spy == []


def test_db_says_when_the_connection_is_not_configured(
    build: Build, spy: list[dict[str, object]], capsys: pytest.CaptureFixture[str]
) -> None:
    kernel = build()

    assert kernel.run_argv("db", ["ghost"]) == 1
    assert "ghost" in capsys.readouterr().err
    assert spy == []


# --- the argv each driver wants --------------------------------------------------


def test_every_driver_s_client_is_spelled_the_way_it_expects() -> None:
    assert _client_command({"driver": "sqlite", "database": "app.sqlite"}) == (
        "sqlite3",
        ["app.sqlite"],
        {},
    )
    assert _client_command(
        {"driver": "mariadb", "database": "shop", "host": "h", "port": 3306, "username": "u"}
    ) == ("mysql", ["--database", "shop", "--host", "h", "--port", "3306", "--user", "u"], {})
    assert _client_command(
        {
            "driver": "pgsql",
            "database": "app",
            "host": "h",
            "port": 5432,
            "username": "u",
            "password": "p",
        }
    ) == (
        "psql",
        ["--dbname", "app", "--host", "h", "--port", "5432", "--username", "u"],
        {"PGPASSWORD": "p"},
    )
    assert _client_command(
        {
            "driver": "sqlsrv",
            "database": "app",
            "host": "h",
            "port": 1433,
            "username": "sa",
            "password": "p",
        }
    ) == ("sqlcmd", ["-S", "h,1433", "-d", "app", "-U", "sa", "-P", "p"], {})
    assert _client_command({"driver": "mssql", "database": "app", "host": "h"}) == (
        "sqlcmd",
        ["-S", "h", "-d", "app"],
        {},
    )
    assert _client_command({"driver": "mongodb", "database": "app"}) is None


def test_a_client_asks_for_nothing_the_config_did_not_give_it() -> None:
    assert _client_command({"driver": "mysql", "database": "shop"}) == (
        "mysql",
        ["--database", "shop"],
        {},
    )
    assert _client_command({"driver": "postgres", "database": "app"}) == (
        "psql",
        ["--dbname", "app"],
        {},
    )
