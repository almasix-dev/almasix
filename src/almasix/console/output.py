"""Console output helpers — tables, colors, confirm."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import typer
from rich.console import Console
from rich.table import Table as RichTable

from almasix.console.prompts.style import CHECK, CROSS, OD_BLUE, OD_CYAN, OD_GREEN


class Output:
    """Laravel-shaped console output bound to a command run."""

    def line(self, message: str = "") -> None:
        typer.echo(message)

    def info(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.CYAN)

    def comment(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.BRIGHT_BLACK)

    def question(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.BLUE)

    def warn(self, message: str) -> None:
        typer.secho(message, fg=typer.colors.YELLOW)

    def error(self, message: str) -> None:
        typer.secho(f"{CROSS} {message}" if message else message, fg=typer.colors.RED, err=True)

    def success(self, message: str) -> None:
        typer.secho(f"{CHECK} {message}" if message else message, fg=typer.colors.GREEN)

    def alert(self, message: str) -> None:
        """Laravel ``$this->alert()`` — the message inside an asterisk box."""
        rule = "*" * (len(message) + 12)
        typer.secho(rule, fg=typer.colors.YELLOW)
        typer.secho(f"*     {message}     *", fg=typer.colors.YELLOW)
        typer.secho(rule, fg=typer.colors.YELLOW)

    def new_line(self, count: int = 1) -> None:
        for _ in range(count):
            typer.echo("")

    def table(self, headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
        grid = RichTable(
            show_header=True,
            header_style=f"bold {OD_CYAN}",
            box=None,
            pad_edge=False,
            border_style=OD_BLUE,
        )
        for header in headers:
            grid.add_column(str(header), style=OD_GREEN)
        for row in rows:
            grid.add_row(*[str(cell) for cell in row])
        Console(soft_wrap=True).print(grid)

    def confirm(self, question: str, default: bool = False) -> bool:
        from almasix.console.prompts import confirm as prompts_confirm

        return bool(prompts_confirm(question, default=default))
