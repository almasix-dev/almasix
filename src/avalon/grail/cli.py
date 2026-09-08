"""Grail — Avalon in-application CLI.

Preferred usage with the virtualenv active::

    grail version
    grail serve
    grail make:controller UserController
    grail fiddle   # aliases: tinker, repl

Or via the root ``grail`` script::

    python grail serve

Project creation uses ``avalon new``, not Grail.

There is nothing else in this module on purpose. Every command is a
:class:`~avalon.console.command.Command` under ``avalon/console/commands``, and
:func:`avalon.console.front_door.install` puts them all behind Typer — so the
terminal, ``Artisan.call``, and the scheduler reach the same command the same
way. See ``docs/PLAN.md`` M30.
"""

from __future__ import annotations

import typer

from avalon.console.front_door import install

app = typer.Typer(
    name="grail",
    help="Grail — Avalon in-app CLI. Prefer: grail … (or python grail …)",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Run application commands."""


install(app)


if __name__ == "__main__":
    app()
