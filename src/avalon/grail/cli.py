"""Grail — Avalon in-application CLI.

Preferred usage with the virtualenv active::

    grail version
    grail serve
    grail make:controller UserController
    grail fiddle   # aliases: tinker, repl

Or via the root ``grail`` script::

    python grail serve

Project creation uses ``avalon new``, not Grail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import uvicorn

from avalon import __version__
from avalon.exceptions.publish import BUNDLES, ErrorsPublishError, publish_errors
from avalon.grail.lang_cmd import LangError, make_lang, missing_keys, publish_lang
from avalon.grail.make import MakeError, make, make_component
from avalon.orm.inflector import table_name
from avalon.orm.migration import MigrationError, Migrator, make_migration
from avalon.orm.seeder import SeederError, resolve_seeder_class, run_seeder
from avalon.grail.ports import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_PORT,
    NoFreePortError,
    find_available_port,
)

app = typer.Typer(
    name="grail",
    help="Grail — Avalon in-app CLI. Prefer: grail … (or python grail …)",
    no_args_is_help=True,
)

DEFAULT_ASGI = "bootstrap.app:asgi"


@app.callback()
def main() -> None:
    """Run application commands."""


@app.command("version")
def version() -> None:
    """Show Avalon version."""
    typer.echo(f"Avalon {__version__}")


def _generate(kind: str, name: str, force: bool) -> None:
    try:
        path = make(kind, name, base_path=Path.cwd(), force=force)
    except MakeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(f"{kind.capitalize()} created: {path.relative_to(Path.cwd())}", fg=typer.colors.GREEN)


@app.command("make:controller")
def make_controller(
    name: str = typer.Argument(..., help="Class name, e.g. PostController or Admin/PostController"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a controller in app/http/controllers."""
    _generate("controller", name, force)


@app.command("make:middleware")
def make_middleware(
    name: str = typer.Argument(..., help="Class name, e.g. EnsureTokenIsValid"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a middleware in app/http/middleware."""
    _generate("middleware", name, force)


@app.command("make:provider")
def make_provider(
    name: str = typer.Argument(..., help="Class name, e.g. RouteServiceProvider"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a service provider in app/providers."""
    _generate("provider", name, force)


@app.command("make:request")
def make_request(
    name: str = typer.Argument(..., help="Class name, e.g. StorePostRequest"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a FormRequest in app/http/requests."""
    _generate("request", name, force)


@app.command("make:model")
def make_model(
    name: str = typer.Argument(..., help="Class name, e.g. Post or Admin/Post"),
    migration: bool = typer.Option(False, "-m", "--migration", help="Also create a migration"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a model in app/models."""
    _generate("model", name, force)
    if migration:
        class_name = name.replace("\\", "/").split("/")[-1]
        path = make_migration(
            f"create_{table_name(class_name)}_table",
            Path.cwd() / "database" / "migrations",
            table=table_name(class_name),
            create=True,
        )
        typer.secho(
            f"Migration created: {path.relative_to(Path.cwd())}",
            fg=typer.colors.GREEN,
        )


@app.command("make:migration")
def make_migration_command(
    name: str = typer.Argument(
        ...,
        help="Slug, e.g. create_posts_table or add_slug_to_posts_table",
    ),
    table: str | None = typer.Option(
        None,
        "--table",
        help="Table to alter (overrides name inference)",
    ),
    create: str | None = typer.Option(
        None,
        "--create",
        help="Table to create (overrides name inference)",
    ),
) -> None:
    """Create a migration in database/migrations.

    Names like ``create_users_table`` or ``add_x_to_posts_table`` pick the
    create/update stub and class name automatically (Laravel TableGuesser).
    """
    try:
        path = make_migration(
            name,
            Path.cwd() / "database" / "migrations",
            table=create or table,
            create=create is not None,
        )
    except MigrationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Migration created: {path.relative_to(Path.cwd())}", fg=typer.colors.GREEN)


@app.command("make:seeder")
def make_seeder_command(
    name: str = typer.Argument(..., help="Class name, e.g. UserSeeder"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a seeder in database/seeders."""
    _generate("seeder", name, force)


@app.command("make:component")
def make_component_command(
    name: str = typer.Argument(..., help="Component name, e.g. alert or forms/input"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
    class_based: bool = typer.Option(
        False,
        "--class",
        help="Also create app/view/components/… class",
    ),
) -> None:
    """Create an anonymous Caliburn component in resources/views/components."""
    try:
        path = make_component(
            name,
            base_path=Path.cwd(),
            force=force,
            class_based=class_based,
        )
    except MakeError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"Component created: {path.relative_to(Path.cwd())}",
        fg=typer.colors.GREEN,
    )
    if class_based:
        typer.secho("Class created under app/view/components/", fg=typer.colors.GREEN)


def _boot_app():
    from avalon.framework import Application

    return Application(Path.cwd()).bootstrap()


def _boot_migrator() -> Migrator:
    _boot_app()
    return Migrator(Path.cwd() / "database" / "migrations")


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


def _seed(
    *,
    class_name: str | None = None,
    app=None,
) -> None:
    application = app or _boot_app()
    target = None
    if class_name:
        target = resolve_seeder_class(class_name, base_path=Path.cwd())
    try:
        run_seeder(
            target,
            base_path=Path.cwd(),
            container=application.container,
            command=typer,
        )
    except SeederError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho("Database seeding completed successfully.", fg=typer.colors.GREEN)


@app.command("db:seed")
def db_seed(
    class_name: Optional[str] = typer.Option(
        None,
        "--class",
        help="Seeder class to run (default: DatabaseSeeder)",
    ),
) -> None:
    """Seed the database using DatabaseSeeder (or --class)."""
    _seed(class_name=class_name)


@app.command("migrate")
def migrate_command(
    seed: bool = typer.Option(False, "--seed", help="Run DatabaseSeeder after migrating"),
    seeder: Optional[str] = typer.Option(
        None,
        "--seeder",
        help="Seeder class to run when --seed is set",
    ),
) -> None:
    """Run outstanding migrations."""
    try:
        app = _boot_app()
        applied = _run_async(Migrator(Path.cwd() / "database" / "migrations").run())
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if not applied:
        typer.echo("Nothing to migrate.")
    else:
        for name in applied:
            typer.secho(f"Migrated: {name}", fg=typer.colors.GREEN)
    if seed or seeder:
        _seed(class_name=seeder, app=app)


@app.command("migrate:rollback")
def migrate_rollback(
    steps: int = typer.Option(1, "--step", help="Batches to roll back"),
) -> None:
    """Roll back the last migration batch."""
    try:
        rolled = _run_async(_boot_migrator().rollback(steps))
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if not rolled:
        typer.echo("Nothing to roll back.")
        return
    for name in rolled:
        typer.secho(f"Rolled back: {name}", fg=typer.colors.YELLOW)


@app.command("migrate:fresh")
def migrate_fresh(
    seed: bool = typer.Option(False, "--seed", help="Run DatabaseSeeder after migrating"),
    seeder: Optional[str] = typer.Option(
        None,
        "--seeder",
        help="Seeder class to run when --seed is set",
    ),
) -> None:
    """Drop all tables and re-run every migration."""
    try:
        app = _boot_app()
        applied = _run_async(Migrator(Path.cwd() / "database" / "migrations").fresh())
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    for name in applied:
        typer.secho(f"Migrated: {name}", fg=typer.colors.GREEN)
    if seed or seeder:
        _seed(class_name=seeder, app=app)


@app.command("migrate:status")
def migrate_status() -> None:
    """Show which migrations have run."""
    try:
        rows = _run_async(_boot_migrator().status())
    except Exception as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    if not rows:
        typer.echo("No migrations.")
        return
    for row in rows:
        mark = "Ran" if row["ran"] else "Pending"
        typer.echo(f"{mark:8} {row['migration']}")


@app.command("make:lang")
def make_lang_command(
    locale: str = typer.Argument(..., help="Locale tag, e.g. en or sw"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing locale tree"),
) -> None:
    """Create an empty lang/<locale>/ tree."""
    try:
        path = make_lang(locale, Path.cwd(), force=force)
    except LangError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Locale created: {path.relative_to(Path.cwd())}", fg=typer.colors.GREEN)


@app.command("lang:publish")
def lang_publish(
    force: bool = typer.Option(False, "--force", help="Overwrite existing published files"),
) -> None:
    """Publish framework language files into lang/."""
    try:
        path = publish_lang(Path.cwd(), force=force)
    except LangError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(f"Language files published: {path.relative_to(Path.cwd())}", fg=typer.colors.GREEN)


@app.command("errors:publish")
def errors_publish(
    bundle: str = typer.Option(
        "default",
        "--bundle",
        "-b",
        help=f"View look: {', '.join(BUNDLES)}",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite existing published files"),
) -> None:
    """Publish framework error views into resources/views/errors/."""
    try:
        path = publish_errors(Path.cwd(), bundle=bundle, force=force)
    except ErrorsPublishError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc
    typer.secho(
        f"Error views published ({bundle}): {path.relative_to(Path.cwd())}",
        fg=typer.colors.GREEN,
    )


@app.command("lang:missing")
def lang_missing(
    locale: str = typer.Option(..., "--locale", "-l", help="Target locale to compare"),
    fallback: str = typer.Option("en", "--fallback", help="Fallback locale"),
) -> None:
    """List keys present in the fallback locale but missing in the target."""
    missing = missing_keys(Path.cwd(), locale=locale, fallback=fallback)
    if not missing:
        typer.secho("No missing keys.", fg=typer.colors.GREEN)
        return
    for key in missing:
        typer.echo(key)
    raise typer.Exit(code=1)


@app.command("make:command")
def make_command(
    name: str = typer.Argument(..., help="Class name, e.g. SendEmails"),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file"),
) -> None:
    """Create a console command in app/console/commands."""
    _generate("command", name, force)


@app.command("list")
def list_commands() -> None:
    """List Grail commands and discovered Avalon Command classes."""
    typer.echo("Grail commands:")
    for cmd in sorted(app.registered_commands, key=lambda c: c.name or ""):
        if getattr(cmd, "hidden", False):
            continue
        help_text = (cmd.help or "").split("\n")[0]
        typer.echo(f"  {(cmd.name or ''):<22} {help_text}")
    try:
        from avalon.console.kernel import ConsoleKernel

        kernel = ConsoleKernel.from_cwd()
        if kernel.commands:
            typer.echo("\nDiscovered Command classes:")
            for name, cls in sorted(kernel.commands.items()):
                if cls.hidden:
                    continue
                typer.echo(f"  {name:<22} {cls.description}")
    except Exception as exc:
        typer.secho(f"(command discovery skipped: {exc})", fg=typer.colors.YELLOW)


def _scheduler():
    """Boot the app, load ``routes/console.py``, and hand back what runs tasks."""
    from avalon.console.kernel import ConsoleKernel
    from avalon.console.scheduling import schedule

    kernel = ConsoleKernel.from_cwd()
    kernel.load_console_routes()

    def runner(command_name: str) -> int:
        parts = command_name.split()
        return kernel.run_argv(parts[0], parts[1:])

    return kernel, schedule, runner


def _report_start(event) -> None:
    typer.echo(f"Running: {event.summary()}")


def _report_finish(outcome) -> None:
    if outcome.skipped:
        typer.secho(f"  skipped: {outcome.event.summary()}", fg=typer.colors.YELLOW)
    elif outcome.code != 0:
        typer.secho(f"  exit {outcome.code}: {outcome.event.summary()}", fg=typer.colors.RED)


@app.command("schedule:run")
def schedule_run() -> None:
    """Run the tasks that are due (wire this to cron, every minute)."""
    from avalon.console.scheduling import run_schedule

    kernel, schedule, runner = _scheduler()
    if not schedule.due_events() and not schedule.has_sub_minute_events():
        typer.echo("No scheduled tasks are ready.")
        return

    outcomes = run_schedule(
        schedule,
        base_path=kernel.app.base_path,
        runner=runner,
        on_start=_report_start,
        on_finish=_report_finish,
    )
    if any(outcome.code != 0 and not outcome.skipped for outcome in outcomes):
        raise typer.Exit(code=1)


@app.command("schedule:work")
def schedule_work(
    sleep: int = typer.Option(60, "--sleep", help="Seconds between ticks"),
) -> None:
    """Run the scheduler in the foreground, minute after minute."""
    import time

    from avalon.console.scheduling import run_schedule

    kernel, schedule, runner = _scheduler()
    typer.echo("Schedule worker started. Press Ctrl-C to stop.")
    try:
        while True:
            run_schedule(
                schedule,
                base_path=kernel.app.base_path,
                runner=runner,
                on_start=_report_start,
                on_finish=_report_finish,
            )
            time.sleep(max(1, sleep))
    except KeyboardInterrupt:
        typer.echo("Schedule worker stopped.")


@app.command("schedule:list")
def schedule_list(
    timezone: str = typer.Option("", "--timezone", help="Show next run times in this timezone"),
) -> None:
    """List the scheduled tasks and when each next runs."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    _, schedule, _ = _scheduler()
    if not schedule.events:
        typer.echo("No scheduled tasks are defined.")
        return

    zone = ZoneInfo(timezone) if timezone else None
    rows = []
    for event in schedule.events:
        moment = event.next_run_at(datetime.now())
        if zone is not None:
            moment = (
                moment.astimezone(zone) if moment.tzinfo else moment.astimezone().astimezone(zone)
            )
        rows.append(
            (
                event.frequency(),
                event.summary(),
                event.description if event.description != event.summary() else "",
                moment.strftime("%Y-%m-%d %H:%M:%S"),
            )
        )

    width = max(len(row[0]) for row in rows)
    for frequency, summary, description, next_run in rows:
        suffix = f"  ({description})" if description else ""
        typer.echo(f"  {frequency:<{width}}  {summary}{suffix}  next: {next_run}")


@app.command("schedule:test")
def schedule_test(
    name: str = typer.Option("", "--name", help="Run the task with this name or command"),
) -> None:
    """Run one scheduled task now, whatever its frequency says."""
    from avalon.console.scheduling import run_task

    kernel, schedule, runner = _scheduler()
    if not schedule.events:
        typer.echo("No scheduled tasks are defined.")
        return

    event = _pick_task(schedule.events, name)
    if event is None:
        typer.secho(f"No scheduled task matches {name!r}.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(f"Running: {event.summary()}")
    outcome = run_task(event, base_path=kernel.app.base_path, runner=runner)
    if outcome.output:
        typer.echo(outcome.output.rstrip())
    if outcome.code != 0:
        raise typer.Exit(code=outcome.code)


def _pick_task(events, name: str):
    """Find the named task, or ask which one when nothing was named."""
    if name:
        for event in events:
            if name in (event.summary(), event.mutex_name(), event.description):
                return event
        return None
    if len(events) == 1:
        return events[0]
    from avalon.console.prompts import select

    labels = {index: event.summary() for index, event in enumerate(events)}
    return events[select("Which task would you like to run?", labels, default=0)]


@app.command("schedule:interrupt")
def schedule_interrupt() -> None:
    """Stop an in-progress schedule:run at the end of this second."""
    from avalon.console.scheduling import interrupt

    kernel, schedule, _ = _scheduler()
    interrupt(base_path=kernel.app.base_path, store=schedule.cache_store)
    typer.echo("Interrupt signalled for the current minute.")


@app.command("schedule:clear-cache")
def schedule_clear_cache() -> None:
    """Release without-overlapping locks left behind by a stuck task."""
    from avalon.console.scheduling import clear_cache

    _, schedule, _ = _scheduler()
    cleared = clear_cache(schedule)
    if not cleared:
        typer.echo("No scheduled task locks were held.")
        return
    for name in cleared:
        typer.echo(f"Released lock for: {name}")


@app.command("down")
def down() -> None:
    """Put the application into maintenance mode (scheduled tasks stop)."""
    from avalon.console.kernel import ConsoleKernel

    kernel = ConsoleKernel.from_cwd()
    path = kernel.app.base_path / "storage" / "framework" / "down"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("down", encoding="utf-8")
    typer.echo("Application is now in maintenance mode.")


@app.command("up")
def up() -> None:
    """Bring the application out of maintenance mode."""
    from avalon.console.kernel import ConsoleKernel

    kernel = ConsoleKernel.from_cwd()
    path = kernel.app.base_path / "storage" / "framework" / "down"
    path.unlink(missing_ok=True)
    typer.echo("Application is now live.")


@app.command("fiddle")
@app.command("tinker")
@app.command("repl")
def fiddle() -> None:
    """Interactive Avalon REPL (aliases: ``tinker``, ``repl``)."""
    from avalon.console.kernel import ConsoleKernel
    from avalon.console.repl import start_fiddle

    kernel = ConsoleKernel.from_cwd()
    raise typer.Exit(code=start_fiddle(kernel.app))


def _register_discovered_commands() -> None:
    if not (Path.cwd() / "bootstrap" / "app.py").is_file():
        return
    try:
        from avalon.console.kernel import ConsoleKernel

        kernel = ConsoleKernel.from_cwd()
        # routes/console.py may define closure commands (Artisan.command).
        kernel.load_console_routes()
        kernel.register_on_typer(app)
    except Exception:
        return


_register_discovered_commands()


@app.command("serve")
def serve(
    host: str = typer.Option(DEFAULT_HOST, help="Bind host"),
    port: Optional[int] = typer.Option(
        None,
        help=(
            f"Bind port (default: first free port from {DEFAULT_PORT}–{MAX_PORT}; "
            "if the chosen port is busy, try the next)"
        ),
    ),
    reload: bool = typer.Option(True, help="Auto-reload on code changes"),
    app_path: str = typer.Option(
        DEFAULT_ASGI,
        "--app",
        help="ASGI import path (default: bootstrap.app:asgi)",
    ),
) -> None:
    """Serve the application with Uvicorn.

    Defaults to port 3000. If that port is taken, tries 3001, 3002, … up to 3099
    (Laravel-style). Passing ``--port`` still auto-advances from that starting port.
    """
    module_file = Path.cwd() / "bootstrap" / "app.py"
    if app_path == DEFAULT_ASGI and not module_file.is_file():
        typer.secho(
            "No bootstrap/app.py found. Run this from an Avalon app created with "
            "`avalon new`, or pass --app IMPORT_PATH.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    start_port = DEFAULT_PORT if port is None else port
    # Default discovery window is 3000–3099 (100 ports). Explicit --port uses
    # the same window size starting from the requested port.
    window = MAX_PORT - DEFAULT_PORT
    end_port = start_port + window if start_port > MAX_PORT else max(start_port, MAX_PORT)

    try:
        chosen = find_available_port(host=host, start=start_port, end=end_port)
    except NoFreePortError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc

    if chosen != start_port:
        typer.secho(
            f"Port {start_port} is in use, using http://{host}:{chosen} instead.",
            fg=typer.colors.YELLOW,
        )

    typer.echo(f"Serving {app_path} on http://{host}:{chosen}")
    uvicorn.run(app_path, host=host, port=chosen, reload=reload)


if __name__ == "__main__":
    app()
