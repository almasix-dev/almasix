"""Informational messages, tables, and clear — Laravel Prompts display helpers."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text


def _console() -> Console:
    return Console(stderr=False, soft_wrap=True)


def note(message: str, *, title: str = "Note") -> None:
    _console().print(Panel(message, title=title, border_style="#5c6370", padding=(0, 1)))


def info(message: str) -> None:
    _console().print(Panel(Text(message), title="Info", border_style="#56b6c2", padding=(0, 1)))


def warning(message: str) -> None:
    _console().print(Panel(Text(message), title="Warning", border_style="#e5c07b", padding=(0, 1)))


def error(message: str) -> None:
    _console().print(Panel(Text(message), title="Error", border_style="#e06c75", padding=(0, 1)))


def alert(message: str) -> None:
    _console().print(
        Panel(
            Text(message, style="bold #abb2bf"),
            title="Alert",
            border_style="#e06c75",
            style="#e06c75",
            padding=(0, 1),
        )
    )


def intro(message: str) -> None:
    _console().print(f"\n[bold #61afef]{message}[/]\n")


def outro(message: str) -> None:
    _console().print(f"\n[bold #98c379]✔ {message}[/]\n")


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    grid = RichTable(
        show_header=True,
        header_style="bold #56b6c2",
        box=None,
        pad_edge=False,
    )
    for header in headers:
        grid.add_column(str(header), style="#98c379")
    for row in rows:
        grid.add_row(*[str(cell) for cell in row])
    _console().print(grid)


def clear() -> None:
    if os.name == "nt":  # pragma: no cover
        os.system("cls")
    else:
        _console().clear()
