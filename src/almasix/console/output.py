"""Console output helpers — tables, colors, confirm.

Uses Rich + One Dark Pro truecolor so Smith matches Almasix Prompts. Tables stay
fixed-width (one logical row per line) for greppable ``route:list`` / ``model:show``.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Sequence
from typing import Any

from rich.console import Console
from rich.style import Style
from rich.text import Text

from almasix.console.prompts.style import (
    CHECK,
    CROSS,
    OD_BLUE,
    OD_COMMENT,
    OD_CYAN,
    OD_FG,
    OD_GREEN,
    OD_MAGENTA,
    OD_ORANGE,
    OD_RED,
    OD_YELLOW,
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# One Dark Pro styles for command output (Laravel Artisan / Prompts energy).
_STYLE_FG = Style(color=OD_FG)
_STYLE_DIM = Style(color=OD_COMMENT)
_STYLE_BOLD = Style(color=OD_FG, bold=True)
_STYLE_TITLE = Style(color=OD_CYAN, bold=True)
_STYLE_LABEL = Style(color=OD_YELLOW, bold=True)
_STYLE_CMD = Style(color=OD_GREEN, bold=True)
_STYLE_INFO = Style(color=OD_CYAN, bold=True)
_STYLE_WARN = Style(color=OD_YELLOW, bold=True)
_STYLE_ERROR = Style(color=OD_RED, bold=True)
_STYLE_SUCCESS = Style(color=OD_GREEN, bold=True)
_STYLE_ACCENT = Style(color=OD_ORANGE, bold=True)
_STYLE_HEADER = Style(color=OD_BLUE, bold=True)
_STYLE_NAME = Style(color=OD_MAGENTA)

_METHOD_STYLES: dict[str, Style] = {
    "GET": Style(color=OD_GREEN, bold=True),
    "HEAD": Style(color=OD_GREEN),
    "POST": Style(color=OD_YELLOW, bold=True),
    "PUT": Style(color=OD_BLUE, bold=True),
    "PATCH": Style(color=OD_CYAN, bold=True),
    "DELETE": Style(color=OD_RED, bold=True),
    "OPTIONS": Style(color=OD_COMMENT),
    "ANY": Style(color=OD_MAGENTA, bold=True),
}

_PRINT_KW = {"overflow": "ignore", "crop": False, "no_wrap": True}


def _console(*, stderr: bool = False) -> Console:
    # Fixed width + no_wrap so ``route:list`` / ``model:show`` stay one logical
    # row per physical line (greppable in tests; matches prior typer.echo).
    # Honor NO_COLOR / FORCE_COLOR the way modern CLIs do.
    no_color = bool(os.environ.get("NO_COLOR"))
    force = os.environ.get("FORCE_COLOR", "")
    force_terminal: bool | None
    if no_color:
        force_terminal = False
    elif force not in ("", "0"):
        force_terminal = True
    else:
        force_terminal = None
    return Console(
        file=sys.stderr if stderr else sys.stdout,
        highlight=False,
        soft_wrap=False,
        emoji=False,
        markup=False,  # help text uses ``[default: …]`` literally
        color_system="auto",
        force_terminal=force_terminal,
        no_color=True if no_color else None,
        width=500,
    )


def strip_ansi(text: str) -> str:
    """Remove ANSI SGR sequences — useful in tests that assert on layout."""
    return _ANSI_RE.sub("", text)


def style_http_methods(methods: str) -> Text:
    """Color ``GET|HEAD|POST`` the way Laravel's route:list does."""
    out = Text()
    parts = str(methods).split("|")
    for index, part in enumerate(parts):
        if index:
            out.append("|", style=_STYLE_DIM)
        out.append(part, style=_METHOD_STYLES.get(part.upper(), _STYLE_BOLD))
    return out


class Output:
    """Laravel-shaped console output bound to a command run."""

    def __init__(self) -> None:
        self._console = _console()
        self._err = _console(stderr=True)

    def _print(self, message: Any = "", *, style: Style | None = None, err: bool = False) -> None:
        console = self._err if err else self._console
        if message == "" or message is None:
            console.print(**_PRINT_KW)
            return
        if style is None:
            console.print(message, **_PRINT_KW)
        else:
            console.print(message, style=style, **_PRINT_KW)

    def line(self, message: str = "") -> None:
        if not message:
            self._print()
            return
        self._print(message, style=_STYLE_FG)

    def info(self, message: str) -> None:
        self._print(message, style=_STYLE_INFO)

    def comment(self, message: str) -> None:
        self._print(message, style=_STYLE_DIM)

    def question(self, message: str) -> None:
        self._print(message, style=_STYLE_LABEL)

    def warn(self, message: str) -> None:
        self._print(message, style=_STYLE_WARN)

    def error(self, message: str) -> None:
        text = f"{CROSS} {message}" if message else message
        self._print(text, style=_STYLE_ERROR, err=True)

    def success(self, message: str) -> None:
        text = f"{CHECK} {message}" if message else message
        self._print(text, style=_STYLE_SUCCESS)

    def alert(self, message: str) -> None:
        """Laravel ``$this->alert()`` — the message inside an asterisk box."""
        rule = "*" * (len(message) + 12)
        self._print(rule, style=_STYLE_WARN)
        self._print(f"*     {message}     *", style=_STYLE_WARN)
        self._print(rule, style=_STYLE_WARN)

    def title(self, message: str) -> None:
        """Bold accent heading (version banners, section titles)."""
        self._print(message, style=_STYLE_TITLE)

    def label(self, message: str) -> None:
        """Section heading without indent (``Usage:``, ``Available commands:``)."""
        self._print(message, style=_STYLE_LABEL)

    def two_column(self, left: str, right: str, *, width: int) -> None:
        """Command catalogue row: bold green name + dim description."""
        row = Text()
        row.append(f"  {left:<{width}}  ", style=_STYLE_CMD)
        row.append(right, style=_STYLE_DIM)
        self._print(row)

    def definition(self, left: str, right: str, *, width: int) -> None:
        """``about``-style row: bold yellow label + bright value."""
        row = Text()
        row.append(f"  {left:<{width}}  ", style=_STYLE_LABEL)
        row.append(right, style=_STYLE_BOLD)
        self._print(row)

    def namespace(self, name: str) -> None:
        """``cache`` / ``make`` group heading in ``smith list``."""
        self._print(f" {name}", style=_STYLE_LABEL)

    def quote(self, body: str, attribution: str = "") -> None:
        """Inspiring quote — bold accent body, dim author line."""
        self._print()
        self._print(f"  “{body}”", style=_STYLE_ACCENT)
        if attribution:
            self._print(f"    — {attribution}", style=_STYLE_DIM)
        self._print()

    def new_line(self, count: int = 1) -> None:
        for _ in range(count):
            self._print()

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        # Fixed-width columns (not soft-wrap) so ``route:list`` / ``model:show``
        # stay one logical row per physical line and greppable in tests.
        widths = [len(str(header)) for header in headers]
        str_rows = [[str(cell) for cell in row] for row in rows]
        for row in str_rows:
            for index, cell in enumerate(row):
                if index < len(widths):
                    widths[index] = max(widths[index], len(cell))

        header = Text()
        for index, name in enumerate(headers):
            if index:
                header.append("  ")
            header.append(str(name).ljust(widths[index]), style=_STYLE_HEADER)
        self._print(header)

        rule = Text("  ".join("-" * widths[i] for i in range(len(headers))), style=_STYLE_DIM)
        self._print(rule)

        method_idx = next(
            (i for i, name in enumerate(headers) if str(name).lower() == "method"),
            None,
        )
        name_idx = next(
            (i for i, name in enumerate(headers) if str(name).lower() == "name"),
            None,
        )
        action_idx = next(
            (i for i, name in enumerate(headers) if str(name).lower() == "action"),
            None,
        )

        for row in str_rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            line = Text()
            for index, cell in enumerate(padded[: len(headers)]):
                if index:
                    line.append("  ")
                cell_text = cell.ljust(widths[index])
                if index == method_idx:
                    # Pad after coloring so ANSI width does not break columns.
                    methods = style_http_methods(cell)
                    pad = " " * max(0, widths[index] - len(cell))
                    line.append(methods)
                    line.append(pad)
                elif index == name_idx and cell.strip():
                    line.append(cell_text, style=_STYLE_NAME)
                elif index == action_idx:
                    line.append(cell_text, style=_STYLE_DIM)
                else:
                    line.append(cell_text, style=_STYLE_FG)
            self._print(line)

    def write(self, message: Any = "", *, style: Style | None = None) -> None:
        """Print a Rich ``Text`` or string with the shared console settings."""
        self._print(message, style=style)

    def confirm(self, question: str, default: bool = False) -> bool:
        from almasix.console.prompts import confirm as prompts_confirm

        return bool(prompts_confirm(question, default=default))
