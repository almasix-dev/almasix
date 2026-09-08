"""The two commands that hand the process away — ``serve`` and ``loupe``."""

from __future__ import annotations

from pathlib import Path

import uvicorn

from almasix.console.command import Command
from almasix.smith.ports import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_PORT,
    NoFreePortError,
    find_available_port,
)

DEFAULT_ASGI = "bootstrap.app:asgi"


class ServeCommand(Command):
    """Serve with Uvicorn, on the first free port.

    Defaults to port 3000. If that port is taken, tries 3001, 3002, … up to
    3099 (Laravel-style). Passing ``--port`` still auto-advances from that
    starting port.
    """

    signature = (
        f"serve {{--host={DEFAULT_HOST} : Bind host}} "
        f"{{--port= : Bind port (default: first free port from {DEFAULT_PORT}–{MAX_PORT}; "
        "if the chosen port is busy, try the next)} "
        "{--no-reload : Do not auto-reload on code changes} "
        f"{{--app={DEFAULT_ASGI} : ASGI import path (default: {DEFAULT_ASGI})}}"
    )
    description = "Serve the application with Uvicorn"

    #: Uvicorn boots the application in its own process, from the import path
    #: below — booting it here first would do it twice, in the wrong directory.
    boots_application = False

    def handle(self) -> int:
        # ``--app`` also lands on ``self.app`` (Command.run() sets an attribute
        # per input), so the import path is only ever read through option().
        app_path = str(self.option("app") or DEFAULT_ASGI)
        module_file = Path.cwd() / "bootstrap" / "app.py"
        if app_path == DEFAULT_ASGI and not module_file.is_file():
            self.error(
                "No bootstrap/app.py found. Run this from an Almasix app created with "
                "`almasix new`, or pass --app IMPORT_PATH."
            )
            return self.FAILURE

        host = str(self.option("host") or DEFAULT_HOST)
        port = self.option("port")
        try:
            # The signature parser hands over strings; Typer used to do this.
            start_port = DEFAULT_PORT if port is None else int(str(port))
        except ValueError:
            self.error(f"Invalid value for '--port': {port!r} is not a valid integer.")
            return self.INVALID

        # Default discovery window is 3000–3099 (100 ports). Explicit --port uses
        # the same window size starting from the requested port.
        window = MAX_PORT - DEFAULT_PORT
        end_port = start_port + window if start_port > MAX_PORT else max(start_port, MAX_PORT)

        try:
            chosen = find_available_port(host=host, start=start_port, end=end_port)
        except NoFreePortError as exc:
            self.error(str(exc))
            return self.FAILURE

        if chosen != start_port:
            self.warn(f"Port {start_port} is in use, using http://{host}:{chosen} instead.")

        self.line(f"Serving {app_path} on http://{host}:{chosen}")
        uvicorn.run(app_path, host=host, port=chosen, reload=not self.option("no_reload"))
        return self.SUCCESS


class LoupeCommand(Command):
    signature = "loupe"
    description = "Interactive Almasix REPL"
    aliases = ("tinker", "repl")

    def handle(self) -> int:
        from almasix.console.repl import start_loupe

        return start_loupe(self.app)
