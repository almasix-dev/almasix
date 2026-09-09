"""What ``almasix new`` is going to do, decided before it does any of it.

Every question the installer can ask has a flag, and every flag has a
documented default, so the same command is usable by a person and by CI. A
value passed on the command line is never asked about again.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from almasix.installer.scaffold import (
    DATABASES,
    STACKS,
    Database,
    Stack,
    find_database,
    find_stack,
)

#: What the installer picks when nobody is there to ask.
DEFAULTS = {
    "stack": "tailwind",
    "database": "sqlite",
    "tests": True,
    "git": False,
    "install": False,
    "npm": False,
    "migrate": False,
}


@dataclass
class InstallPlan:
    """The resolved answers, ready to execute."""

    name: str
    destination: Path
    stack: str = str(DEFAULTS["stack"])
    database: str = str(DEFAULTS["database"])
    tests: bool = bool(DEFAULTS["tests"])
    git: bool = bool(DEFAULTS["git"])
    branch: str = "main"
    install: bool = bool(DEFAULTS["install"])
    installer: str = "auto"
    npm: bool = bool(DEFAULTS["npm"])
    migrate: bool = bool(DEFAULTS["migrate"])
    stubs: Path | None = None
    #: Which values a human (rather than a flag or a default) chose.
    asked: list[str] = field(default_factory=list)

    @property
    def stack_info(self) -> Stack:
        return find_stack(self.stack)

    @property
    def database_info(self) -> Database:
        return find_database(self.database)

    @property
    def uses_node(self) -> bool:
        return self.stack_info.node


@dataclass(frozen=True)
class Answers:
    """Flags as given. ``None`` means "not answered, so it may be asked"."""

    stack: str | None = None
    database: str | None = None
    tests: bool | None = None
    git: bool | None = None
    branch: str = "main"
    install: bool | None = None
    installer: str = "auto"
    npm: bool | None = None
    migrate: bool | None = None
    stubs: Path | None = None


class Prompter:
    """The questions, behind an object a test can replace."""

    def select(self, label: str, options: Sequence[tuple[str, str]], default: str) -> str:
        from almasix.console.prompts import select

        return str(select(label, dict(options), default=default))

    def confirm(self, label: str, *, default: bool, hint: str = "") -> bool:
        from almasix.console.prompts import confirm

        return bool(confirm(label, default=default, hint=hint))


def resolve_plan(
    name: str,
    destination: Path,
    answers: Answers,
    *,
    interactive: bool = True,
    prompter: Prompter | None = None,
    node_available: Callable[[], bool] | None = None,
) -> InstallPlan:
    """Turn flags plus (optionally) prompts into a plan.

    ``interactive=False`` is ``--no-interaction``: whatever was not passed
    takes its documented default, and nothing is asked.
    """
    plan = InstallPlan(
        name=name,
        destination=destination,
        branch=answers.branch,
        installer=answers.installer,
        stubs=answers.stubs,
    )
    asker = prompter or Prompter()
    has_node = node_available or _node_available

    if answers.stack is not None:
        plan.stack = find_stack(answers.stack).name
    elif interactive:
        plan.stack = asker.select(
            "Which frontend stack?",
            [(stack.name, f"{stack.label} — {stack.description}") for stack in STACKS],
            str(DEFAULTS["stack"]),
        )
        plan.asked.append("stack")

    if answers.database is not None:
        plan.database = find_database(answers.database).name
    elif interactive:
        plan.database = asker.select(
            "Which database will this application use?",
            [(db.name, db.label) for db in DATABASES],
            str(DEFAULTS["database"]),
        )
        plan.asked.append("database")

    plan.tests = _answer(
        answers.tests,
        interactive,
        lambda: asker.confirm(
            "Scaffold a pytest suite (tests/)?",
            default=True,
            hint="smith test runs it",
        ),
        bool(DEFAULTS["tests"]),
        plan.asked,
        "tests",
    )

    plan.git = _answer(
        answers.git,
        interactive,
        lambda: asker.confirm("Initialize a git repository?", default=True),
        bool(DEFAULTS["git"]),
        plan.asked,
        "git",
    )

    plan.install = _answer(
        answers.install,
        interactive,
        lambda: asker.confirm(
            "Install Python dependencies now?",
            default=True,
            hint="uv when available, otherwise pip",
        ),
        bool(DEFAULTS["install"]),
        plan.asked,
        "install",
    )

    if plan.uses_node and has_node():
        plan.npm = _answer(
            answers.npm,
            interactive,
            lambda: asker.confirm("Run npm install and npm run build?", default=False),
            bool(DEFAULTS["npm"]),
            plan.asked,
            "npm",
        )
    else:
        # Asking about npm with no Node installed, or no package.json to
        # install, would be a question with one honest answer.
        plan.npm = bool(answers.npm) and plan.uses_node and has_node()

    if plan.install:
        plan.migrate = _answer(
            answers.migrate,
            interactive,
            lambda: asker.confirm(
                "Run the default migrations?",
                default=plan.database == "sqlite",
                hint="creates users, sessions, cache, and the queue tables",
            ),
            bool(DEFAULTS["migrate"]),
            plan.asked,
            "migrate",
        )
    else:
        # Migrating needs the application's dependencies importable.
        plan.migrate = bool(answers.migrate)

    return plan


def _answer(
    given: bool | None,
    interactive: bool,
    ask: Callable[[], bool],
    default: bool,
    asked: list[str],
    key: str,
) -> bool:
    if given is not None:
        return given
    if not interactive:
        return default
    asked.append(key)
    return ask()


def _node_available() -> bool:
    import shutil

    return shutil.which("npm") is not None
