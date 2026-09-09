"""Discover and run Almasix console commands."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from almasix.console import isolation
from almasix.console.command import Command, parse_signature
from almasix.console.events import CommandFinished, CommandStarting, ConsoleStarting
from almasix.console.exceptions import CommandNotFound
from almasix.console.help import help_text, metavar

if TYPE_CHECKING:
    from almasix.framework.application import Application

#: Injected into isolatable commands so ``--isolated[=CODE]`` always parses.
_ISOLATED_OPTION: dict[str, Any] = {
    "name": "isolated",
    "shortcut": "",
    "description": "Do not run if another instance of the command is already running",
    "default": None,
    "is_flag": False,
    "array": False,
}


# ``routes/console.py`` files already executed, and how many scheduled tasks
# existed before each one ran.
_loaded_console_routes: dict[Path, int] = {}


@dataclass(frozen=True)
class DiscoveryFailure:
    """A command module that would not import.

    Discovery keeps the modules that do work and collects these, so one broken
    file costs you that file's commands rather than the whole directory's.
    """

    module: str
    error: BaseException

    def summary(self) -> str:
        return f"{self.module}: {type(self.error).__name__}: {self.error}"


def _isolated_exit_code(isolated: Any) -> int:
    """``--isolated`` exits successfully unless given an explicit code."""
    if isinstance(isolated, bool):
        return Command.SUCCESS
    try:
        return int(isolated)
    except (TypeError, ValueError):
        return Command.SUCCESS


class ConsoleKernel:
    """Registers Command subclasses and runs them with M8 exception reporting."""

    def __init__(self, app: Application) -> None:
        self.app = app
        self.commands: dict[str, type[Command]] = {}
        #: Command modules that could not be imported, newest last.
        self.failures: list[DiscoveryFailure] = []

    @classmethod
    def from_cwd(cls, cwd: Path | None = None) -> ConsoleKernel:
        """Boot the application in ``cwd``, then discover its commands."""
        kernel = cls.for_cwd(cwd)
        kernel.boot_application()
        kernel.discover()
        return kernel

    @classmethod
    def for_cwd(cls, cwd: Path | None = None) -> ConsoleKernel:
        """A kernel over ``cwd`` with nothing booted yet.

        Generators and ``version`` need no application, so the front door
        starts here and boots only when a command asks for it.
        """
        from almasix.framework.application import Application

        return cls(Application(Path(cwd or Path.cwd())))

    def boot_application(self) -> None:
        """Env, config, providers, boot — everything except the HTTP routes."""
        if self.app.is_bootstrapped:
            return
        self.app.load_environment()
        self.app.load_configuration()
        self.app.apply_middleware_callbacks()
        self.app.register_configured_providers()
        self.app.boot()
        self.app._bootstrapped = True

    def discover(self) -> None:
        from almasix.console.facade import Artisan, drain_pending

        self.discover_framework_commands()
        # An app's command directory is usually an importable package. When it
        # is not, load the files directly — but never both, or one broken file
        # is reported twice.
        if not self._load_package("app.console.commands"):
            self._load_path(self.app.path("app", "console", "commands"))
        Artisan.set_kernel(self)
        drain_pending(self)
        self._dispatch(ConsoleStarting(sorted(self.commands)))

    def discover_framework_commands(self) -> None:
        """Register the commands Almasix itself ships — no application needed."""
        self._load_package("almasix.console.commands")

    def register(self, command_cls: type[Command]) -> None:
        if not command_cls.signature:
            return
        self.commands[command_cls.name()] = command_cls
        for alias in command_cls.aliases:
            self.commands[alias] = command_cls

    def _load_package(self, package_name: str) -> bool:
        """Register the commands in a package; ``False`` if there is no package."""
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return False
        paths = list(getattr(package, "__path__", []))
        for module_info in pkgutil.iter_modules(paths):
            name = f"{package_name}.{module_info.name}"
            try:
                module = importlib.import_module(name)
            except Exception as exc:
                self.failures.append(DiscoveryFailure(name, exc))
                continue
            if self._half_imported(module):
                # Discovery ran from inside this module's own import, so its
                # commands do not exist yet. Skipping quietly would drop them
                # from the CLI depending on what was imported first.
                self.failures.append(
                    DiscoveryFailure(
                        name, ImportError(f"{name} is still importing — circular import")
                    )
                )
                continue
            self._register_module(module)
        return True

    def _load_path(self, directory: Path) -> None:
        """Load command files directly, for when the import name is unusable.

        ``app`` is a generic package name, and an interpreter that has already
        imported a different application's ``app`` owns it. Loading each file
        under a synthetic module name gets this application's commands anyway.
        """
        if not directory.is_dir():
            return
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith("_"):
                continue
            module_name = f"almasix_app_command_{file.stem}_{abs(hash(file))}"
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception as exc:
                del sys.modules[module_name]
                self.failures.append(DiscoveryFailure(str(file), exc))
                continue
            self._register_module(module)

    @staticmethod
    def _half_imported(module: Any) -> bool:
        return bool(getattr(getattr(module, "__spec__", None), "_initializing", False))

    def _register_module(self, module: Any) -> None:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Command) and obj is not Command and obj.signature:
                self.register(obj)

    def load_console_routes(self) -> None:
        """Load ``routes/console.py`` (schedule DSL + ``Artisan.command`` closures).

        The file is executed again on every call, because each kernel needs the
        closure commands it defines. The scheduled tasks from the previous run
        are dropped first, so loading twice does not schedule everything twice.
        """
        from almasix.console.facade import Artisan, drain_pending
        from almasix.console.scheduling import schedule

        Artisan.set_kernel(self)
        path = self.app.path("routes", "console.py")
        if not path.is_file():
            return
        baseline = _loaded_console_routes.get(path)
        if baseline is None:
            _loaded_console_routes[path] = len(schedule.events)
        else:
            del schedule.events[baseline:]
        module_name = f"almasix_console_routes_{abs(hash(path))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        drain_pending(self)

    def run_command(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> int:
        command_cls = self._resolve(name)
        instance = command_cls(self.app)
        instance.kernel = self
        arguments = dict(arguments or {})
        options = dict(options or {})
        self._dispatch(CommandStarting(name, arguments, options))
        try:
            code = self._run_instance(instance, arguments, options)
        except Exception as exc:
            from almasix.debug import DumpAndDie

            if isinstance(exc, DumpAndDie):
                # dd() already pretty-printed; exit cleanly (not an app error).
                self._dispatch(CommandFinished(name, arguments, options, 0))
                return 0
            self._report_exception(exc)
            raise
        self._dispatch(CommandFinished(name, arguments, options, code))
        return code

    def _run_instance(
        self,
        instance: Command,
        arguments: dict[str, Any],
        options: dict[str, Any],
    ) -> int:
        isolated = options.get("isolated") if instance.isolatable else None
        if not isolated:
            return instance.run(arguments=arguments, options=options)

        instance._arguments = arguments
        instance._options = options
        lock = isolation.acquire(
            instance.isolatable_id(),
            instance.isolation_lock_seconds(),
            self.app.base_path,
        )
        if lock is None:
            return _isolated_exit_code(isolated)
        try:
            return instance.run(arguments=arguments, options=options)
        finally:
            lock.release()

    def run_argv(self, name: str, argv: list[str]) -> int:
        command_cls = self._resolve(name)
        _, arguments_meta, options_meta = parse_signature(command_cls.signature)
        if command_cls.isolatable:
            options_meta = [*options_meta, _ISOLATED_OPTION]
        arguments, options = _parse_argv(
            argv,
            arguments_meta,
            options_meta,
            prompt_for_missing=command_cls.prompts_for_missing_input,
        )
        if command_cls.prompts_for_missing_input:
            arguments = self._prompt_for_missing(command_cls, arguments, arguments_meta)
        return self.run_command(name, arguments=arguments, options=options)

    def _prompt_for_missing(
        self,
        command_cls: type[Command],
        arguments: dict[str, Any],
        arguments_meta: list[dict[str, Any]],
    ) -> dict[str, Any]:
        missing = [
            meta["name"]
            for meta in arguments_meta
            if not meta["optional"] and meta["name"].replace("-", "_") not in arguments
        ]
        if not missing:
            return arguments
        prompter = command_cls(self.app)
        for argument_name in missing:
            arguments[argument_name.replace("-", "_")] = prompter.prompt_for_missing_argument(
                argument_name
            )
        return arguments

    def _resolve(self, name: str) -> type[Command]:
        command_cls = self.commands.get(name)
        if command_cls is None:
            raise CommandNotFound(name)
        return command_cls

    def _dispatch(self, event: Any) -> None:
        try:
            from almasix.events.facade import Event

            Event.dispatch(event)
        except Exception:  # pragma: no cover - events are best effort in the console
            pass

    def _report_exception(self, exc: BaseException) -> None:
        try:
            from almasix.exceptions.handler import Handler

            if self.app.container.bound(Handler):
                handler = self.app.make(Handler)
            else:
                handler = Handler(self.app)
            handler.report(exc)
        except Exception:
            pass
        typer.secho(f"{type(exc).__name__}: {exc}", fg=typer.colors.RED, err=True)

    def register_on_typer(
        self,
        typer_app: typer.Typer,
        *,
        resolve: Callable[[], ConsoleKernel] | None = None,
    ) -> None:
        """Put every registered command behind the argv front door.

        ``resolve`` says which kernel should run the command when it is finally
        typed, which is not necessarily this one — the front door rebuilds its
        kernel when the working directory changes.
        """
        running = resolve or (lambda: self)
        existing = {cmd.name for cmd in typer_app.registered_commands}
        for name, command_cls in sorted(self.commands.items()):
            if command_cls.hidden or name in existing:
                continue
            self._attach(typer_app, name, command_cls, running)

    def _attach(
        self,
        typer_app: typer.Typer,
        name: str,
        command_cls: type[Command],
        resolve: Callable[[], ConsoleKernel],
    ) -> None:
        def callback(ctx: typer.Context) -> None:
            kernel = resolve()
            if command_cls.boots_application:
                kernel.boot_application()
            code = kernel.run_argv(name, list(ctx.args))
            if code:
                raise typer.Exit(code=code)

        body = help_text(command_cls)
        callback.__doc__ = body or command_cls.__doc__
        typer_app.command(
            name=name,
            help=body or None,
            # Click prints the usage line from this, and Almasix's parser — not
            # Click's — reads the argv, so the signature has to describe itself.
            options_metavar=metavar(command_cls),
            context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        )(callback)


def _parse_argv(
    argv: list[str],
    arguments_meta: list[dict[str, Any]],
    options_meta: list[dict[str, Any]],
    *,
    prompt_for_missing: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    by_name = {meta["name"]: meta for meta in options_meta}
    by_shortcut = {meta["shortcut"]: meta for meta in options_meta if meta.get("shortcut")}
    options = _option_defaults(options_meta)

    positional: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            positional.extend(argv[index + 1 :])
            break
        if token.startswith("--"):
            index = _consume_option(argv, index, token[2:], by_name, options)
        elif len(token) > 1 and token.startswith("-") and token[1] in by_shortcut:
            meta = by_shortcut[token[1]]
            inline = token[2:].lstrip("=")
            index = _consume_option(
                argv,
                index,
                f"{meta['name']}={inline}" if inline else meta["name"],
                by_name,
                options,
            )
        else:
            positional.append(token)
        index += 1

    return (
        _collect_arguments(positional, arguments_meta, prompt_for_missing=prompt_for_missing),
        options,
    )


def _option_defaults(options_meta: list[dict[str, Any]]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for meta in options_meta:
        key = meta["name"].replace("-", "_")
        if meta["array"]:
            defaults[key] = list(meta["default"] or [])
        elif meta["is_flag"]:
            defaults[key] = False
        else:
            defaults[key] = meta["default"]
    return defaults


def _consume_option(
    argv: list[str],
    index: int,
    raw: str,
    by_name: dict[str, dict[str, Any]],
    options: dict[str, Any],
) -> int:
    """Store one option, returning the argv index that was consumed last."""
    name, separator, inline = raw.partition("=")
    meta = by_name.get(name)
    key = name.replace("-", "_")

    if separator:
        value: Any = inline
    elif meta is not None and meta["is_flag"]:
        value = True
    elif index + 1 < len(argv) and not argv[index + 1].startswith("-"):
        index += 1
        value = argv[index]
    else:
        value = True

    if meta is not None and meta["array"]:
        options.setdefault(key, [])
        options[key] = [*options[key], value]
    else:
        options[key] = value
    return index


def _collect_arguments(
    positional: list[str],
    arguments_meta: list[dict[str, Any]],
    *,
    prompt_for_missing: bool,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {}
    pos_index = 0
    for meta in arguments_meta:
        key = meta["name"].replace("-", "_")
        if meta["array"]:
            remaining = positional[pos_index:]
            arguments[key] = remaining or list(meta["default"] or [])
            pos_index = len(positional)
            continue
        if pos_index < len(positional):
            arguments[key] = positional[pos_index]
            pos_index += 1
        elif meta["default"] is not None:
            arguments[key] = meta["default"]
        elif meta["optional"]:
            arguments[key] = None
        elif prompt_for_missing:
            continue  # the kernel prompts for it
        else:
            raise typer.BadParameter(f"Missing required argument: {meta['name']}")
    return arguments
