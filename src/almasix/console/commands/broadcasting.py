"""Broadcasting commands — `make:channel` and `channel:list`."""

from __future__ import annotations

from typing import Any

from almasix.console.command import Command
from almasix.console.commands.make import Generator
from almasix.orm.inflector import snake


class MakeChannelCommand(Generator):
    """Create a channel class in `app/broadcasting`."""

    signature = (
        "make:channel {name : Class name, e.g. OrderChannel} "
        "{--force : Overwrite an existing file}"
    )
    description = "Create a broadcast channel class in app/broadcasting"
    kind = "channel"

    def replacements(self) -> dict[str, str]:
        """A plausible channel name for the docstring, from the class name."""
        name = self.class_name()
        base = name.removesuffix("Channel")
        return {"channel": snake(base or name).replace("_", "-")}


class ChannelListCommand(Command):
    """Show the channels the application authorizes, and how."""

    signature = "channel:list"
    description = "List the registered broadcast channels"

    def handle(self) -> int:
        from almasix.broadcasting.manager import BroadcastManager

        manager = self.app.make(BroadcastManager)
        channels = manager.channels()
        self.line(f"broadcasting via [{manager.get_default_driver()}]")
        if not channels:
            self.comment("No channels registered. Declare them in routes/channels.py.")
            return self.SUCCESS

        for route in channels:
            guards = f"  guards: {', '.join(route.guards)}" if route.guards else ""
            self.line(f"  {route.pattern} -> {_label(route.callback)}{guards}")
        return self.SUCCESS


def _label(callback: Any) -> str:
    """Something readable for whatever was registered."""
    name = getattr(callback, "__qualname__", None) or getattr(callback, "__name__", None)
    if name is None:
        return type(callback).__name__
    return "closure" if name.endswith("<lambda>") else name
