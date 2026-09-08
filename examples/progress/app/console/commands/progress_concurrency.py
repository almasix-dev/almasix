"""Demo Concurrency.run / defer / drivers (M22)."""

from __future__ import annotations

import asyncio
import os
import time

from almasix.concurrency import Concurrency, UnsupportedDriverException
from almasix.console.command import Command


def slow(label: str, seconds: float = 0.2) -> str:
    time.sleep(seconds)
    return label


class ProgressConcurrencyCommand(Command):
    signature = "progress:concurrency"
    description = "Demo Concurrency run, keys, drivers, defer, and arun (M22)"

    def handle(self) -> int:
        started = time.monotonic()
        results = Concurrency.run([lambda: slow("first"), lambda: slow("second")])
        elapsed = time.monotonic() - started
        assert results == ["first", "second"]
        self.info(f"run -> {results} in {elapsed:.2f}s (0.40s if serial)")

        counted = Concurrency.run(
            {"users": lambda: 3, "posts": lambda: 7, "comments": lambda: 11}
        )
        assert counted == {"users": 3, "posts": 7, "comments": 11}
        self.info(f"keys -> {counted}")

        self.info(f"driver -> {Concurrency.get_default_driver()}")
        assert Concurrency.run([lambda: "serial"], "sync") == ["serial"]

        try:
            pids = Concurrency.run([os.getpid, os.getpid], "fork")
            assert os.getpid() not in pids
            self.info(f"fork -> {len(set(pids))} child processes, parent {os.getpid()}")
        except UnsupportedDriverException as exception:
            self.warn(f"fork -> unavailable here: {exception}")

        try:
            Concurrency.run([lambda: 1], "process")
        except UnsupportedDriverException:
            self.info("process -> refuses a lambda, as documented")

        recorded: list[str] = []
        deferred = Concurrency.defer([lambda: recorded.append("audited")])
        assert deferred.wait() == [None]
        self.info(f"defer -> {recorded}")

        async def fetch(label: str) -> str:
            await asyncio.sleep(0.1)
            return label

        awaited = asyncio.run(
            Concurrency.arun({"a": lambda: fetch("a"), "b": lambda: fetch("b")})
        )
        assert awaited == {"a": "a", "b": "b"}
        self.info(f"arun -> {awaited}")

        try:
            Concurrency.run([lambda: 1, self._explode])
        except RuntimeError as exception:
            self.info(f"failure -> {exception}")

        self.success("concurrency demo ok")
        return 0

    def _explode(self) -> None:
        raise RuntimeError("a failing task raises after the others settle")
