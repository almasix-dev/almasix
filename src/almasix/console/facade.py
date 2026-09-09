"""``Smith`` façade — run, queue, and define console commands."""

from __future__ import annotations

import contextlib
import inspect
import io
import shlex
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from almasix.console.command import Command, parse_signature

if TYPE_CHECKING:
    from almasix.console.kernel import ConsoleKernel
    from almasix.framework.application import Application

#: Closure commands registered before a kernel exists (e.g. ``routes/console.py``).
_pending: list[type[Command]] = []


class ClosureCommand:
    """Handle returned by ``Smith.command()`` for fluent descriptions."""

    def __init__(self, command_cls: type[Command]) -> None:
        self.command_cls = command_cls

    def purpose(self, description: str) -> ClosureCommand:
        """Laravel ``purpose()`` — describe the closure command."""
        self.command_cls.description = description
        return self

    #: Laravel also exposes ``describe()`` for the same thing.
    describe = purpose

    def schedule(self, arguments: list[Any] | None = None) -> Any:
        """Schedule this closure command, with arguments (Laravel ``schedule()``).

        Returns the scheduled task, so the frequency is chained onto it:
        ``Smith.command(...).purpose(...).schedule(["taylor"]).daily()``.
        """
        from almasix.console.scheduling import schedule as task_schedule

        return task_schedule.command(self.command_cls.name(), arguments)


class Smith:
    """Static façade over the console kernel (Smith — Laravel ``Artisan`` parity)."""

    _kernel: ConsoleKernel | None = None
    _output: str = ""

    @classmethod
    def set_kernel(cls, kernel: ConsoleKernel | None) -> None:
        cls._kernel = kernel

    @classmethod
    def kernel(cls, app: Application | None = None) -> ConsoleKernel:
        if cls._kernel is not None:
            return cls._kernel
        if app is not None:
            resolved = _kernel_from_app(app)
            if resolved is not None:
                cls._kernel = resolved
                return resolved
        from almasix.console.kernel import ConsoleKernel

        cls._kernel = ConsoleKernel.from_cwd()
        return cls._kernel

    @classmethod
    def command(cls, signature: str, callback: Callable[..., Any]) -> ClosureCommand:
        """Laravel ``Artisan::command()`` parity — define a command from a callable."""
        command_cls = _closure_command(signature, callback)
        if cls._kernel is not None:
            cls._kernel.register(command_cls)
        else:
            _pending.append(command_cls)
        return ClosureCommand(command_cls)

    @classmethod
    def call(
        cls,
        command: str,
        parameters: dict[str, Any] | None = None,
        *,
        app: Application | None = None,
        silent: bool = False,
        kernel: ConsoleKernel | None = None,
    ) -> int:
        """Laravel ``Artisan::call()`` parity — run a command programmatically.

        ``command`` may carry its own argv (``"mail:send 1 --queue=bulk"``) or
        the values may be passed as ``parameters``. A command calling another
        passes the kernel running it, so the call stays inside its application.
        """
        kernel = kernel or cls.kernel(app)
        name, argv = _split_command(command)
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                if parameters:
                    argv = argv + _parameters_to_argv(parameters)
                code = kernel.run_argv(name, argv)
        finally:
            cls._output = buffer.getvalue()
        if not silent:
            print(cls._output, end="")
        return code

    @classmethod
    def call_silently(
        cls,
        command: str,
        parameters: dict[str, Any] | None = None,
        *,
        app: Application | None = None,
    ) -> int:
        return cls.call(command, parameters, app=app, silent=True)

    @classmethod
    def output(cls) -> str:
        """Laravel ``Artisan::output()`` parity — output captured by the last ``call``."""
        return cls._output

    @classmethod
    async def queue(
        cls,
        command: str,
        parameters: dict[str, Any] | None = None,
        *,
        connection: str | None = None,
        queue: str | None = None,
    ) -> Any:
        """Laravel ``Artisan::queue()`` parity — run a command on a queue worker.

        Awaitable because Almasix's queue dispatch is async.
        """
        from almasix.console.queued import CallQueuedCommand
        from almasix.queue.helpers import dispatch

        job = CallQueuedCommand(command, parameters, connection=connection, queue=queue)
        return await dispatch(job)

    @classmethod
    def all(cls, app: Application | None = None) -> dict[str, type[Command]]:
        return dict(cls.kernel(app).commands)

    @classmethod
    def has(cls, name: str, app: Application | None = None) -> bool:
        return name in cls.kernel(app).commands


def drain_pending(kernel: ConsoleKernel) -> None:
    """Register closure commands defined before the kernel existed."""
    while _pending:
        kernel.register(_pending.pop(0))


def _kernel_from_app(app: Application) -> ConsoleKernel | None:
    from almasix.console.kernel import ConsoleKernel

    try:
        if app.container.bound(ConsoleKernel):
            return app.make(ConsoleKernel)
    except Exception:  # pragma: no cover - container edge cases
        return None
    return None


def _split_command(command: str) -> tuple[str, list[str]]:
    parts = shlex.split(command)
    if not parts:
        raise ValueError("A command name is required")
    return parts[0], parts[1:]


def _parameters_to_argv(parameters: dict[str, Any]) -> list[str]:
    """Turn Laravel-style parameter dicts into argv, including arrays and flags."""
    argv: list[str] = []
    for key, value in parameters.items():
        if key.startswith("--"):
            argv.extend(_option_argv(key, value))
        elif isinstance(value, (list, tuple)):
            argv.extend(str(item) for item in value)
        else:
            argv.append(str(value))
    return argv


def _option_argv(key: str, value: Any) -> list[str]:
    if isinstance(value, bool):
        return [key] if value else []
    if isinstance(value, (list, tuple)):
        return [f"{key}={item}" for item in value]
    return [f"{key}={value}"]


def _closure_command(signature: str, callback: Callable[..., Any]) -> type[Command]:
    name, _arguments, _options = parse_signature(signature)

    def handle(self: Command) -> Any:
        return callback(**_resolve_parameters(self, callback))

    return type(
        f"ClosureCommand_{name.replace(':', '_').replace('-', '_')}",
        (Command,),
        {
            "signature": signature,
            "description": (callback.__doc__ or "").strip().splitlines()[0]
            if callback.__doc__
            else "",
            "handle": handle,
        },
    )


def _resolve_parameters(command: Command, callback: Callable[..., Any]) -> dict[str, Any]:
    """Fill closure parameters from input, then from the container."""
    parameters = _signature_parameters(callback)
    if parameters is None:  # pragma: no cover - builtins without signatures
        return {}
    values: dict[str, Any] = {}
    inputs = {**command.arguments(), **command.options()}
    for parameter in parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name == "command":
            values["command"] = command
        elif parameter.name in inputs:
            values[parameter.name] = inputs[parameter.name]
        else:
            resolved = _resolve_dependency(command, parameter)
            if resolved is not inspect.Parameter.empty:
                values[parameter.name] = resolved
    return values


def _signature_parameters(
    callback: Callable[..., Any],
) -> dict[str, inspect.Parameter] | None:
    """Signature parameters with annotations evaluated (``from __future__``)."""
    for eval_str in (True, False):
        try:
            return dict(inspect.signature(callback, eval_str=eval_str).parameters)
        except (TypeError, ValueError, NameError):
            continue
    return None


#: Scalars come from command input, never from the container.
_SCALARS = (str, int, float, bool, bytes, list, dict, set, tuple)


def _resolve_dependency(command: Command, parameter: inspect.Parameter) -> Any:
    annotation = parameter.annotation
    resolvable = (
        command.app is not None
        and annotation is not inspect.Parameter.empty
        and isinstance(annotation, type)
        and not issubclass(annotation, _SCALARS)
    )
    if resolvable:
        with contextlib.suppress(Exception):
            return command.app.make(annotation)
    if parameter.default is not inspect.Parameter.empty:
        return parameter.default
    return inspect.Parameter.empty
