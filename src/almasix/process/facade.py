"""``Process`` façade — Laravel-shaped subprocess entry point."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from almasix.process.factory import Factory
from almasix.process.fake import (
    FakeProcessDescription,
    FakeProcessResult,
    FakeProcessSequence,
)
from almasix.process.invoked import InvokedProcess
from almasix.process.pending import PendingProcess
from almasix.process.pipe import Pipe
from almasix.process.pool import Pool, ProcessPoolResults
from almasix.process.result import ProcessResult
from almasix.process.runner import OutputCallback

_factory: Factory | None = None


def get_factory() -> Factory:
    global _factory
    if _factory is None:
        _factory = Factory()
    return _factory


def set_factory(factory: Factory | None) -> None:
    global _factory
    _factory = factory


class Process:
    """Static façade over the process factory."""

    @classmethod
    def factory(cls) -> Factory:
        return get_factory()

    @classmethod
    def pending(cls) -> PendingProcess:
        return cls.factory().pending()

    # --- running --------------------------------------------------------

    @classmethod
    def run(
        cls,
        command: str | Sequence[str],
        output_callback: OutputCallback | None = None,
    ) -> ProcessResult:
        return cls.pending().run(command, output_callback)

    @classmethod
    def start(
        cls,
        command: str | Sequence[str],
        output_callback: OutputCallback | None = None,
    ) -> InvokedProcess:
        return cls.pending().start(command, output_callback)

    @classmethod
    def pool(cls, callback: Callable[[Pool], Any]) -> Pool:
        return cls.factory().pool(callback)

    @classmethod
    def concurrently(
        cls, callback: Callable[[Pool], Any], output: Any = None
    ) -> ProcessPoolResults:
        return cls.factory().concurrently(callback, output)

    @classmethod
    def pipe(
        cls, commands: Callable[[Pipe], Any] | Sequence[Any], output: Any = None
    ) -> ProcessResult:
        return cls.factory().pipe(commands, output)

    # --- configuration --------------------------------------------------

    @classmethod
    def command(cls, command: str | Sequence[str]) -> PendingProcess:
        return cls.pending().command(command)

    @classmethod
    def path(cls, directory: str | os.PathLike[str]) -> PendingProcess:
        return cls.pending().path(directory)

    @classmethod
    def timeout(cls, seconds: float) -> PendingProcess:
        return cls.pending().timeout(seconds)

    @classmethod
    def idle_timeout(cls, seconds: float) -> PendingProcess:
        return cls.pending().idle_timeout(seconds)

    @classmethod
    def forever(cls) -> PendingProcess:
        return cls.pending().forever()

    @classmethod
    def env(cls, environment: Mapping[str, Any]) -> PendingProcess:
        return cls.pending().env(environment)

    @classmethod
    def input(cls, input: str | bytes) -> PendingProcess:
        return cls.pending().input(input)

    @classmethod
    def quietly(cls) -> PendingProcess:
        return cls.pending().quietly()

    @classmethod
    def tty(cls, tty: bool = True) -> PendingProcess:
        return cls.pending().tty(tty)

    @classmethod
    def options(cls, options: Mapping[str, Any]) -> PendingProcess:
        return cls.pending().options(options)

    @classmethod
    def when(
        cls, condition: Any, callback: Callable[..., Any], default: Callable[..., Any] | None = None
    ) -> PendingProcess:
        return cls.pending().when(condition, callback, default)

    @classmethod
    def unless(
        cls, condition: Any, callback: Callable[..., Any], default: Callable[..., Any] | None = None
    ) -> PendingProcess:
        return cls.pending().unless(condition, callback, default)

    # --- faking ---------------------------------------------------------

    @classmethod
    def fake(cls, callback: Any = None) -> Factory:
        return cls.factory().fake(callback)

    @classmethod
    def result(
        cls,
        output: str | Sequence[str] = "",
        error_output: str | Sequence[str] = "",
        exit_code: int = 0,
    ) -> FakeProcessResult:
        return cls.factory().result(output, error_output, exit_code)

    @classmethod
    def describe(cls) -> FakeProcessDescription:
        return cls.factory().describe()

    @classmethod
    def sequence(cls) -> FakeProcessSequence:
        """An unattached sequence, for use inside a ``fake`` command map."""
        return cls.factory().sequence()

    @classmethod
    def fake_sequence(cls, command: str | None = None) -> FakeProcessSequence:
        return cls.factory().fake_sequence(command)

    @classmethod
    def prevent_stray_processes(cls, prevent: bool = True) -> Factory:
        return cls.factory().prevent_stray_processes(prevent)

    @classmethod
    def allow_stray_processes(cls) -> Factory:
        return cls.factory().allow_stray_processes()

    # --- assertions -----------------------------------------------------

    @classmethod
    def recorded(
        cls, callback: str | Callable[..., bool] | None = None
    ) -> list[tuple[PendingProcess, ProcessResult]]:
        return cls.factory().recorded(callback)

    @classmethod
    def assert_ran(cls, callback: str | Callable[..., bool]) -> None:
        cls.factory().assert_ran(callback)

    @classmethod
    def assert_didnt_run(cls, callback: str | Callable[..., bool]) -> None:
        cls.factory().assert_didnt_run(callback)

    @classmethod
    def assert_ran_times(cls, callback: str | Callable[..., bool], times: int = 1) -> None:
        cls.factory().assert_ran_times(callback, times)

    @classmethod
    def assert_nothing_ran(cls) -> None:
        cls.factory().assert_nothing_ran()

    @classmethod
    def assert_sequences_are_empty(cls) -> None:
        cls.factory().assert_sequences_are_empty()
