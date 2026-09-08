"""Class generators behind `python smith make:*`."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from almasix.console.stub import render
from almasix.orm.inflector import snake

_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VIEW_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_-]*$")


class MakeError(ValueError):
    """Invalid generator request."""


@dataclass(frozen=True)
class Blueprint:
    directory: tuple[str, ...]
    stub: str

BLUEPRINTS: dict[str, Blueprint] = {
    "controller": Blueprint(("app", "http", "controllers"), "controller.stub"),
    "middleware": Blueprint(("app", "http", "middleware"), "middleware.stub"),
    "provider": Blueprint(("app", "providers"), "provider.stub"),
    "request": Blueprint(("app", "http", "requests"), "request.stub"),
    "resource": Blueprint(("app", "http", "resources"), "resource.stub"),
    "model": Blueprint(("app", "models"), "model.stub"),
    "seeder": Blueprint(("database", "seeders"), "seeder.stub"),
    "command": Blueprint(("app", "console", "commands"), "command.stub"),
    "job": Blueprint(("app", "jobs"), "job.queued.stub"),
    "mail": Blueprint(("app", "mail"), "mail.stub"),
    "notification": Blueprint(("app", "notifications"), "notification.stub"),
    "rule": Blueprint(("app", "rules"), "rule.stub"),
    "cast": Blueprint(("app", "casts"), "cast.stub"),
    "exception": Blueprint(("app", "exceptions"), "exception.stub"),
    "enum": Blueprint(("app", "enums"), "enum.stub"),
    "interface": Blueprint(("app", "contracts"), "interface.stub"),
    "observer": Blueprint(("app", "observers"), "observer.plain.stub"),
    # A plain class lands wherever its name says: ``Services/Ledger`` →
    # ``app/services/ledger.py``.
    "class": Blueprint(("app",), "class.stub"),
}

def make_component(
    name: str,
    *,
    base_path: Path,
    force: bool = False,
    class_based: bool = False,
) -> Path:
    """Create an anonymous view component, optionally with a class.

    Returns the path to the ``.prism.html`` template (class path is a sibling
    under ``app/view/components`` when ``class_based`` is true).
    """
    from almasix.orm.inflector import studly

    parts = [part for part in name.replace("\\", "/").split("/") if part]
    if not parts:
        raise MakeError("A component name is required.")
    for part in parts:
        if not _SEGMENT_RE.match(part):
            raise MakeError(
                f"Invalid name segment {part!r}. Use letters, numbers, and underscores; "
                "must start with a letter."
            )
    rel_parts = tuple(snake(part) for part in parts)
    directory = base_path.joinpath("resources", "views", "components", *rel_parts[:-1])
    target = directory / f"{rel_parts[-1]}.prism.html"
    if target.exists() and not force:
        raise MakeError(f"{target.relative_to(base_path)} already exists. Use --force to overwrite.")
    directory.mkdir(parents=True, exist_ok=True)
    display = "/".join(rel_parts)
    view_name = "components." + ".".join(rel_parts)
    target.write_text(
        render("component.stub", {"name": display}, base_path=base_path),
        encoding="utf-8",
    )

    if class_based:
        class_name = studly(rel_parts[-1])
        class_dir = base_path.joinpath("app", "view", "components", *rel_parts[:-1])
        class_path = class_dir / f"{rel_parts[-1]}.py"
        if class_path.exists() and not force:
            raise MakeError(
                f"{class_path.relative_to(base_path)} already exists. Use --force to overwrite."
            )
        class_dir.mkdir(parents=True, exist_ok=True)
        _ensure_packages(base_path, ("app", "view", "components") + rel_parts[:-1])
        class_path.write_text(
            render(
                "component-class.stub",
                {"class": class_name, "view": view_name},
                base_path=base_path,
            ),
            encoding="utf-8",
        )

    return target


def _split(name: str) -> tuple[tuple[str, ...], str]:
    parts = [part for part in name.replace("\\", "/").split("/") if part]
    if not parts:
        raise MakeError("A class name is required.")
    for part in parts:
        if not _SEGMENT_RE.match(part):
            raise MakeError(
                f"Invalid name segment {part!r}. Use letters, numbers, and underscores; "
                "must start with a letter."
            )
    return tuple(parts[:-1]), parts[-1]


def make(
    kind: str,
    name: str,
    *,
    base_path: Path,
    force: bool = False,
    stub: str | None = None,
    replacements: Mapping[str, str] | None = None,
) -> Path:
    """Generate a class file and return its path.

    CLI names stay PascalCase (`PostController`, `Admin/UserController`);
    packages and module files use Python snake_case
    (`app/http/controllers/admin/user_controller.py`).

    `stub` overrides the blueprint's template, which is how one generator
    offers variants (`make:job --sync`); `replacements` adds placeholder
    values on top of `class` and `command`.
    """
    blueprint = BLUEPRINTS.get(kind)
    if blueprint is None:
        raise MakeError(f"Unknown generator {kind!r}.")

    namespace, class_name = _split(name)
    package_ns = tuple(snake(part) for part in namespace)
    module_name = snake(class_name)
    directory = base_path.joinpath(*blueprint.directory, *package_ns)
    target = directory / f"{module_name}.py"
    if target.exists() and not force:
        raise MakeError(f"{target.relative_to(base_path)} already exists. Use --force to overwrite.")

    directory.mkdir(parents=True, exist_ok=True)
    _ensure_packages(base_path, blueprint.directory + package_ns)
    target.write_text(
        render(
            stub or blueprint.stub,
            {
                "class": class_name,
                "command": command_name(class_name),
                **dict(replacements or {}),
            },
            base_path=base_path,
        ),
        encoding="utf-8",
    )
    return target


def make_view(
    name: str,
    *,
    base_path: Path,
    force: bool = False,
    stub: str = "view.stub",
    replacements: Mapping[str, str] | None = None,
) -> Path:
    """Create a Prism template under ``resources/views`` and return its path.

    Names are view names, so `posts.index`, `posts/index`, and `Posts/Index`
    all reach `resources/views/posts/index.prism.html`.
    """
    parts = view_parts(name)
    directory = base_path.joinpath("resources", "views", *parts[:-1])
    target = directory / f"{parts[-1]}.prism.html"
    if target.exists() and not force:
        raise MakeError(f"{target.relative_to(base_path)} already exists. Use --force to overwrite.")

    directory.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render(
            stub,
            {"name": view_name(name), **dict(replacements or {})},
            base_path=base_path,
        ),
        encoding="utf-8",
    )
    return target


def view_parts(name: str) -> tuple[str, ...]:
    """Split a view name on dots and slashes into snake_case path segments."""
    raw = [part for part in re.split(r"[./\\]", name.removesuffix(".prism.html")) if part]
    if not raw:
        raise MakeError("A view name is required.")
    for part in raw:
        if not _VIEW_SEGMENT_RE.match(part):
            raise MakeError(
                f"Invalid name segment {part!r}. Use letters, numbers, dashes, and "
                "underscores; must start with a letter or number."
            )
    return tuple(snake(part) for part in raw)


def view_name(name: str) -> str:
    """The dotted name Prism resolves the generated template by."""
    return ".".join(view_parts(name))


def command_name(class_name: str) -> str:
    """``SendEmails`` → ``send-emails``, the signature a new command starts with."""
    dashed = "".join(
        f"-{letter.lower()}" if letter.isupper() else letter
        for letter in class_name.replace("Command", "")
    )
    return dashed.lstrip("-") or "command"

def _ensure_packages(base_path: Path, parts: tuple[str, ...]) -> None:
    """Generated directories must be importable packages."""
    for depth in range(1, len(parts) + 1):
        init = base_path.joinpath(*parts[:depth], "__init__.py")
        if not init.exists():
            init.write_text("", encoding="utf-8")
