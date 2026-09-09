"""Console output helpers — tables, colors, confirm."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import typer

from almasix.console.prompts.style import CHECK, CROSS


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
        # Fixed-width columns (not Rich wrap) so ``route:list`` / ``model:show``
        # stay one logical row per physical line and greppable in tests.
        widths = [len(str(header)) for header in headers]
        str_rows = [[str(cell) for cell in row] for row in rows]
        for row in str_rows:
            for index, cell in enumerate(row):
                if index < len(widths):
                    widths[index] = max(widths[index], len(cell))
        header_line = "  ".join(str(headers[i]).ljust(widths[i]) for i in range(len(headers)))
        rule = "  ".join("-" * widths[i] for i in range(len(headers)))
        typer.echo(header_line)
        typer.echo(rule)
        for row in str_rows:
            padded = list(row) + [""] * (len(headers) - len(row))
            typer.echo("  ".join(padded[i].ljust(widths[i]) for i in range(len(headers))))

    def confirm(self, question: str, default: bool = False) -> bool:
        from almasix.console.prompts import confirm as prompts_confirm

        return bool(prompts_confirm(question, default=default))
