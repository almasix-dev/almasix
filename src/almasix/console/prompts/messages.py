"""Informational messages, tables, and clear — Laravel Prompts display helpers."""

from __future__ import annotations

import os
from typing import Any, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text


def _console() -> Console:
    return Console(stderr=False, soft_wrap=True)


def note(message: str, *, title: str = "Note") -> None:
    _console().print(Panel(message, title=title, border_style="bright_black", padding=(0, 1)))


def info(message: str) -> None:
    _console().print(Panel(Text(message), title="Info", border_style="cyan", padding=(0, 1)))


def warning(message: str) -> None:
    _console().print(Panel(Text(message), title="Warning", border_style="yellow", padding=(0, 1)))


def error(message: str) -> None:
    _console().print(Panel(Text(message), title="Error", border_style="red", padding=(0, 1)))


def alert(message: str) -> None:
    _console().print(
        Panel(Text(message, style="bold white"), title="Alert", border_style="red", style="red", padding=(0, 1))
    )


def intro(message: str) -> None:
    _console().print(f"\n[bold cyan]{message}[/]\n")


def outro(message: str) -> None:
    _console().print(f"\n[bold green]{message}[/]\n")


def table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    grid = RichTable(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    for header in headers:
        grid.add_column(str(header))
    for row in rows:
        grid.add_row(*[str(cell) for cell in row])
    _console().print(grid)


def clear() -> None:
    if os.name == "nt":  # pragma: no cover
        os.system("cls")
    else:
        _console().clear()
