"""Almasix installer CLI — Laravel's ``laravel`` command equivalent.

Preferred usage::

    almasix new myapp                     # asks: stack, database, tests, git, venv/install
    almasix new myapp --no-interaction    # asks nothing, takes the defaults
    almasix new myapp --stack bootstrap --database pgsql --git --install --migrate
"""

from __future__ import annotations

from pathlib import Path

import typer

from almasix import __version__
from almasix.installer.options import Answers, resolve_plan
from almasix.installer.scaffold import (
    DATABASE_NAMES,
    STACK_NAMES,
    ScaffoldError,
    scaffold_app,
)
from almasix.installer.steps import StepResult, run_steps

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


@app.command("stacks")
def stacks() -> None:
    """List the frontend stacks `almasix new --stack` accepts."""
    from almasix.installer.scaffold import DATABASES, STACKS

    typer.secho("Stacks", bold=True)
    for stack in STACKS:
        typer.echo(f"  {stack.name:<10} {stack.label} — {stack.description}")
    typer.secho("\nDatabases", bold=True)
    for database in DATABASES:
        extra = f" (needs `pip install {database.extra}`)" if database.extra else ""
        typer.echo(f"  {database.name:<10} {database.label}{extra}")


@app.command("new")
def new(
    name: str = typer.Argument(..., help="Application directory name"),
    path: Path | None = typer.Option(
        None,
        "--path",
        help="Parent directory (default: current working directory)",
    ),
    stack: str | None = typer.Option(
        None,
        "--stack",
        help=f"Frontend stack: {', '.join(STACK_NAMES)} (default: tailwind)",
    ),
    database: str | None = typer.Option(
        None,
        "--database",
        help=f"Database: {', '.join(DATABASE_NAMES)} (default: sqlite)",
    ),
    tests: bool | None = typer.Option(
        None,
        "--tests/--no-tests",
        help="Scaffold the pytest suite under tests/ (default: yes)",
    ),
    git: bool | None = typer.Option(
        None,
        "--git/--no-git",
        help="Initialize a git repository and commit (default: no)",
    ),
    branch: str = typer.Option(
        "main",
        "--branch",
        help="Initial branch name for --git",
    ),
    install: bool | None = typer.Option(
        None,
        "--install/--no-install",
        help="Create .venv and install Python deps with -e . (default: no unless asked)",
    ),
    installer: str = typer.Option(
        "auto",
        "--installer",
        help="Which installer to use: auto, uv, pip",
    ),
    npm: bool | None = typer.Option(
        None,
        "--npm/--no-npm",
        help="Run npm install and npm run build (default: no unless asked)",
    ),
    migrate: bool | None = typer.Option(
        None,
        "--migrate/--no-migrate",
        help="Run default migrations after installing (users, sessions, …; default: no unless asked)",
    ),
    stubs: Path | None = typer.Option(
        None,
        "--stubs",
        help="Scaffold from a published stub tree (smith stub:publish --scaffold)",
    ),
    no_interaction: bool = typer.Option(
        False,
        "--no-interaction",
        "-n",
        help="Ask nothing; every unset option takes its documented default",
    ),
) -> None:
    """Create a new Almasix application."""
    destination = (path or Path.cwd()) / name
    answers = Answers(
        stack=stack,
        database=database,
        tests=tests,
        git=git,
        branch=branch,
        install=install,
        installer=installer,
        npm=npm,
        migrate=migrate,
        stubs=stubs,
    )

    # Without a terminal there is nobody to answer, and a prompt's displayed
    # default is not the documented one: `--install` shows Yes because that is
    # what someone at a keyboard usually wants, while the non-interactive
    # default is No precisely so a script never installs anything unasked.
    from almasix.console.prompts.types import is_interactive

    try:
        plan = resolve_plan(
            name,
            destination,
            answers,
            interactive=not no_interaction and is_interactive(),
        )
        root = scaffold_app(
            name,
            destination=destination,
            stack=plan.stack,
            database=plan.database,
            tests=plan.tests,
            stubs=plan.stubs,
        )
    except ScaffoldError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    typer.secho(f"Created Almasix application: {root}", fg=typer.colors.GREEN)
    typer.echo(
        f"  stack     {plan.stack_info.label}\n"
        f"  database  {plan.database_info.label}\n"
        f"  tests     {'tests/ with pytest' if plan.tests else 'none'}"
    )

    results = run_steps(plan, root)
    _report(results)
    _next_steps(plan, root, results)

    if any(result.failed for result in results):
        raise typer.Exit(code=1)


def _report(results: list[StepResult]) -> None:
    for result in results:
        if not result.ran:
            continue
        if result.ok:
            typer.secho(f"  {result.name:<9} {result.detail}", fg=typer.colors.GREEN)
        else:
            typer.secho(
                f"  {result.name:<9} failed: {result.detail}",
                fg=typer.colors.RED,
                err=True,
            )


def _next_steps(plan: object, root: Path, results: list[StepResult]) -> None:
    """Print only the steps that are actually still owed."""
    from almasix.installer.options import InstallPlan

    assert isinstance(plan, InstallPlan)
    done = {result.name for result in results if result.ran and result.ok}

    lines = [f"  cd {root.name}"]
    if "venv" not in done and "install" not in done:
        lines.append("  python -m venv .venv && source .venv/bin/activate")
        extra = plan.database_info.extra
        lines.append(
            f"  pip install -e . {'&& pip install ' + extra if extra else ''}".rstrip()
        )
    elif "install" not in done:
        lines.append("  source .venv/bin/activate")
        extra = plan.database_info.extra
        lines.append(
            f"  pip install -e . {'&& pip install ' + extra if extra else ''}".rstrip()
        )
    else:
        lines.append("  source .venv/bin/activate")
    if "migrate" not in done:
        lines.append("  python smith migrate")
    if plan.uses_node and "npm" not in done:
        lines.append("  npm install && npm run build")
    lines.append("  python smith serve")

    typer.echo("\nNext steps:")
    typer.echo("\n".join(lines))
    typer.echo("")


if __name__ == "__main__":
    app()
