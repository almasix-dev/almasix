"""Process pipelines (Laravel ``Process::pipe``)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from almasix.process.pool import PoolProcess, _Slot
from almasix.process.result import ProcessResult

#: A pipe callback receives the stream, the chunk, and the process key.
PipeOutputCallback = Callable[[str, str, "str | int"], Any]


class Pipe:
    """Chains processes, feeding each one's output into the next's input."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._slots: list[_Slot] = []

    def process(self) -> PoolProcess:
        slot = _Slot(len(self._slots), self._factory.pending())
        self._slots.append(slot)
        return PoolProcess(slot)

    def as_(self, key: str) -> PoolProcess:
        return self.process().as_(key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.process(), name)

    def __len__(self) -> int:
        return len(self._slots)

    def run(self, callback: PipeOutputCallback | None = None) -> ProcessResult:
        """Run every stage in order and return the last result.

        A failing stage short-circuits the pipeline and is returned as-is,
        the way Laravel's pipe does — there is nothing sensible to feed the
        next command.
        """
        result: ProcessResult | None = None
        for slot in self._slots:
            if result is not None and result.failed():
                return result
            pending = slot.pending
            if result is not None:
                pending = pending.input(result.output())
            key = slot.key
            stage_callback = None if callback is None else _keyed(callback, key)
            result = pending.run(None, stage_callback)
        if result is None:
            raise ValueError("A process pipe needs at least one command.")
        return result


def build_pipe(factory: Any, commands: Callable[[Pipe], Any] | Sequence[Any]) -> Pipe:
    """Accept either a configuring callable or a plain list of commands."""
    pipe = Pipe(factory)
    if callable(commands):
        commands(pipe)
    else:
        for command in commands:
            pipe.command(command)
    return pipe


def _keyed(callback: PipeOutputCallback, key: str | int) -> Any:
    return lambda kind, chunk: callback(kind, chunk, key)
