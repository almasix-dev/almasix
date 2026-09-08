"""Command base — signature, IoC handle(), input and output helpers."""

from __future__ import annotations

import re
import signal as signal_module
from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from almasix.console.exceptions import CommandFailed
from almasix.console.output import Output

if TYPE_CHECKING:
    from almasix.framework.application import Application

_TOKEN_RE = re.compile(r"\{([^}]*)\}")
_DESCRIPTION_RE = re.compile(r"\s+:\s+")
_LIST_SPLIT_RE = re.compile(r",\s?")
_NAME_RE = re.compile(r"[a-zA-Z_][\w-]*")


class Command:
    """Laravel-shaped console command.

    Declare ``signature`` like ``mail:send {user} {--Q|queue= : Which queue}``
    and implement ``handle()``. Arguments and options are injected as
    attributes before ``handle`` runs.
    """

    signature: ClassVar[str] = ""
    description: ClassVar[str] = ""
    hidden: ClassVar[bool] = False

    #: Extra names this command answers to (Laravel's ``$aliases``).
    aliases: ClassVar[tuple[str, ...]] = ()

    #: Whether the application must be booted before ``handle()`` runs.
    #: Generators and ``version`` work in a bare directory, so they say no.
    boots_application: ClassVar[bool] = True

    #: Laravel exit codes (`Command::SUCCESS` and friends).
    SUCCESS: ClassVar[int] = 0
    FAILURE: ClassVar[int] = 1
    INVALID: ClassVar[int] = 2

    #: Set by the ``Isolatable`` / ``PromptsForMissingInput`` mixins.
    isolatable: ClassVar[bool] = False
    prompts_for_missing_input: ClassVar[bool] = False

    def __init__(self, app: Application | None = None) -> None:
        self.app = app
        #: The kernel running this command (Laravel's ``getApplication()``),
        #: set by :meth:`ConsoleKernel.run_command`. It is how a command can
        #: ask what other commands exist.
        self.kernel: Any = None
        self.output = Output()
        self._arguments: dict[str, Any] = {}
        self._options: dict[str, Any] = {}

    @classmethod
    def name(cls) -> str:
        """Command name (first token of the signature)."""
        return (cls.signature or cls.__name__).split()[0]

    # --- input ----------------------------------------------------------

    def argument(self, key: str, default: Any = None) -> Any:
        return self._arguments.get(key, default)

    def arguments(self) -> dict[str, Any]:
        return dict(self._arguments)

    def option(self, key: str, default: Any = None) -> Any:
        return self._options.get(key, default)

    def options(self) -> dict[str, Any]:
        return dict(self._options)

    def has_option(self, key: str) -> bool:
        return key in self._options

    # --- output ---------------------------------------------------------

    def line(self, message: str = "") -> None:
        self.output.line(message)

    def info(self, message: str) -> None:
        self.output.info(message)

    def comment(self, message: str) -> None:
        self.output.comment(message)

    def question(self, message: str) -> None:
        self.output.question(message)

    def warn(self, message: str) -> None:
        self.output.warn(message)

    def error(self, message: str) -> None:
        self.output.error(message)

    def success(self, message: str) -> None:
        self.output.success(message)

    def alert(self, message: str) -> None:
        """Laravel ``$this->alert()`` — a boxed, attention-grabbing message."""
        self.output.alert(message)

    def new_line(self, count: int = 1) -> None:
        self.output.new_line(count)

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        self.output.table(headers, rows)

    def with_progress_bar(
        self,
        items: Iterable[Any],
        callback: Callable[[Any], Any] | None = None,
        label: str = "Processing",
    ) -> list[Any]:
        """Laravel ``withProgressBar()`` — map over items, advancing a bar."""
        from almasix.console.prompts import progress

        collected = list(items)
        return progress(label, items=collected, callback=callback or (lambda item: item))

    # --- interactive ----------------------------------------------------

    def confirm(self, question: str, default: bool = False) -> bool:
        return self.output.confirm(question, default=default)

    def ask(self, question: str, default: str | None = None, *, required: bool = False) -> str:
        """Laravel ``$this->ask()`` — styled text prompt."""
        from almasix.console.prompts import text

        return text(question, default="" if default is None else default, required=required)

    def secret(self, question: str, *, required: bool = False) -> str:
        """Laravel ``$this->secret()`` — hidden input."""
        from almasix.console.prompts import password

        return password(question, required=required)

    def choice(
        self,
        question: str,
        choices: list[Any] | dict[Any, str],
        default: Any = None,
        *,
        multiple: bool = False,
    ) -> Any:
        """Laravel ``$this->choice()`` — arrow-key select (or multiselect)."""
        from almasix.console.prompts import multiselect, select

        if multiple:
            preselected = default if isinstance(default, list) else ([] if default is None else [default])
            return multiselect(question, choices, default=preselected)
        return select(question, choices, default=default)

    def anticipate(
        self,
        question: str,
        options: list[str],
        default: str | None = None,
    ) -> str:
        """Laravel ``$this->anticipate()`` — text with suggestions."""
        from almasix.console.prompts import suggest

        return suggest(question, options, default="" if default is None else default)

    # --- calling other commands ----------------------------------------

    def call(self, command: str, arguments: dict[str, Any] | None = None) -> int:
        """Laravel ``$this->call()`` — run another command, showing its output."""
        from almasix.console.facade import Artisan

        return Artisan.call(command, arguments, app=self.app, kernel=self.kernel)

    def call_silently(self, command: str, arguments: dict[str, Any] | None = None) -> int:
        """Laravel ``$this->callSilently()`` — run another command, muting output."""
        from almasix.console.facade import Artisan

        return Artisan.call(command, arguments, app=self.app, silent=True, kernel=self.kernel)

    # --- lifecycle ------------------------------------------------------

    def fail(self, message: str = "") -> None:
        """Laravel ``$this->fail()`` — abort the command with ``FAILURE``."""
        raise CommandFailed(message)

    def trap(self, signals: int | Iterable[int], callback: Callable[[int], Any]) -> None:
        """Laravel ``$this->trap()`` — handle one or more OS signals.

        Ignored when the interpreter cannot install handlers (non-main thread).
        """
        wanted = [signals] if isinstance(signals, int) else list(signals)
        for number in wanted:
            try:
                signal_module.signal(number, lambda sig, _frame: callback(sig))
            except (ValueError, OSError, RuntimeError):  # pragma: no cover - platform dependent
                return

    def isolatable_id(self) -> str:
        """Laravel ``isolatableId()`` — the isolation lock key for this run."""
        return self.name()

    def isolation_lock_seconds(self) -> int:
        """Laravel ``isolationLockExpiresAt()``, expressed in seconds."""
        return 3600

    def prompt_for_missing_arguments_using(self) -> dict[str, Any]:
        """Map argument name -> question (or callable) for missing input."""
        return {}

    def prompt_for_missing_argument(self, name: str) -> Any:
        """Ask for one missing argument; override for full control."""
        questions = self.prompt_for_missing_arguments_using()
        question = questions.get(name)
        if callable(question):
            return question()
        return self.ask(question or f"What is the {name.replace('_', ' ')}?", required=True)

    def handle(self) -> int | None:
        """Execute the command. Return a process exit code (default 0)."""
        raise NotImplementedError(f"{type(self).__name__}.handle() is not implemented")

    def run(
        self,
        arguments: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> int:
        self._arguments = dict(arguments or {})
        self._options = dict(options or {})
        for key, value in {**self._arguments, **self._options}.items():
            attribute = key.replace("-", "_")
            # ``serve --app`` must not replace the command's application, and
            # ``make:policy {name}`` must not shadow ``name()``. Input that
            # collides with the command's own surface stays in option()/argument().
            if attribute in _COMMAND_SURFACE:
                continue
            setattr(self, attribute, value)
        try:
            result = self.handle()
        except CommandFailed as exc:
            if str(exc):
                self.error(str(exc))
            return self.FAILURE
        if result is None:
            return self.SUCCESS
        return int(result)


#: Names that belong to the command itself, so input never overwrites them.
_COMMAND_SURFACE = frozenset(vars(Command)) | {"app", "kernel", "output"}


class Isolatable:
    """Mixin marking a command as isolatable (adds ``--isolated``)."""

    isolatable: ClassVar[bool] = True


class PromptsForMissingInput:
    """Mixin: prompt for required arguments instead of failing."""

    prompts_for_missing_input: ClassVar[bool] = True


def parse_signature(signature: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a Laravel-style signature into name, arguments, and options."""
    text_signature = signature.strip()
    if not text_signature:
        raise ValueError("Command signature must include a name")
    name = text_signature.split()[0]
    if name.startswith("{"):
        raise ValueError("Command signature must include a name")

    arguments: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    rest = text_signature[len(name) :]
    position = 0
    for match in _TOKEN_RE.finditer(rest):
        _reject_stray(rest[position : match.start()])
        position = match.end()
        token, description = _split_description(match.group(1).strip())
        if not token:
            raise ValueError("Empty signature token")
        if token.startswith("--"):
            options.append(_parse_option(token[2:], description))
        else:
            arguments.append(_parse_argument(token, description))
    _reject_stray(rest[position:])
    return name, arguments, options


def _reject_stray(text: str) -> None:
    if text.strip():
        raise ValueError(f"Invalid signature token: {text.strip()!r}")


def _split_description(token: str) -> tuple[str, str]:
    parts = _DESCRIPTION_RE.split(token, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return token, ""


def _parse_argument(token: str, description: str) -> dict[str, Any]:
    """Mirror Laravel's argument forms: ``{a}``, ``{a?}``, ``{a*}``, ``{a=v}``."""
    if token.endswith("?*"):
        return _argument(token[:-2], description, optional=True, array=True)
    if token.endswith("..."):  # Almasix's original variadic spelling
        return _argument(token[:-3], description, optional=True, array=True)
    if token.endswith("*"):
        return _argument(token[:-1], description, array=True)
    if token.endswith("?"):
        return _argument(token[:-1], description, optional=True)
    head, sep, tail = token.partition("=")
    if sep and tail.startswith("*"):
        default = _LIST_SPLIT_RE.split(tail[1:]) if tail[1:] else []
        return _argument(head, description, optional=True, array=True, default=default)
    if sep:
        return _argument(head, description, optional=True, default=tail)
    return _argument(token, description)


def _validate_name(name: str) -> str:
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"Invalid signature token: {name!r}")
    return name


def _argument(
    name: str,
    description: str,
    *,
    optional: bool = False,
    array: bool = False,
    default: Any = None,
) -> dict[str, Any]:
    _validate_name(name)
    return {
        "name": name,
        "description": description,
        "optional": optional or array,
        "array": array,
        "variadic": array,
        "default": default,
    }


def _parse_option(token: str, description: str) -> dict[str, Any]:
    """Mirror Laravel's option forms, including ``{--Q|queue=*}`` shortcuts."""
    shortcut = ""
    if "|" in token:
        shortcut, _, token = token.partition("|")
        shortcut = shortcut.strip()
    if token.endswith("=*"):
        return _option(token[:-2], shortcut, description, array=True, default=[])
    if token.endswith("="):
        return _option(token[:-1], shortcut, description)
    head, sep, tail = token.partition("=")
    if sep and tail.startswith("*"):
        default = _LIST_SPLIT_RE.split(tail[1:]) if tail[1:] else []
        return _option(head, shortcut, description, array=True, default=default)
    if sep:
        return _option(head, shortcut, description, default=tail)
    return _option(token, shortcut, description, is_flag=True)


def _option(
    name: str,
    shortcut: str,
    description: str,
    *,
    is_flag: bool = False,
    array: bool = False,
    default: Any = None,
) -> dict[str, Any]:
    _validate_name(name)
    return {
        "name": name,
        "shortcut": shortcut,
        "description": description,
        "default": default,
        "is_flag": is_flag,
        "array": array,
    }
