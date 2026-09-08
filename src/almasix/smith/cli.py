"""Smith — Almasix in-application CLI.

Preferred usage with the virtualenv active::

    smith version
    smith serve
    smith make:controller UserController
    smith loupe   # aliases: tinker, repl

Or via the root ``smith`` script::

    python smith serve

Project creation uses ``almasix new``, not Smith.

There is nothing else in this module on purpose. Every command is a
:class:`~almasix.console.command.Command` under ``almasix/console/commands``, and
:func:`almasix.console.front_door.install` puts them all behind Typer — so the
terminal, ``Artisan.call``, and the scheduler reach the same command the same
way. See ``docs/PLAN.md`` M30.
"""

from __future__ import annotations

import typer

from almasix.console.front_door import install

app = typer.Typer(
    name="smith",
    help="Smith — Almasix in-app CLI. Prefer: smith … (or python smith …)",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run application commands."""


install(app)


if __name__ == "__main__":
    app()
