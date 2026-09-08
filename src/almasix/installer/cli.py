"""Almasix installer CLI — Laravel's ``laravel`` command equivalent.

Preferred usage::

    almasix new myapp
"""

from __future__ import annotations

from pathlib import Path

import typer

from almasix import __version__
from almasix.installer.scaffold import ScaffoldError, scaffold_app

app = typer.Typer(
    name="almasix",
    help="Almasix installer — create new applications (like `laravel new`).",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """Create and manage Almasix application projects."""


@app.command("version")
def version() -> None:
    """Show Almasix version."""
    typer.echo(f"Almasix {__version__}")


@app.command("new")
def new(
    name: str = typer.Argument(..., help="Application directory name"),
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Parent directory (default: current working directory)",
    ),
) -> None:
    """Create a new Almasix application."""
    destination = (path or Path.cwd()) / name
    try:
        root = scaffold_app(name, destination=destination)
    except ScaffoldError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho(f"Created Almasix application: {root}", fg=typer.colors.GREEN)
    typer.echo(
        "\nNext steps:\n"
        f"  cd {root.name}\n"
        "  python -m venv .venv && source .venv/bin/activate\n"
        "  pip install -e .\n"
        "  python smith serve\n"
    )


if __name__ == "__main__":
    app()
