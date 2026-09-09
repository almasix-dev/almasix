"""Scaffold a new Almasix application from the installer's stub tree.

The tree lives beside this module rather than as strings inside it, so the
files a new application starts from can be read, diffed, and overridden. Three
layers are rendered in order:

1. ``stubs/app`` — everything an application has whatever it looks like
2. ``stubs/stacks/_node`` — the Vite plugin, for stacks that use Node
3. ``stubs/stacks/<stack>`` — the CSS stack's own files

``--stubs DIR`` points the whole thing at a published copy (``smith
stub:publish --scaffold``), which is how a team keeps its own starting point.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from almasix.console.stub import render_text
from almasix.exceptions.publish import publish_errors

_APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

#: The installer's own stub tree.
STUBS = Path(__file__).parent / "stubs"

#: Suffix every stub file carries, stripped when it lands in the application.
STUB_SUFFIX = ".stub"

#: Stub names that land somewhere other than their own path.
RENAMES = {"env": (".env", ".env.example"), "gitignore": (".gitignore",)}

#: Default migrations, in the order they must run. Laravel ships the same three.
DEFAULT_MIGRATIONS = (
    ("0001_01_01_000000_create_users_table.py", "migration.users.stub", "CreateUsersTable"),
    ("0001_01_01_000001_create_cache_table.py", "migration.cache.stub", "CreateCacheTable"),
    ("0001_01_01_000002_create_jobs_table.py", "migration.queue.stub", "CreateJobsTable"),
)


@dataclass(frozen=True)
class Stack:
    """A CSS / bundler stack the installer can scaffold."""

    name: str
    label: str
    #: Whether the stack has a ``package.json`` worth running ``npm install`` on.
    node: bool
    #: Which ``errors:publish`` bundle matches the stack's look.
    error_bundle: str
    description: str


#: Every stack ``almasix new --stack`` accepts, default first.
STACKS: tuple[Stack, ...] = (
    Stack(
        name="tailwind",
        label="Tailwind CSS",
        node=True,
        error_bundle="tailwind",
        description="Vite + Tailwind CSS 4 (Laravel's default)",
    ),
    Stack(
        name="bootstrap",
        label="Bootstrap",
        node=True,
        error_bundle="bootstrap",
        description="Vite + Bootstrap 5 Sass",
    ),
    Stack(
        name="plain",
        label="Plain CSS",
        node=True,
        error_bundle="default",
        description="Vite, no CSS framework",
    ),
    Stack(
        name="none",
        label="No frontend build",
        node=False,
        error_bundle="default",
        description="Server-rendered Prism only — no Node, no build step",
    ),
)

STACK_NAMES = tuple(stack.name for stack in STACKS)


@dataclass(frozen=True)
class Database:
    """A database the installer can point a new application at."""

    name: str
    label: str
    #: ``.env`` lines this engine needs, already in the order Laravel writes them.
    env: tuple[str, ...]
    #: Extra Almasix needs installed to talk to it, if any.
    extra: str | None = None


DATABASES: tuple[Database, ...] = (
    Database(
        name="sqlite",
        label="SQLite",
        env=("DB_CONNECTION=sqlite", "DB_DATABASE=database/database.sqlite"),
    ),
    Database(
        name="pgsql",
        label="PostgreSQL",
        env=(
            "DB_CONNECTION=pgsql",
            "DB_HOST=127.0.0.1",
            "DB_PORT=5432",
            "DB_DATABASE={database}",
            "DB_USERNAME=almasix",
            "DB_PASSWORD=",
        ),
        extra="almasix[pgsql]",
    ),
    Database(
        name="mysql",
        label="MySQL",
        env=(
            "DB_CONNECTION=mysql",
            "DB_HOST=127.0.0.1",
            "DB_PORT=3306",
            "DB_DATABASE={database}",
            "DB_USERNAME=almasix",
            "DB_PASSWORD=",
        ),
        extra="almasix[mysql]",
    ),
    Database(
        name="mariadb",
        label="MariaDB",
        env=(
            "DB_CONNECTION=mariadb",
            "DB_HOST=127.0.0.1",
            "DB_PORT=3306",
            "DB_DATABASE={database}",
            "DB_USERNAME=almasix",
            "DB_PASSWORD=",
        ),
        extra="almasix[mariadb]",
    ),
)

DATABASE_NAMES = tuple(database.name for database in DATABASES)


class ScaffoldError(ValueError):
    """Invalid scaffold request."""


def validate_app_name(name: str) -> str:
    if not _APP_NAME_RE.match(name):
        raise ScaffoldError(
            f"Invalid app name {name!r}. Use letters, numbers, underscores, or hyphens; "
            "must start with a letter."
        )
    return name


def title_case(name: str) -> str:
    parts = re.split(r"[-_]+", name)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def find_stack(name: str) -> Stack:
    for stack in STACKS:
        if stack.name == name:
            return stack
    raise ScaffoldError(f"Unknown stack {name!r}. Choose one of: {', '.join(STACK_NAMES)}.")


def find_database(name: str) -> Database:
    for database in DATABASES:
        if database.name == name:
            return database
    raise ScaffoldError(f"Unknown database {name!r}. Choose one of: {', '.join(DATABASE_NAMES)}.")


def database_env(database: Database, *, app_name: str) -> str:
    return "\n".join(line.format(database=app_name) for line in database.env)


def scaffold_app(
    name: str,
    destination: Path | None = None,
    *,
    stack: str = "tailwind",
    database: str = "sqlite",
    tests: bool = True,
    stubs: Path | str | None = None,
) -> Path:
    """Create a new Almasix application directory and return its path."""
    name = validate_app_name(name)
    chosen_stack = find_stack(stack)
    chosen_database = find_database(database)

    root = (destination or Path.cwd() / name).resolve()
    if root.exists() and any(root.iterdir()):
        raise ScaffoldError(f"Directory already exists and is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    tree = Path(stubs) if stubs is not None else STUBS
    if not (tree / "app").is_dir():
        raise ScaffoldError(f"No scaffold stubs under {tree}.")

    replacements = {
        "app_name": name,
        "app_display": title_case(name),
        "app_key": _fresh_key(),
        "stack": chosen_stack.name,
        "db_connection": chosen_database.name,
        "db_label": chosen_database.label,
        "db_env": database_env(chosen_database, app_name=name),
        "frontend_section": _frontend_section(tree, chosen_stack),
    }

    _render_tree(tree / "app", root, replacements, skip_tests=not tests)
    if chosen_stack.node:
        _render_tree(tree / "stacks" / "_node", root, replacements)
    _render_tree(tree / "stacks" / chosen_stack.name, root, replacements)

    _write_default_migrations(root)
    publish_errors(root, bundle=chosen_stack.error_bundle)
    if chosen_database.name == "sqlite":
        _create_sqlite_file(root)

    # A published tree is the team's to edit, and one that dropped `smith` is
    # their choice, not a scaffolding error.
    smith = root / "smith"
    if smith.is_file():
        smith.chmod(smith.stat().st_mode | 0o111)
    return root


def publish_scaffold_stubs(base_path: Path | str, *, force: bool = False) -> tuple[Path, int]:
    """Copy the scaffold tree into ``<base_path>/stubs/scaffold``.

    Returns the directory and how many files landed, so a team can edit its own
    starting point and scaffold from it with ``almasix new --stubs``.
    """
    import shutil

    target = Path(base_path) / "stubs" / "scaffold"
    written = 0
    for source in sorted(STUBS.rglob(f"*{STUB_SUFFIX}")):
        destination = target / source.relative_to(STUBS)
        if destination.exists() and not force:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        written += 1
    return target, written


def _render_tree(
    source: Path,
    root: Path,
    replacements: Mapping[str, str],
    *,
    skip_tests: bool = False,
) -> None:
    if not source.is_dir():
        return
    for path in sorted(source.rglob(f"*{STUB_SUFFIX}")):
        relative = path.relative_to(source)
        # A README fragment is spliced into the README, not written beside it.
        if relative.name == f"readme-frontend.md{STUB_SUFFIX}":
            continue
        if skip_tests and relative.parts and relative.parts[0] == "tests":
            continue
        body = render_text(path.read_text(encoding="utf-8"), replacements)
        for target in _targets(relative):
            destination = root / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(body, encoding="utf-8")


def _targets(relative: Path) -> tuple[str, ...]:
    stem = relative.as_posix().removesuffix(STUB_SUFFIX)
    return RENAMES.get(stem, (stem,))


def _write_default_migrations(root: Path) -> None:
    """Write the tables auth, sessions, cache, and the queue read.

    Laravel ships these in its skeleton, and Almasix did not: a scaffolded app
    said "Nothing to migrate" and then failed on the first queued job.
    """
    from almasix.console import stub as console_stub

    directory = root / "database" / "migrations"
    directory.mkdir(parents=True, exist_ok=True)
    for filename, stub, class_name in DEFAULT_MIGRATIONS:
        body = console_stub.render(stub, {"class": class_name})
        (directory / filename).write_text(body, encoding="utf-8")
    gitkeep = directory / ".gitkeep"
    if gitkeep.exists():
        gitkeep.unlink()


def _frontend_section(tree: Path, stack: Stack) -> str:
    path = tree / "stacks" / stack.name / f"readme-frontend.md{STUB_SUFFIX}"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _create_sqlite_file(root: Path) -> None:
    """Touch ``database/database.sqlite`` — `laravel new` does the same."""
    path = root / "database" / "database.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def _fresh_key() -> str:
    from almasix.encryption.encrypter import generate_key

    return generate_key()
