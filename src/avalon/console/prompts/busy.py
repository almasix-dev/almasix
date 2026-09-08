"""Spin and progress — busy indicators (Laravel Prompts)."""

from __future__ import annotations

import itertools
import sys
import threading
from collections.abc import Callable, Iterable, Sequence
from typing import TypeVar

from rich.console import Console
from rich.progress import BarColumn, Progress as RichProgress, SpinnerColumn, TextColumn, TimeElapsedColumn

from avalon.console.prompts.types import is_interactive

T = TypeVar("T")
R = TypeVar("R")


def spin(callback: Callable[[], R], message: str = "Working…") -> R:
    """Show a spinner while ``callback`` runs (Laravel ``spin``)."""
    if not is_interactive():
        return callback()

    console = Console()
    done = threading.Event()
    error: list[BaseException] = []
    result: list[R] = []

    def worker() -> None:
        try:
            result.append(callback())
        except BaseException as exc:  # noqa: BLE001 — re-raise after spinner stops
            error.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    frames = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
    try:
        while not done.wait(0.08):
            console.print(f"\r[cyan]{next(frames)}[/] {message}", end="")
            sys.stdout.flush()
        console.print(f"\r[green]✔[/] {message}   ")
    finally:
        thread.join(timeout=0.1)
    if error:
        raise error[0]
    return result[0]


class Progress:
    """Manual progress bar (Laravel ``Progress``)."""

    def __init__(self, label: str, steps: int) -> None:
        self._label = label
        self.steps = max(1, steps)
        self._advance = 0
        self._hint = ""
        self._interactive = is_interactive()
        self._progress: RichProgress | None = None
        self._task_id = None
        if self._interactive:
            self._progress = RichProgress(
                SpinnerColumn(),
                TextColumn("[cyan]{task.description}[/]"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeElapsedColumn(),
                console=Console(),
            )
            self._progress.start()
            self._task_id = self._progress.add_task(label, total=self.steps)

    def hint(self, message: str) -> Progress:
        self._hint = message
        if self._progress is not None and self._task_id is not None:
            desc = f"{self._label} — {message}" if message else self._label
            self._progress.update(self._task_id, description=desc)
        return self

    def label(self, message: str) -> Progress:  # noqa: A003
        self._label = message
        return self.hint(self._hint)

    def advance(self, step: int = 1) -> None:
        self._advance += step
        if self._progress is not None and self._task_id is not None:
            self._progress.update(self._task_id, advance=step)

    def finish(self) -> None:
        if self._progress is not None:
            if self._task_id is not None and self._advance < self.steps:
                self._progress.update(self._task_id, completed=self.steps)
            self._progress.stop()
            self._progress = None


def progress(
    label: str,
    steps: int | Iterable[T] | None = None,
    callback: Callable[[T], R] | None = None,
    *,
    items: Iterable[T] | None = None,
) -> Progress | list[R]:
    """Progress bar helper (Laravel ``progress``).

    - ``progress('Work', steps=10)`` → manual :class:`Progress`
    - ``progress('Work', users, callback)`` → map with bar, returns results
    """
    sequence: Sequence[T] | None = None
    if items is not None:
        sequence = list(items)
    elif steps is not None and not isinstance(steps, int):
        sequence = list(steps)

    if sequence is not None:
        bar = Progress(label, len(sequence) or 1)
        results: list[R] = []
        try:
            for item in sequence:
                if callback is not None:
                    results.append(callback(item))
                bar.advance()
        finally:
            bar.finish()
        return results

    total = int(steps or 0)
    return Progress(label, total)
