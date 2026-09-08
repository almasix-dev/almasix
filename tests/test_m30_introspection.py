"""M30 — the introspection commands: ``about``, ``help``, ``route:list``, ``config:show``.

These four only report what the application already knows. The tests hold that
line: a row Avalon cannot answer is absent, not blank and not guessed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from avalon import __version__
from avalon.console.command import Command
from avalon.console.commands.introspection import HelpCommand
from avalon.console.facade import Artisan
from avalon.console.kernel import ConsoleKernel

ROUTES = '''
"""Routes written by the test, with no application package to import."""

from functools import partial

from avalon.routing import Route


class ProbeController:
    def store(self) -> str:
        return "stored"


def home() -> str:
    return "ok"


Route.get("/", home, name="home")
Route.post("/posts/{post}", [ProbeController, "store"])
Route.match(["GET", "POST"], "/legacy", "LegacyController@index", name="legacy.index")
Route.get("/partial", partial(home))
'''


@pytest.fixture()
def kernel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ConsoleKernel]:
    """A kernel over an empty directory, with the framework commands registered.

    Nothing is booted, so each test says exactly which config it has — which is
    also how it can say what happens when a key is missing.
    """
    monkeypatch.chdir(tmp_path)
    built = ConsoleKernel.for_cwd(tmp_path)
    built.discover_framework_commands()
    Artisan.set_kernel(built)
    yield built
    Artisan.set_kernel(None)


def configure(kernel: ConsoleKernel, values: dict[str, object]) -> None:
    for key, value in values.items():
        kernel.app.config.set(key, value)


FULL_CONFIG: dict[str, object] = {
    "app.name": "Probe",
    "app.env": "testing",
    "app.debug": True,
    "app.url": "http://127.0.0.1:3000",
    "app.locale": "en",
    "app.fallback_locale": "en",
    "cache.default": "array",
    "database.default": "sqlite",
    "filesystems.default": "local",
    "logging.default": "stack",
    "mail.default": "log",
    "mail.mailers.log.transport": "log",
    "notifications.default": "mail",
    "queue.default": "sync",
    "session.driver": "cookie",
}


# --- about ----------------------------------------------------------------


def test_about_reports_the_environment_and_the_drivers(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, FULL_CONFIG)

    assert kernel.run_argv("about", []) == 0

    out = capsys.readouterr().out
    assert "Environment" in out
    assert f"Avalon Version    {__version__}" in out
    assert "Application Name  Probe" in out
    assert "Environment       testing" in out
    assert "Debug Mode        ENABLED" in out
    assert "Maintenance Mode  OFF" in out
    assert str(kernel.app.base_path) in out
    assert "Python Version" in out

    assert "Drivers" in out
    assert "Cache            array" in out
    assert "Database         sqlite" in out
    assert "Filesystem Disk  local" in out
    assert "Logs             stack" in out
    assert "Mail             log" in out
    assert "Notifications    mail" in out
    assert "Queue            sync" in out
    assert "Session          cookie" in out


def test_about_leaves_out_the_rows_the_application_cannot_answer(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory with no ``config/`` has no drivers — and says so, rather than lying."""
    assert kernel.run_argv("about", []) == 0

    out = capsys.readouterr().out
    assert "(nothing configured)" in out
    for absent in ("Application Name", "Debug Mode", "Cache", "Session", "Mail"):
        assert absent not in out
    assert f"Avalon Version    {__version__}" in out


def test_about_drops_a_configured_row_that_is_empty(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {**FULL_CONFIG, "app.url": ""})

    assert kernel.run_argv("about", []) == 0
    assert "URL" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("debug", "expected"),
    [(True, "ENABLED"), (False, "OFF"), ("true", "ENABLED"), ("no", "OFF"), ("", None)],
)
def test_about_reads_debug_mode_however_it_was_written(
    kernel: ConsoleKernel,
    capsys: pytest.CaptureFixture[str],
    debug: object,
    expected: str | None,
) -> None:
    configure(kernel, {"app.debug": debug})

    assert kernel.run_argv("about", []) == 0

    out = capsys.readouterr().out
    if expected is None:
        assert "Debug Mode" not in out
    else:
        assert f"Debug Mode        {expected}" in out


def test_about_names_the_transport_behind_the_default_mailer(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {"mail.default": "smtp", "mail.mailers.smtp.transport": "smtp"})

    assert kernel.run_argv("about", []) == 0
    assert "Mail  smtp" in capsys.readouterr().out


def test_about_falls_back_to_the_mailer_name_when_it_declares_no_transport(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {"mail.default": "postmark"})

    assert kernel.run_argv("about", []) == 0
    assert "Mail  postmark" in capsys.readouterr().out


def test_about_says_when_the_application_is_down_for_maintenance(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = kernel.app.path("storage", "framework", "down")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("down", encoding="utf-8")

    assert kernel.run_argv("about", []) == 0
    assert "Maintenance Mode  DOWN" in capsys.readouterr().out


def test_about_json_is_snake_cased_and_grouped_by_section(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, FULL_CONFIG)

    assert kernel.run_argv("about", ["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"environment", "drivers"}
    assert payload["environment"]["avalon_version"] == __version__
    assert payload["environment"]["application_name"] == "Probe"
    assert payload["environment"]["debug_mode"] == "ENABLED"
    assert payload["environment"]["fallback_locale"] == "en"
    assert payload["environment"]["base_path"] == str(kernel.app.base_path)
    assert payload["drivers"] == {
        "cache": "array",
        "database": "sqlite",
        "filesystem_disk": "local",
        "logs": "stack",
        "mail": "log",
        "notifications": "mail",
        "queue": "sync",
        "session": "cookie",
    }


def test_about_only_prints_the_section_it_was_asked_for(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, FULL_CONFIG)

    assert kernel.run_argv("about", ["--only", "DRIVERS"]) == 0

    out = capsys.readouterr().out
    assert "Drivers" in out
    assert "Avalon Version" not in out


def test_about_only_in_json_carries_just_that_section(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, FULL_CONFIG)

    assert kernel.run_argv("about", ["--only=environment", "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == {"environment"}


def test_about_rejects_a_section_it_does_not_have(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("about", ["--only=broadcasting"]) == Command.FAILURE

    error = capsys.readouterr().err
    assert "Unknown section 'broadcasting'" in error
    assert "environment, drivers" in error


# --- help -----------------------------------------------------------------


class DescribedCommand(Command):
    signature = (
        "probe:describe {user : The user ID} {--Q|queue=default : Which queue} "
        "{--force : Skip the confirmation}"
    )
    description = "Describe one user"
    aliases = ("probe:described",)

    def handle(self) -> int:
        return 0


class UndescribedCommand(Command):
    signature = "probe:quiet"

    def handle(self) -> int:
        return 0


def test_help_prints_the_description_usage_arguments_options_and_aliases(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel.register(DescribedCommand)

    assert kernel.run_argv("help", ["probe:describe"]) == 0

    out = capsys.readouterr().out
    assert "Description:" in out
    assert "  Describe one user" in out
    assert "  grail probe:describe <user> [-Q, --queue=QUEUE] [--force]" in out
    assert "Arguments:" in out
    assert "<user>" in out and "The user ID" in out
    assert "Options:" in out
    assert "-Q, --queue=QUEUE" in out and "Which queue [default: default]" in out
    assert "Aliases:" in out
    assert "probe:described" in out
    assert "\b" not in out


def test_help_describes_a_command_that_has_no_description(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel.register(UndescribedCommand)

    assert kernel.run_argv("help", ["probe:quiet"]) == 0

    out = capsys.readouterr().out
    assert "Description:" not in out
    assert "  grail probe:quiet" in out


def test_help_answers_for_an_alias_too(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    kernel.register(DescribedCommand)

    assert kernel.run_argv("help", ["probe:described"]) == 0
    assert "  grail probe:describe <user>" in capsys.readouterr().out


def test_help_without_an_argument_prints_the_same_overview_as_list(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("help", []) == 0

    out = capsys.readouterr().out
    assert "Available commands:" in out
    assert "route:list" in out


def test_help_suggests_near_matches_for_a_name_it_does_not_know(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("help", ["rout:list"]) == Command.FAILURE

    captured = capsys.readouterr()
    assert 'The command "rout:list" is not defined.' in captured.err
    assert "Did you mean one of these?" in captured.out
    assert "route:list" in captured.out


def test_help_stays_quiet_when_nothing_is_close(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("help", ["zzzzzzzzzz"]) == Command.FAILURE

    captured = capsys.readouterr()
    assert 'The command "zzzzzzzzzz" is not defined.' in captured.err
    assert "Did you mean" not in captured.out


def test_help_needs_no_application(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    """A bare directory has no config, and ``help`` must still answer."""
    assert HelpCommand.boots_application is False

    assert kernel.run_argv("help", ["version"]) == 0
    assert not kernel.app.is_bootstrapped
    assert "  grail version" in capsys.readouterr().out


# --- route:list -----------------------------------------------------------


@pytest.fixture()
def routed(kernel: ConsoleKernel) -> ConsoleKernel:
    routes = kernel.app.path("routes")
    routes.mkdir(parents=True, exist_ok=True)
    (routes / "web.py").write_text(ROUTES, encoding="utf-8")
    return kernel


def test_route_list_loads_the_http_routes_the_console_kernel_skipped(
    routed: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert not routed.app.router.routes

    assert routed.run_argv("route:list", []) == 0

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines[0].split() == ["Method", "URI", "Name", "Action"]
    body = [line for line in lines[2:]]
    assert [line.split()[1] for line in body] == [
        "/",
        "/legacy",
        "/partial",
        "/posts/{post}",
    ]
    assert "GET|POST" in body[1]
    assert "legacy.index" in body[1]
    assert "LegacyController@index" in body[1]
    assert "ProbeController@store" in body[3]
    assert "home" in body[0]
    assert "partial" in body[2]


def test_route_list_filters_by_method(
    routed: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert routed.run_argv("route:list", ["--method", "post"]) == 0

    out = capsys.readouterr().out
    assert "/posts/{post}" in out
    assert "/partial" not in out


def test_route_list_filters_by_name_and_path(
    routed: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert routed.run_argv("route:list", ["--name=legacy"]) == 0
    assert "/legacy" in capsys.readouterr().out

    assert routed.run_argv("route:list", ["--path=/posts"]) == 0
    out = capsys.readouterr().out
    assert "/posts/{post}" in out
    assert "/legacy" not in out


def test_route_list_says_when_no_route_matches_the_filters(
    routed: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert routed.run_argv("route:list", ["--name=nothing"]) == 0
    assert "No routes match the given filters." in capsys.readouterr().out


def test_route_list_says_when_there_are_no_routes_at_all(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("route:list", []) == 0
    assert "Your application has no registered routes." in capsys.readouterr().out


def test_route_list_json_carries_every_column(
    routed: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert routed.run_argv("route:list", ["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [route["uri"] for route in payload] == [
        "/",
        "/legacy",
        "/partial",
        "/posts/{post}",
    ]
    assert payload[1]["methods"] == ["GET", "POST"]
    assert payload[1]["name"] == "legacy.index"
    assert payload[1]["action"] == "LegacyController@index"
    assert payload[2]["name"] is None
    assert payload[3]["action"].endswith("ProbeController@store")


# --- config:show ----------------------------------------------------------


def test_config_show_prints_a_namespace_as_an_indented_tree(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(
        kernel,
        {
            "database.default": "sqlite",
            "database.connections.sqlite": {"driver": "sqlite", "database": "db.sqlite"},
        },
    )

    assert kernel.run_argv("config:show", ["database"]) == 0
    assert capsys.readouterr().out == (
        "database\n"
        "  default: sqlite\n"
        "  connections\n"
        "    sqlite\n"
        "      driver: sqlite\n"
        "      database: db.sqlite\n"
    )


def test_config_show_prints_a_dotted_key_on_its_own(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {"database.connections.sqlite.driver": "sqlite"})

    assert kernel.run_argv("config:show", ["database.connections.sqlite.driver"]) == 0
    assert capsys.readouterr().out == "database.connections.sqlite.driver\n  sqlite\n"


def test_config_show_writes_every_kind_of_leaf_plainly(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(
        kernel,
        {
            "probe.on": True,
            "probe.off": False,
            "probe.missing": None,
            "probe.nothing": {},
            "probe.none": [],
            "probe.providers": ["one", "two"],
            "probe.pairs": [{"host": "localhost"}],
        },
    )

    assert kernel.run_argv("config:show", ["probe"]) == 0
    assert capsys.readouterr().out == (
        "probe\n"
        "  on: true\n"
        "  off: false\n"
        "  missing: null\n"
        "  nothing: {}\n"
        "  none: []\n"
        "  providers\n"
        "    - one\n"
        "    - two\n"
        "  pairs\n"
        "    host: localhost\n"
    )


def test_config_show_prints_an_empty_namespace_as_a_scalar(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {"probe": {}})

    assert kernel.run_argv("config:show", ["probe"]) == 0
    assert capsys.readouterr().out == "probe\n  {}\n"


def test_config_show_redacts_credentials_by_default(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(
        kernel,
        {
            "database.connections.pgsql": {
                "host": "127.0.0.1",
                "username": "avalon",
                "password": "s3cret",
            },
            "app.key": "base64:abc",
            "services.api_token": "tok",
            "services.client_secret": "shh",
            "services.blank_password": "",
        },
    )

    assert kernel.run_argv("config:show", ["database"]) == 0
    out = capsys.readouterr().out
    assert "password: ********" in out
    assert "s3cret" not in out
    assert "username: avalon" in out

    assert kernel.run_argv("config:show", ["app.key"]) == 0
    assert capsys.readouterr().out == "app.key\n  ********\n"

    assert kernel.run_argv("config:show", ["services"]) == 0
    out = capsys.readouterr().out
    assert "api_token: ********" in out
    assert "client_secret: ********" in out
    assert "blank_password:" in out
    assert "blank_password: ********" not in out


def test_config_show_prints_secrets_when_asked(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {"app.key": "base64:abc"})

    assert kernel.run_argv("config:show", ["app.key", "--show-secrets"]) == 0
    assert capsys.readouterr().out == "app.key\n  base64:abc\n"


def test_config_show_json_redacts_the_same_way(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(kernel, {"database.connections.pgsql.password": "s3cret"})

    assert kernel.run_argv("config:show", ["database", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"database": {"connections": {"pgsql": {"password": "********"}}}}

    assert kernel.run_argv("config:show", ["database", "--json", "--show-secrets"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["database"]["connections"]["pgsql"]["password"] == "s3cret"


def test_config_show_fails_on_a_key_the_application_does_not_have(
    kernel: ConsoleKernel, capsys: pytest.CaptureFixture[str]
) -> None:
    assert kernel.run_argv("config:show", ["database.connections.nope"]) == Command.FAILURE
    assert "Configuration key 'database.connections.nope' is not set." in capsys.readouterr().err
