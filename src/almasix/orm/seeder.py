"""Database seeders — Laravel ``Seeder`` / ``db:seed`` / ``migrate --seed`` parity."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
import time
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from almasix.orm.inflector import snake

_called: list[Any] = []


class SeederError(RuntimeError):
    """Raised when a seeder cannot be loaded or executed."""


class Seeder:
    """Base class for database seeders (Laravel ``Illuminate\\Database\\Seeder``)."""

    def __init__(self) -> None:
        self.container: Any | None = None
        self.command: Any | None = None  # optional Typer/console output hook

    async def run(self, *args: Any, **kwargs: Any) -> None:
        """Override in subclasses — called by ``db:seed`` / ``migrate --seed``."""

    async def call(
        self,
        classes: type[Seeder] | str | Sequence[type[Seeder] | str],
        silent: bool = False,
        parameters: dict[str, Any] | None = None,
    ) -> Seeder:
        """Run one or more seeder classes (Laravel ``call``)."""
        parameters = parameters or {}
        for item in _wrap(classes):
            seeder = self.resolve(item)
            name = type(seeder).__name__
            if not silent:
                self._announce(name, "RUNNING")
            started = time.perf_counter()
            await seeder(parameters)
            if not silent:
                elapsed_ms = (time.perf_counter() - started) * 1000
                self._announce(name, f"{elapsed_ms:.0f} ms DONE")
            _called.append(item)
        return self

    async def call_with(
        self,
        classes: type[Seeder] | str | Sequence[type[Seeder] | str],
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Run seeders with parameters passed into ``run`` (Laravel ``callWith``)."""
        await self.call(classes, silent=False, parameters=parameters or {})

    async def call_silent(
        self,
        classes: type[Seeder] | str | Sequence[type[Seeder] | str],
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Run seeders without console output (Laravel ``callSilent``)."""
        await self.call(classes, silent=True, parameters=parameters or {})

    async def call_once(
        self,
        classes: type[Seeder] | str | Sequence[type[Seeder] | str],
        silent: bool = False,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """Run each seeder at most once per process (Laravel ``callOnce``)."""
        for item in _wrap(classes):
            if item in _called:
                continue
            await self.call(item, silent=silent, parameters=parameters or {})

    def resolve(self, class_: type[Seeder] | str) -> Seeder:
        """Instantiate a seeder, optionally via the application container."""
        if isinstance(class_, str):
            class_ = _import_seeder_class(class_)
        if not isinstance(class_, type) or not issubclass(class_, Seeder):
            raise SeederError(f"{class_!r} is not a Seeder subclass")

        if self.container is not None:
            try:
                instance = self.container.make(class_)
            except Exception:
                instance = class_()
        else:
            instance = class_()

        if not isinstance(instance, Seeder):
            raise SeederError(f"{class_!r} did not resolve to a Seeder")
        instance.set_container(self.container)
        instance.set_command(self.command)
        return instance

    def set_container(self, container: Any) -> Seeder:
        self.container = container
        return self

    def set_command(self, command: Any) -> Seeder:
        self.command = command
        return self

    async def __call__(self, parameters: dict[str, Any] | None = None) -> Any:
        """Run ``run`` with optional kwargs (Laravel ``__invoke``)."""
        parameters = parameters or {}

        async def invoke() -> Any:
            result = self.run(**parameters)
            if inspect.isawaitable(result):
                return await result
            return result

        if uses_without_model_events(type(self)):
            with without_model_events():
                return await invoke()
        return await invoke()

    def _announce(self, name: str, status: str) -> None:
        if self.command is not None and hasattr(self.command, "echo"):
            self.command.echo(f"{name:40} {status}")
        else:
            print(f"{name:40} {status}")


def reset_called() -> None:
    """Clear the ``call_once`` registry (tests)."""
    _called.clear()


def uses_without_model_events(cls: type) -> bool:
    return WithoutModelEvents in getattr(cls, "__mro__", ())


@contextmanager
def without_model_events() -> Any:
    """Temporarily disable model event dispatch (Laravel ``WithoutModelEvents``)."""
    from almasix.orm import model as model_mod

    previous = getattr(model_mod, "_EVENTS_DISABLED", False)
    model_mod._EVENTS_DISABLED = True
    try:
        yield
    finally:
        model_mod._EVENTS_DISABLED = previous


class WithoutModelEvents:
    """Mixin — seed without firing model events (Laravel ``WithoutModelEvents``)."""


async def invoke_seeder(
    class_: type[Seeder] | str | None = None,
    *,
    base_path: Path | None = None,
    container: Any | None = None,
    command: Any | None = None,
    parameters: dict[str, Any] | None = None,
) -> Any:
    """Resolve and await a seeder (default: ``database/seeders/database_seeder.py``)."""
    base = Path(base_path or Path.cwd())
    target: type[Seeder] | str
    if class_ is None:
        target = load_database_seeder(base)
    else:
        target = class_

    root = Seeder()
    root.set_container(container)
    root.set_command(command)
    seeder = root.resolve(target)
    return await seeder(parameters or {})


def run_seeder(
    class_: type[Seeder] | str | None = None,
    *,
    base_path: Path | None = None,
    container: Any | None = None,
    command: Any | None = None,
    parameters: dict[str, Any] | None = None,
) -> Any:
    """Sync entry for CLI — wraps :func:`invoke_seeder` in ``asyncio.run``."""
    import asyncio

    return asyncio.run(
        invoke_seeder(
            class_,
            base_path=base_path,
            container=container,
            command=command,
            parameters=parameters,
        )
    )


def load_database_seeder(base_path: Path) -> type[Seeder]:
    """Load ``database/seeders/database_seeder.py`` → ``DatabaseSeeder``."""
    path = base_path / "database" / "seeders" / "database_seeder.py"
    if not path.is_file():
        raise SeederError(
            f"Missing {path.relative_to(base_path)}. "
            "Scaffold ships DatabaseSeeder; create one with `python smith make:seeder DatabaseSeeder`."
        )
    module = _load_module(path, "almasix_database_seeder")
    cls = getattr(module, "DatabaseSeeder", None)
    if not isinstance(cls, type) or not issubclass(cls, Seeder):
        raise SeederError(f"{path.name} must define class DatabaseSeeder(Seeder)")
    return cls


def resolve_seeder_class(name: str, *, base_path: Path | None = None) -> type[Seeder]:
    """Resolve ``UserSeeder`` or a dotted import path to a Seeder subclass."""
    if "." in name and "/" not in name and not name.endswith(".py"):
        return _import_seeder_class(name)

    base = Path(base_path or Path.cwd())
    class_name = name.replace("\\", "/").split("/")[-1].removesuffix(".py")
    path = base / "database" / "seeders" / f"{snake(class_name)}.py"
    if not path.is_file():
        raise SeederError(f"Seeder not found: database/seeders/{snake(class_name)}.py")

    module = _load_module(path, f"almasix_seeder_{path.stem}")
    cls = getattr(module, class_name, None)
    if cls is None:
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, Seeder)
                and value is not Seeder
                and value.__module__ == module.__name__
            ):
                cls = value
                break
    if not isinstance(cls, type) or not issubclass(cls, Seeder):
        raise SeederError(f"{path.name} does not define a Seeder subclass named {class_name}")
    return cls


def make_seeder(name: str, directory: Path, *, force: bool = False) -> Path:
    """Write ``database/seeders/<snake>.py`` with a Seeder subclass."""
    class_name = name.replace("\\", "/").split("/")[-1]
    if not class_name:
        raise SeederError("A seeder class name is required.")
    module_name = snake(class_name)
    directory.mkdir(parents=True, exist_ok=True)
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    target = directory / f"{module_name}.py"
    if target.exists() and not force:
        raise SeederError(f"{target.name} already exists. Use --force to overwrite.")
    target.write_text(
        f'''"""{class_name}."""

from __future__ import annotations

from almasix.orm import Seeder


class {class_name}(Seeder):
    """{class_name}."""

    async def run(self) -> None:
        """Seed the application's database."""
''',
        encoding="utf-8",
    )
    return target


def _wrap(classes: type[Seeder] | str | Sequence[type[Seeder] | str]) -> list[type[Seeder] | str]:
    if isinstance(classes, (list, tuple)):
        return list(classes)
    return [classes]


def _import_seeder_class(dotted: str) -> type[Seeder]:
    module_path, _, name = dotted.rpartition(".")
    if not module_path:
        raise SeederError(f"Invalid seeder path: {dotted!r}")
    module = importlib.import_module(module_path)
    cls = getattr(module, name)
    if not isinstance(cls, type) or not issubclass(cls, Seeder):
        raise SeederError(f"{dotted!r} is not a Seeder subclass")
    return cls


def _load_module(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SeederError(f"Cannot load seeder {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    # Ensure app root is importable (`database.seeders.*`, `app.*`)
    app_root = str(path.parent.parent.parent)
    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    spec.loader.exec_module(module)
    return module
