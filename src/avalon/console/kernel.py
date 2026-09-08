"""Discover and run Avalon console commands."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import pkgutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import typer

from avalon.console import isolation
from avalon.console.command import Command, parse_signature
from avalon.console.events import CommandFinished, CommandStarting, ConsoleStarting
from avalon.console.exceptions import CommandNotFound

if TYPE_CHECKING:
    from avalon.framework.application import Application

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

    @classmethod
    def from_cwd(cls, cwd: Path | None = None) -> ConsoleKernel:
        from avalon.framework.application import Application

        root = Path(cwd or Path.cwd())
        application = Application(root)
        application.load_environment()
        application.load_configuration()
        application.apply_middleware_callbacks()
        application.register_configured_providers()
        application.boot()
        application._bootstrapped = True  # noqa: SLF001
        kernel = cls(application)
        kernel.discover()
        return kernel

    def discover(self) -> None:
        from avalon.console.facade import Artisan, drain_pending

        self._load_package("avalon.console.commands")
        self._load_package("app.console.commands")
        self._load_path(self.app.path("app", "console", "commands"))
        Artisan.set_kernel(self)
        drain_pending(self)
        self._dispatch(ConsoleStarting(sorted(self.commands)))

    def register(self, command_cls: type[Command]) -> None:
        if not command_cls.signature:
            return
        self.commands[command_cls.name()] = command_cls

    def _load_package(self, package_name: str) -> None:
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return
        paths = list(getattr(package, "__path__", []))
        for module_info in pkgutil.iter_modules(paths):
            module = importlib.import_module(f"{package_name}.{module_info.name}")
            self._register_module(module)

    def _load_path(self, directory: Path) -> None:
        if not directory.is_dir():
            return
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith("_"):
                continue
            module_name = f"avalon_app_command_{file.stem}_{abs(hash(file))}"
            spec = importlib.util.spec_from_file_location(module_name, file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            self._register_module(module)

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
        from avalon.console.facade import Artisan, drain_pending
        from avalon.console.scheduling import schedule

        Artisan.set_kernel(self)
        path = self.app.path("routes", "console.py")
        if not path.is_file():
            return
        baseline = _loaded_console_routes.get(path)
        if baseline is None:
            _loaded_console_routes[path] = len(schedule.events)
        else:
            del schedule.events[baseline:]
        module_name = f"avalon_console_routes_{abs(hash(path))}"
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
        arguments = dict(arguments or {})
        options = dict(options or {})
        self._dispatch(CommandStarting(name, arguments, options))
        try:
            code = self._run_instance(instance, arguments, options)
        except Exception as exc:
            from avalon.debug import DumpAndDie

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

        instance._arguments = arguments  # noqa: SLF001 - isolatable_id() may read input
        instance._options = options  # noqa: SLF001
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
            from avalon.events.facade import Event

            Event.dispatch(event)
        except Exception:  # pragma: no cover - events are best effort in the console
            pass

    def _report_exception(self, exc: BaseException) -> None:
        try:
            from avalon.exceptions.handler import Handler

            if self.app.container.bound(Handler):
                handler = self.app.make(Handler)
            else:
                handler = Handler(self.app)
            handler.report(exc)
        except Exception:
            pass
        typer.secho(f"{type(exc).__name__}: {exc}", fg=typer.colors.RED, err=True)

    def register_on_typer(self, typer_app: typer.Typer) -> None:
        existing = {cmd.name for cmd in typer_app.registered_commands}
        for name, command_cls in sorted(self.commands.items()):
            if command_cls.hidden or name in existing:
                continue
            self._attach(typer_app, command_cls)

    def _attach(self, typer_app: typer.Typer, command_cls: type[Command]) -> None:
        name = command_cls.name()

        def callback(ctx: typer.Context) -> None:
            code = self.run_argv(name, list(ctx.args))
            if code:
                raise typer.Exit(code=code)

        callback.__doc__ = command_cls.description or command_cls.__doc__
        typer_app.command(
            name=name,
            help=command_cls.description or None,
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
                argv, index, f"{meta['name']}={inline}" if inline else meta["name"], by_name, options
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
