"""Processes — ``Process.run`` / ``start`` / pools / pipes / fakes (Laravel-shaped)."""

from __future__ import annotations

from almasix.process.exceptions import (
    ProcessException,
    ProcessFailedException,
    ProcessNotStartedException,
    ProcessTimedOutException,
    StrayProcessException,
)
from almasix.process.facade import Process, get_factory, set_factory
from almasix.process.factory import Factory, RecordedProcess
from almasix.process.fake import (
    FakeProcessDescription,
    FakeProcessHandle,
    FakeProcessResult,
    FakeProcessSequence,
    OutOfFakeProcesses,
)
from almasix.process.invoked import InvokedProcess
from almasix.process.pending import PendingProcess
from almasix.process.pipe import Pipe
from almasix.process.pool import InvokedProcessPool, Pool, PoolProcess, ProcessPoolResults
from almasix.process.provider import ProcessServiceProvider
from almasix.process.result import ProcessResult
from almasix.process.runner import ERR, OUT, ProcessHandle

__all__ = [
    "ERR",
    "OUT",
    "Factory",
    "FakeProcessDescription",
    "FakeProcessHandle",
    "FakeProcessResult",
    "FakeProcessSequence",
    "InvokedProcess",
    "InvokedProcessPool",
    "OutOfFakeProcesses",
    "PendingProcess",
    "Pipe",
    "Pool",
    "PoolProcess",
    "Process",
    "ProcessException",
    "ProcessFailedException",
    "ProcessHandle",
    "ProcessNotStartedException",
    "ProcessPoolResults",
    "ProcessResult",
    "ProcessServiceProvider",
    "ProcessTimedOutException",
    "RecordedProcess",
    "StrayProcessException",
    "get_factory",
    "set_factory",
]
