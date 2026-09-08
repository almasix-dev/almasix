"""Concurrent process pools (Laravel ``Process::pool`` / ``concurrently``)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from almasix.process.invoked import InvokedProcess
from almasix.process.pending import PendingProcess
from almasix.process.result import ProcessResult
from almasix.process.runner import DEFAULT_STOP_TIMEOUT
from almasix.support import Collection

#: A pool start callback receives the stream, the chunk, and the process key.
PoolOutputCallback = Callable[[str, str, "str | int"], Any]


class _Slot:
    """One pooled process, kept mutable so fluent calls can replace it."""

    def __init__(self, key: str | int, pending: PendingProcess) -> None:
        self.key = key
        self.pending = pending


class PoolProcess:
    """Proxy giving a pooled process the full ``PendingProcess`` fluency."""

    def __init__(self, slot: _Slot) -> None:
        self._slot = slot

    def as_(self, key: str) -> PoolProcess:
        """Name this process so its result can be looked up by key."""
        self._slot.key = key
        return self

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        attribute = getattr(self._slot.pending, name)
        if not callable(attribute):
            return attribute

        def fluent(*args: Any, **kwargs: Any) -> Any:
            result = attribute(*args, **kwargs)
            if isinstance(result, PendingProcess):
                self._slot.pending = result
                return self
            return result

        return fluent


class Pool:
    """Collects processes then starts them together."""

    def __init__(self, factory: Any) -> None:
        self._factory = factory
        self._slots: list[_Slot] = []

    def process(self) -> PoolProcess:
        """A fresh pooled process to configure."""
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

    def pending(self) -> list[PendingProcess]:
        return [slot.pending for slot in self._slots]

    def start(self, callback: PoolOutputCallback | None = None) -> InvokedProcessPool:
        started: list[tuple[str | int, InvokedProcess]] = []
        for slot in self._slots:
            started.append((slot.key, slot.pending.start(None, _keyed(callback, slot.key))))
        return InvokedProcessPool(started)

    def run(self, callback: PoolOutputCallback | None = None) -> ProcessPoolResults:
        return self.start(callback).wait()


class InvokedProcessPool:
    """The started processes of a pool (Laravel ``InvokedProcessPool``)."""

    def __init__(self, processes: list[tuple[str | int, InvokedProcess]]) -> None:
        self._processes = processes

    def running(self) -> Collection:
        """The processes still running, as a Collection."""
        return Collection([process for _key, process in self._processes if process.running()])

    def total(self) -> int:
        return len(self._processes)

    def __len__(self) -> int:
        return len(self._processes)

    def __iter__(self) -> Iterator[InvokedProcess]:
        return iter(process for _key, process in self._processes)

    def __getitem__(self, key: str | int) -> InvokedProcess:
        return _lookup(self._processes, key)

    def signal(self, sig: int) -> InvokedProcessPool:
        for _key, process in self._processes:
            process.signal(sig)
        return self

    def stop(
        self, timeout: float = DEFAULT_STOP_TIMEOUT, sig: int | None = None
    ) -> InvokedProcessPool:
        for _key, process in self._processes:
            process.stop(timeout, sig)
        return self

    def wait(self) -> ProcessPoolResults:
        return ProcessPoolResults([(key, process.wait()) for key, process in self._processes])


class ProcessPoolResults:
    """Results of a finished pool, keyed by index or name."""

    def __init__(self, results: list[tuple[str | int, ProcessResult]]) -> None:
        self._results = results

    def __getitem__(self, key: str | int) -> ProcessResult:
        return _lookup(self._results, key)

    def __iter__(self) -> Iterator[ProcessResult]:
        return iter(result for _key, result in self._results)

    def __len__(self) -> int:
        return len(self._results)

    def keys(self) -> list[str | int]:
        return [key for key, _result in self._results]

    def collect(self) -> Collection:
        return Collection([result for _key, result in self._results])

    def successful(self) -> bool:
        return all(result.successful() for _key, result in self._results)

    def failed(self) -> bool:
        return not self.successful()

    def output(self) -> list[str]:
        return [result.output() for _key, result in self._results]


def _keyed(callback: PoolOutputCallback | None, key: str | int) -> Any:
    if callback is None:
        return None
    return lambda kind, chunk: callback(kind, chunk, key)


def _lookup(pairs: list[tuple[str | int, Any]], key: str | int) -> Any:
    for candidate, value in pairs:
        if candidate == key:
            return value
    if isinstance(key, int) and 0 <= key < len(pairs):
        # Named processes still answer to their position, as PHP arrays do.
        return pairs[key][1]
    raise KeyError(key)
