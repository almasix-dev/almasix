"""Fiddle — interactive Avalon REPL (Laravel Tinker class).

Avalon's ORM is async. Fiddle resolves coroutine results automatically so
expressions like ``User.all()`` work without wrapping them in ``await``, and
enables IPython ``autoawait`` so ``await User.query().get()`` also works.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
import sys
from typing import TYPE_CHECKING, Any

import typer

if TYPE_CHECKING:
    from avalon.framework.application import Application


BANNER = """Avalon Fiddle — app booted, ready to explore.
ORM is async — these both work:
  User.all()
  await User.query().get()
Helpers: app, config, DB, User, run(coro), dump(...), dd(...), to_json(...)
Exit: Ctrl-D or exit()
"""


def resolve_awaitable(value: Any) -> Any:
    """Run a coroutine/awaitable to completion (new event loop).

    Used so Fiddle expressions like ``User.all()`` return models, not
    ``<coroutine ...>`` objects. Safe here because ``grail fiddle`` boots
    outside a running loop (same pattern as ``grail db:seed``).
    """
    if value is None or not inspect.isawaitable(value):
        return value
    if inspect.iscoroutine(value):
        return asyncio.run(value)
    # Generic awaitable (Task, Future, …)
    async def _drain() -> Any:
        return await value

    return asyncio.run(_drain())


def run(awaitable: Any) -> Any:
    """Explicit sync bridge: ``users = run(User.all())``."""
    return resolve_awaitable(awaitable)


def build_namespace(app: Application) -> dict[str, Any]:
    """Namespace shared with the interactive shell."""
    from avalon import __version__
    from avalon.config import config
    from avalon.debug import DumpAndDie, dd as _dd, dump, serialize, to_json

    def dd(*values: Any, as_json: bool = True) -> None:
        """Dump and exit Fiddle (Laravel ``dd()``)."""
        try:
            _dd(*values, as_json=as_json)
        except DumpAndDie as exc:
            raise SystemExit(0) from exc

    ns: dict[str, Any] = {
        "app": app,
        "config": config,
        "__version__": __version__,
        "run": run,
        "resolve_awaitable": resolve_awaitable,
        "dump": dump,
        "dd": dd,
        "to_json": to_json,
        "serialize": serialize,
    }
    try:
        from avalon.routing import Route, url

        ns["Route"] = Route
        ns["url"] = url
    except Exception:
        pass
    try:
        from avalon.orm import DB, Model

        ns["DB"] = DB
        ns["Model"] = Model
    except Exception:
        pass
    try:
        from avalon.log import log

        ns["log"] = log
    except Exception:
        pass
    refused = set(config("fiddle.dont_alias", []) or [])
    try:
        from app.models.user import User  # type: ignore

        if "User" not in refused:
            ns["User"] = User
    except Exception:
        pass
    for name, discovered in discover_app_classes().items():
        if name not in ns and name not in refused:
            ns[name] = discovered
    _add_aliases(ns, refused)
    _add_commands(ns)
    return ns


def discover_app_classes() -> dict[str, Any]:
    """Classes the application declares under ``app.models``, by class name.

    Fiddle has them waiting in the shell and ``model:show`` resolves a bare
    model name through them, so both agree on what the application's models
    are. A module that will not import costs its own classes and no others.
    """
    found: dict[str, Any] = {}
    try:
        package = importlib.import_module("app.models")
    except Exception:
        return found
    for info in pkgutil.iter_modules(getattr(package, "__path__", [])):
        if info.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"app.models.{info.name}")
        except Exception:
            continue
        for attribute in dir(module):
            value = getattr(module, attribute)
            if (
                isinstance(value, type)
                and attribute[:1].isupper()
                and getattr(value, "__module__", "").startswith("app.models")
            ):
                found.setdefault(attribute, value)
    return found


def _add_aliases(ns: dict[str, Any], refused: set[str]) -> None:
    """``config/fiddle.py`` → ``alias``: classes to have waiting in the shell.

    Laravel's Tinker aliases whatever it finds; Avalon asks, because a dotted
    path is unambiguous and an import that fails should say which one did.
    """
    from avalon.config import config

    for name, dotted in (config("fiddle.alias", {}) or {}).items():
        if name in refused:
            continue
        module_name, _, attribute = str(dotted).rpartition(".")
        try:
            ns[name] = getattr(importlib.import_module(module_name), attribute)
        except Exception as exc:
            typer.secho(f"fiddle.alias {name} ({dotted}): {exc}", fg=typer.colors.YELLOW)


def _add_commands(ns: dict[str, Any]) -> None:
    """``config/fiddle.py`` → ``commands``: commands callable from the shell.

    Tinker lists commands so you can type them at its prompt. A Python REPL
    reads Python, so each name becomes a callable instead:
    ``inspire()``, or ``queue_work(once=True)``.
    """
    from avalon.console.facade import Artisan

    available = Artisan.all()
    for name in _config_list("fiddle.commands"):
        if name not in available:
            typer.secho(f"fiddle.commands {name}: no such command", fg=typer.colors.YELLOW)
            continue
        ns[name.replace(":", "_").replace("-", "_")] = _command_caller(name)


def _command_caller(name: str) -> Any:
    """A callable that runs one command with keyword arguments as options."""
    from avalon.console.facade import Artisan

    def call(*arguments: Any, **options: Any) -> int:
        parameters = {f"--{key.replace('_', '-')}": value for key, value in options.items()}
        line = " ".join([name, *(str(argument) for argument in arguments)])
        return Artisan.call(line, parameters)

    call.__name__ = name.replace(":", "_")
    call.__doc__ = f"Run the {name!r} command."
    return call


def _config_list(key: str) -> list[str]:
    from avalon.config import config

    return [str(item) for item in (config(key, []) or [])]


def start_fiddle(app: Application) -> int:
    """Start Fiddle: IPython (preferred) → ptpython → Rich-enhanced stdlib."""
    namespace = build_namespace(app)

    if _start_ipython(namespace) == 0:
        return 0
    if _start_ptpython(namespace) == 0:
        return 0
    return _start_rich_console(namespace)


def _fiddle_prompts_class():
    """Build IPython Prompts subclass (lazy so IPython stays optional)."""
    from IPython.terminal.prompts import Prompts, Token

    class FiddlePrompts(Prompts):
        def in_prompt_tokens(self, cli=None):
            return [
                (Token.Prompt, "fiddle"),
                (Token.PromptNum, f"[{self.shell.execution_count}]"),
                (Token.Prompt, "> "),
            ]

        def out_prompt_tokens(self, cli=None):
            return [
                (Token.OutPrompt, "out"),
                (Token.OutPromptNum, f"[{self.shell.execution_count}]"),
                (Token.OutPrompt, "> "),
            ]

    return FiddlePrompts


def _start_ipython(namespace: dict[str, Any]) -> int | None:
    try:
        from IPython.core.displayhook import DisplayHook
        from IPython.terminal.embed import InteractiveShellEmbed
        from traitlets.config import Config
    except ImportError:
        return None

    class FiddleDisplayHook(DisplayHook):
        """Resolve awaitables and pretty-print models/collections as JSON."""

        def __call__(self, result=None):
            from avalon.console.display import render

            self.check_for_underscore()
            if result is None or self.quiet():
                return
            if inspect.isawaitable(result):
                result = resolve_awaitable(result)
            self.start_displayhook()
            self.write_output_prompt()
            self.update_user_ns(result)
            self.fill_exec_result(result)
            render(result)
            self.finish_displayhook()

    cfg = Config()
    cfg.InteractiveShellEmbed.colors = "Linux"
    cfg.InteractiveShellEmbed.confirm_exit = False
    cfg.InteractiveShell.ast_node_interactivity = "last_expr_or_assign"
    cfg.InteractiveShell.autoawait = True
    cfg.TerminalInteractiveShell.true_color = True
    cfg.TerminalInteractiveShell.prompts_class = _fiddle_prompts_class()
    cfg.TerminalInteractiveShell.editing_mode = "emacs"
    cfg.TerminalInteractiveShell.displayhook_class = FiddleDisplayHook

    shell = InteractiveShellEmbed.instance(
        config=cfg,
        banner1=BANNER,
        exit_msg="Leaving Fiddle.",
        user_ns=namespace,
    )
    # Real asyncio runner so ``await User.all()`` works inside the embed.
    try:
        shell(using="asyncio")
    except TypeError:
        shell()
    return 0


def _configure_ptpython(repl) -> None:  # noqa: ANN001
    repl.show_signature = True
    repl.show_docstring = True
    repl.highlight_matching_parenthesis = True
    repl.use_code_colorscheme("monokai")
    repl.color_depth = "DEPTH_24_BIT"
    repl.enable_syntax_highlighting = True
    repl.prompt_style = "ipython"
    repl.show_line_numbers = False
    # Prefer eval that resolves awaitables when ptpython supports it.
    original_eval = getattr(repl, "eval", None) or getattr(repl, "_eval", None)
    if original_eval is not None:
        def _eval(expression: str):
            result = original_eval(expression)
            return resolve_awaitable(result)

        if hasattr(repl, "eval"):
            repl.eval = _eval  # type: ignore[method-assign]


def _start_ptpython(namespace: dict[str, Any]) -> int | None:
    try:
        from ptpython.repl import embed
    except ImportError:
        return None

    print(BANNER, end="")
    embed(
        globals=namespace,
        locals=namespace,
        configure=_configure_ptpython,
        title="Avalon Fiddle",
    )
    return 0


def _start_rich_console(namespace: dict[str, Any]) -> int:
    """Polished fallback when IPython/ptpython are not installed."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.theme import Theme
    except ImportError:
        return _start_plain_console(namespace)

    theme = Theme(
        {
            "fiddle.banner": "bold cyan",
            "fiddle.hint": "dim",
            "fiddle.prompt": "bold magenta",
            "fiddle.warn": "yellow",
        }
    )
    console = Console(theme=theme, soft_wrap=True)
    console.print(
        Panel.fit(
            "[fiddle.banner]Avalon Fiddle[/]\n"
            "[fiddle.hint]App booted · ORM is async — User.all() auto-awaits[/]\n"
            "[fiddle.hint]Exit with Ctrl-D or exit()[/]",
            border_style="cyan",
            padding=(0, 1),
        )
    )
    console.print(
        "[fiddle.warn]Tip:[/] install IPython for Tinker-class coloring & completion:\n"
        "  [bold]pip install 'avalon[fiddle]'[/]  (or: pip install ipython)\n"
    )

    def displayhook(value: Any) -> None:
        if value is None:
            return
        from avalon.console.display import render

        value = resolve_awaitable(value)
        builtins = __import__("builtins")
        builtins._ = value  # noqa: SLF001 — REPL `_` convenience
        render(value, console=console)

    sys.displayhook = displayhook

    import code
    import readline  # noqa: F401 — arrow keys / history when available

    class FiddleConsole(code.InteractiveConsole):
        def raw_input(self, prompt: str = "") -> str:
            console.print("[fiddle.prompt]fiddle>[/] ", end="")
            return input()

        def runcode(self, code_obj) -> None:  # noqa: A002
            from avalon.debug import DumpAndDie

            try:
                exec(code_obj, self.locals)  # noqa: S102
            except DumpAndDie as exc:
                raise SystemExit(0) from exc
            except SystemExit:
                raise
            except Exception:
                self.showtraceback()

    FiddleConsole(locals=namespace).interact(banner="", exitmsg="")
    return 0


def _start_plain_console(namespace: dict[str, Any]) -> int:
    import code
    import readline  # noqa: F401

    print(BANNER, end="")
    print("Tip: pip install 'avalon[fiddle]' for syntax highlighting.\n")

    def displayhook(value: Any) -> None:
        if value is None:
            return
        from avalon.console.display import render

        value = resolve_awaitable(value)
        builtins = __import__("builtins")
        builtins._ = value
        render(value)

    sys.displayhook = displayhook
    code.InteractiveConsole(locals=namespace).interact(banner="", exitmsg="")
    return 0
