"""``make:event`` / ``make:listener`` / ``event:list``."""

from __future__ import annotations

from pathlib import Path

from avalon.console.command import Command


def _pascal(name: str) -> str:
    parts = name.replace("-", "_").split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


class MakeEventCommand(Command):
    signature = "make:event {name}"
    description = "Create a new event class"

    def handle(self) -> int:
        name = _pascal(str(self.argument("name")))
        path = Path.cwd() / "app" / "events" / f"{_snake(name)}.py"
        if path.exists():
            self.error(f"Event already exists: {path}")
            return 1
        _write(
            path,
            f'''"""Application event."""

from __future__ import annotations


class {name}:
    """Event payload."""

    def __init__(self, **payload) -> None:
        self.__dict__.update(payload)
''',
        )
        # ensure package init
        init = path.parent / "__init__.py"
        if not init.exists():
            init.write_text('"""Application events."""\n', encoding="utf-8")
        self.info(f"Event created: {path}")
        return 0


class MakeListenerCommand(Command):
    signature = "make:listener {name} {--event=} {--queued}"
    description = "Create a new event listener class"

    def handle(self) -> int:
        name = _pascal(str(self.argument("name")))
        event_name = self.option("event")
        queued = bool(self.option("queued"))
        path = Path.cwd() / "app" / "listeners" / f"{_snake(name)}.py"
        if path.exists():
            self.error(f"Listener already exists: {path}")
            return 1

        imports = ["from __future__ import annotations"]
        bases = ""
        if queued:
            imports.append("from avalon.events import ShouldQueue")
            bases = "(ShouldQueue)"
        event_import = ""
        handle_arg = "event"
        if event_name:
            ename = _pascal(str(event_name))
            event_import = f"from app.events.{_snake(ename)} import {ename}\n"
            handle_arg = f"event: {ename}"

        body = f'''"""Event listener."""

{chr(10).join(imports)}
{event_import}

class {name}{bases}:
    """Handle the event."""

    def handle(self, {handle_arg}) -> None:
        pass
'''
        _write(path, body)
        init = path.parent / "__init__.py"
        if not init.exists():
            init.write_text('"""Application listeners."""\n', encoding="utf-8")
        self.info(f"Listener created: {path}")
        return 0


class EventListCommand(Command):
    signature = "event:list"
    description = "List registered event listeners"

    def handle(self) -> int:
        from avalon.events import Event

        listeners = Event.get_dispatcher().get_listeners()
        if not listeners:
            self.comment("No event listeners registered.")
            return 0
        for name, items in sorted(listeners.items()):
            self.line(name)
            for item in items:
                label = getattr(item, "__name__", None) or repr(item)
                self.line(f"  - {label}")
        return 0


def _snake(name: str) -> str:
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)
