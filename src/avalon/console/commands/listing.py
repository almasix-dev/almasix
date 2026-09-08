"""``grail list`` — the command catalogue.

One surface, one listing. Every command Grail can reach — framework, app,
closure — is in the kernel registry, so this reads the registry and nothing
else, grouped by namespace the way ``php artisan list`` groups it.
"""

from __future__ import annotations

from avalon import __version__
from avalon.console.command import Command
from avalon.console.facade import Artisan


class ListCommand(Command):
    signature = "list"
    description = "List the commands available to Grail"

    def handle(self) -> int:
        commands = self._canonical()
        width = max((len(name) for name, _ in commands), default=0)

        self.line(f"Avalon {__version__}")
        self.line()
        self.line("Usage:")
        self.line("  grail <command> [options] [arguments]")
        self.line()
        self.line("Available commands:")
        for namespace, group in _grouped(commands):
            if namespace:
                self.line(f" {namespace}")
            for name, command_cls in group:
                self.line(f"  {name:<{width}}  {_summary(command_cls)}".rstrip())

        self._report_failures()
        return self.SUCCESS

    def _canonical(self) -> list[tuple[str, type[Command]]]:
        """Registry entries, minus the hidden ones and the alias spellings.

        Aliases live in the registry pointing at the same class, so a command
        is listed under its own ``name()`` once and says what else it answers
        to in its description.
        """
        registry = self.kernel.commands if self.kernel else Artisan.all(self.app)
        listable = [
            (name, command_cls)
            for name, command_cls in registry.items()
            if not command_cls.hidden and name == command_cls.name()
        ]
        return sorted(listable, key=lambda item: item[0])

    def _report_failures(self) -> None:
        """Repeat the discovery notices, so a broken module is visible here."""
        failures = (self.kernel or Artisan.kernel(self.app)).failures
        if not failures:
            return
        self.line()
        for failure in failures:
            self.warn(f"Command not loaded — {failure.summary()}")


def _grouped(
    commands: list[tuple[str, type[Command]]],
) -> list[tuple[str, list[tuple[str, type[Command]]]]]:
    """Bucket commands by their ``namespace:`` prefix, un-namespaced first."""
    groups: dict[str, list[tuple[str, type[Command]]]] = {}
    for name, command_cls in commands:
        namespace, separator, _ = name.partition(":")
        groups.setdefault(namespace if separator else "", []).append((name, command_cls))
    return sorted(groups.items(), key=lambda item: (item[0] != "", item[0]))


def _summary(command_cls: type[Command]) -> str:
    """A command's description, prefixed with its aliases when it has any."""
    if not command_cls.aliases:
        return command_cls.description
    return f"[{'|'.join(command_cls.aliases)}] {command_cls.description}".rstrip()
