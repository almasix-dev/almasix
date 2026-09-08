"""The commands that answer "what is this application?".

``about`` summarises the environment and the configured drivers, ``help``
describes one command, ``route:list`` shows what the router answers, and
``config:show`` prints a config namespace. All four read what the application
already knows — a row Avalon cannot answer is left out rather than guessed.
"""

from __future__ import annotations

import difflib
import platform
from typing import TYPE_CHECKING, Any

from avalon import __version__
from avalon.console.command import Command
from avalon.console.display import to_json
from avalon.console.help import help_text, usage

if TYPE_CHECKING:
    from avalon.routing.router import RouteDefinition

#: Key fragments whose values ``config:show`` hides unless asked twice.
_SECRET_HINTS = ("password", "secret", "token", "key")

_REDACTED = "********"


class AboutCommand(Command):
    """Laravel's ``about`` — the application at a glance.

    Every row comes from a config key or from the interpreter, so a section is
    as long as the application's own ``config/`` makes it: a directory with no
    ``config/mail.py`` has no Mail row.
    """

    signature = (
        "about {--only= : Show only this section (environment, drivers)} "
        "{--json : Output as JSON}"
    )
    description = "Show a summary of the application's environment and drivers"

    def handle(self) -> int:
        sections = [
            ("Environment", self._environment()),
            ("Drivers", self._drivers()),
        ]
        only = str(self.option("only") or "").strip()
        if only:
            wanted = [row for row in sections if row[0].lower() == only.lower()]
            if not wanted:
                available = ", ".join(title.lower() for title, _ in sections)
                self.error(f"Unknown section {only!r}. Available sections: {available}.")
                return self.FAILURE
            sections = wanted

        if self.option("json"):
            self.line(
                to_json(
                    {
                        _snake(title): {_snake(label): value for label, value in rows}
                        for title, rows in sections
                    }
                )
            )
            return self.SUCCESS

        for index, (title, rows) in enumerate(sections):
            if index:
                self.new_line()
            self.comment(title)
            if not rows:
                self.line("  (nothing configured)")
                continue
            width = max(len(label) for label, _ in rows)
            for label, value in rows:
                self.line(f"  {label:<{width}}  {value}")
        return self.SUCCESS

    def _environment(self) -> list[tuple[str, str]]:
        config = self.app.config
        return _present(
            [
                ("Application Name", config.get("app.name")),
                ("Avalon Version", __version__),
                ("Python Version", platform.python_version()),
                ("Environment", config.get("app.env")),
                ("Debug Mode", _toggle(config.get("app.debug"))),
                ("URL", config.get("app.url")),
                ("Locale", config.get("app.locale")),
                ("Fallback Locale", config.get("app.fallback_locale")),
                ("Maintenance Mode", "DOWN" if self._is_down() else "OFF"),
                ("Base Path", self.app.base_path),
            ]
        )

    def _drivers(self) -> list[tuple[str, str]]:
        config = self.app.config
        return _present(
            [
                ("Cache", config.get("cache.default")),
                ("Database", config.get("database.default")),
                ("Filesystem Disk", config.get("filesystems.default")),
                ("Logs", config.get("logging.default")),
                ("Mail", self._mail_transport()),
                ("Notifications", config.get("notifications.default")),
                ("Queue", config.get("queue.default")),
                ("Session", config.get("session.driver")),
            ]
        )

    def _mail_transport(self) -> Any:
        """The transport behind the default mailer, or the mailer's own name."""
        mailer = self.app.config.get("mail.default")
        if not mailer:
            return None
        return self.app.config.get(f"mail.mailers.{mailer}.transport") or mailer

    def _is_down(self) -> bool:
        """The marker ``grail down`` writes and the HTTP kernel answers 503 for."""
        return self.app.path("storage", "framework", "down").is_file()


class HelpCommand(Command):
    """Laravel's ``help`` — the full help for one command.

    The signature is the only description a command has, so this prints what
    ``avalon.console.help`` renders from it. The registry is all it needs,
    which means it answers in a directory that is not an application yet.
    """

    signature = "help {command? : The command to describe}"
    description = "Describe a command — its usage, arguments, and options"
    boots_application = False

    def handle(self) -> int:
        name = str(self.argument("command") or "")
        if not name:
            return self.call("list")

        registry = self.kernel.commands
        command_cls = registry.get(name)
        if command_cls is None:
            self.error(f'The command "{name}" is not defined.')
            near = difflib.get_close_matches(name, sorted(registry), n=3)
            if near:
                self.line("Did you mean one of these?")
                for candidate in near:
                    self.line(f"  {candidate}")
            return self.FAILURE

        if command_cls.description:
            self.comment("Description:")
            self.line(f"  {command_cls.description}")
            self.new_line()
        self.comment("Usage:")
        self.line(f"  grail {usage(command_cls)}")
        for line in _help_body(command_cls):
            self.line(line)
        return self.SUCCESS


class RouteListCommand(Command):
    """Laravel's ``route:list`` — every route the application answers.

    The console kernel boots without the HTTP routes, because most commands
    have no use for them, so this asks the application to load them.
    """

    signature = (
        "route:list {--method= : Only routes answering this HTTP method} "
        "{--name= : Only routes whose name contains this text} "
        "{--path= : Only routes whose URI contains this text} "
        "{--json : Output as JSON}"
    )
    description = "List the application's registered routes"

    def handle(self) -> int:
        self.app.load_routes()
        routes = sorted(self.app.router.routes, key=lambda route: (route.uri, route.methods))
        if not routes:
            self.line("Your application has no registered routes.")
            return self.SUCCESS

        matched = [route for route in routes if self._matches(route)]
        if not matched:
            self.warn("No routes match the given filters.")
            return self.SUCCESS

        if self.option("json"):
            self.line(
                to_json(
                    [
                        {
                            "methods": list(route.methods),
                            "uri": route.uri,
                            "name": route.name,
                            "action": _action(route.action),
                        }
                        for route in matched
                    ]
                )
            )
            return self.SUCCESS

        self.table(
            ("Method", "URI", "Name", "Action"),
            [
                ("|".join(route.methods), route.uri, route.name or "", _action(route.action))
                for route in matched
            ],
        )
        return self.SUCCESS

    def _matches(self, route: RouteDefinition) -> bool:
        method = str(self.option("method") or "").strip().upper()
        if method and method not in route.methods:
            return False
        name = str(self.option("name") or "").strip().lower()
        if name and name not in (route.name or "").lower():
            return False
        path = str(self.option("path") or "").strip().lower()
        return not path or path in route.uri.lower()


class ConfigShowCommand(Command):
    """Laravel's ``config:show`` — one config namespace or value.

    Credentials are redacted by default: this is the command people run over a
    shoulder, in a recorded session, or paste into a bug report, and
    ``config/database.py`` holds the production password. ``--show-secrets``
    prints them when that is what you actually want.
    """

    signature = (
        "config:show {key : Config key, e.g. database or database.connections.sqlite} "
        "{--show-secrets : Print credential values instead of redacting them} "
        "{--json : Output as JSON}"
    )
    description = "Show a configuration value or namespace"

    def handle(self) -> int:
        key = str(self.argument("key") or "")
        missing = object()
        value = self.app.config.get(key, missing)
        if value is missing:
            self.error(f"Configuration key {key!r} is not set.")
            return self.FAILURE

        if not self.option("show_secrets"):
            value = _redact(key.rpartition(".")[2], value)

        if self.option("json"):
            self.line(to_json({key: value}))
            return self.SUCCESS

        self.comment(key)
        if isinstance(value, (dict, list)) and value:
            for line in _tree(value, 1):
                self.line(line)
        else:
            self.line(f"  {_scalar(value)}")
        return self.SUCCESS


def _present(rows: list[tuple[str, Any]]) -> list[tuple[str, str]]:
    """Drop the rows the application could not answer, and stringify the rest."""
    return [(label, str(value)) for label, value in rows if value is not None and value != ""]


def _toggle(value: Any) -> str | None:
    """Laravel's ``ENABLED``/``OFF`` for a boolean-ish flag, ``None`` when unset."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        enabled = value.strip().lower() in ("1", "true", "yes", "on")
    else:
        enabled = bool(value)
    return "ENABLED" if enabled else "OFF"


def _snake(label: str) -> str:
    return label.lower().replace(" ", "_")


def _help_body(command_cls: type[Command]) -> list[str]:
    """The rendered help minus its description, which is printed above it.

    ``\\b`` lines are Click's "do not rewrap this" markers; a terminal reading
    ``grail help`` has no use for them.
    """
    lines = [line for line in help_text(command_cls).splitlines() if line != "\b"]
    if command_cls.description and lines and lines[0] == command_cls.description:
        return lines[1:]
    return lines


def _action(action: Any) -> str:
    """A route action as text: ``module.Controller@method``, or the callable."""
    if isinstance(action, (list, tuple)) and len(action) == 2:
        controller, method = action
        return f"{_dotted(controller)}@{method}"
    if isinstance(action, str):
        return action
    return _dotted(action)


def _dotted(target: Any) -> str:
    name = getattr(target, "__qualname__", None) or getattr(target, "__name__", None)
    if name is None:
        return str(target)
    module = getattr(target, "__module__", "")
    return f"{module}.{name}" if module else name


def _redact(name: str, value: Any) -> Any:
    """Replace credential-looking values, keeping the shape of the tree."""
    if isinstance(value, dict):
        return {key: _redact(str(key), item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(name, item) for item in value]
    if _is_secret(name) and value is not None and value != "":
        return _REDACTED
    return value


def _is_secret(name: str) -> bool:
    lowered = name.lower()
    return any(hint in lowered for hint in _SECRET_HINTS)


def _tree(value: dict[Any, Any] | list[Any], indent: int) -> list[str]:
    """Nested config as indented lines, one leaf per line."""
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}{key}")
                lines.extend(_tree(item, indent + 1))
            else:
                lines.append(f"{pad}{key}: {_scalar(item)}".rstrip())
        return lines
    for item in value:
        if isinstance(item, (dict, list)) and item:
            lines.extend(_tree(item, indent))
        else:
            lines.append(f"{pad}- {_scalar(item)}".rstrip())
    return lines


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return "{}"
    if isinstance(value, (list, tuple)):
        return "[]"
    return str(value)
