"""Subprocess execution — pipe pumping, timeouts, signals.

This is the only module that talks to :mod:`subprocess`; everything above it
(``PendingProcess``, ``InvokedProcess``, pools, pipes) works against the
:class:`ProcessHandle` contract so fakes can stand in for a real process.
"""

from __future__ import annotations

import os
import signal as signal_module
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import IO, Any

#: Output stream names Laravel passes to a run callback.
OUT = "out"
ERR = "err"

OutputCallback = Callable[[str, str], Any]

#: How long ``stop()`` waits for a terminated process before killing it.
DEFAULT_STOP_TIMEOUT = 10.0

#: Polling granularity for timeout enforcement, in seconds.
_TICK = 0.01


def describe_command(command: str | Sequence[str]) -> str:
    """Render a command as the single string Laravel records and matches on."""
    if isinstance(command, str):
        return command
    return " ".join(str(part) for part in command)


class ProcessHandle:
    """A started operating-system process and its accumulated output."""

    def __init__(
        self,
        command: str | Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
        input: str | bytes | None = None,
        tty: bool = False,
        quietly: bool = False,
        options: Mapping[str, Any] | None = None,
        output_callback: OutputCallback | None = None,
    ) -> None:
        self.command = describe_command(command)
        self._output_callback = None if quietly else output_callback
        self._lock = threading.Lock()
        self._output: list[str] = []
        self._error_output: list[str] = []
        self._seen_output = 0
        self._seen_error_output = 0
        self._last_output_at = time.monotonic()
        self._readers: list[threading.Thread] = []

        popen_options: dict[str, Any] = dict(options or {})
        popen_options.setdefault("cwd", cwd)
        popen_options.setdefault("env", _environment(env))
        if tty:
            # Inherit the parent's terminal: output goes to the screen and is
            # therefore not captured, exactly as Symfony's TTY mode behaves.
            stdio: dict[str, Any] = {"stdin": None, "stdout": None, "stderr": None}
        else:
            stdio = {
                "stdin": subprocess.PIPE if input is not None else subprocess.DEVNULL,
                "stdout": subprocess.PIPE,
                "stderr": subprocess.PIPE,
            }
        for key, value in stdio.items():
            popen_options.setdefault(key, value)

        # A string command goes through the shell and a list does not, which
        # is the distinction Laravel draws between its two command flavours.
        self._popen = subprocess.Popen(
            command,
            shell=isinstance(command, str),
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **popen_options,
        )

        if input is not None and self._popen.stdin is not None:
            self._write_input(input)
        self._pump(self._popen.stdout, OUT, self._output)
        self._pump(self._popen.stderr, ERR, self._error_output)

    # --- lifecycle ------------------------------------------------------

    def pid(self) -> int:
        return self._popen.pid

    def running(self) -> bool:
        return self._popen.poll() is None

    def exit_code(self) -> int | None:
        return self._popen.poll()

    def signal(self, sig: int) -> None:
        if self.running():
            self._popen.send_signal(sig)

    def stop(self, timeout: float = DEFAULT_STOP_TIMEOUT, sig: int | None = None) -> int | None:
        """Terminate the process, killing it if it outlives ``timeout``."""
        if self.running():
            self._popen.send_signal(sig if sig is not None else signal_module.SIGTERM)
            try:
                self._popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._popen.kill()
        return self.wait_for_exit()

    def wait_for_exit(self) -> int | None:
        code = self._popen.wait()
        for reader in self._readers:
            reader.join(timeout=1.0)
        return code

    def wait(self, timeout: float | None = None, idle_timeout: float | None = None) -> int | None:
        """Block until the process exits, honouring both timeout flavours.

        Returns the exit code, or ``None`` if a deadline passed — the caller
        decides whether that is a timeout exception or a poll returning early.
        """
        started_at = time.monotonic()
        while self.running():
            now = time.monotonic()
            if timeout is not None and now - started_at >= timeout:
                return None
            if idle_timeout is not None and now - self._idle_since() >= idle_timeout:
                return None
            time.sleep(_TICK)
        return self.wait_for_exit()

    def timed_out_kind(
        self, started_at: float, timeout: float | None, idle_timeout: float | None
    ) -> str | None:
        now = time.monotonic()
        if timeout is not None and now - started_at >= timeout:
            return "timeout"
        if idle_timeout is not None and now - self._idle_since() >= idle_timeout:
            return "idle"
        return None

    # --- output ---------------------------------------------------------

    def output(self) -> str:
        with self._lock:
            return "".join(self._output)

    def error_output(self) -> str:
        with self._lock:
            return "".join(self._error_output)

    def latest_output(self) -> str:
        with self._lock:
            chunk = "".join(self._output[self._seen_output :])
            self._seen_output = len(self._output)
            return chunk

    def latest_error_output(self) -> str:
        with self._lock:
            chunk = "".join(self._error_output[self._seen_error_output :])
            self._seen_error_output = len(self._error_output)
            return chunk

    def set_output_callback(self, callback: OutputCallback | None) -> None:
        """Attach a callback after the fact (``InvokedProcess.wait($callback)``)."""
        with self._lock:
            self._output_callback = callback

    # --- internals ------------------------------------------------------

    def _idle_since(self) -> float:
        with self._lock:
            return self._last_output_at

    def _write_input(self, payload: str | bytes) -> None:
        stdin = self._popen.stdin
        assert stdin is not None
        text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload

        def write() -> None:
            try:
                stdin.write(text)
                stdin.flush()
            except (BrokenPipeError, ValueError):  # pragma: no cover - racy shutdown
                pass
            finally:
                try:
                    stdin.close()
                except (BrokenPipeError, ValueError):  # pragma: no cover
                    pass

        thread = threading.Thread(target=write, daemon=True)
        thread.start()
        self._readers.append(thread)

    def _pump(self, stream: IO[str] | None, kind: str, sink: list[str]) -> None:
        if stream is None:
            return

        def read() -> None:
            try:
                for line in stream:
                    with self._lock:
                        sink.append(line)
                        self._last_output_at = time.monotonic()
                        callback = self._output_callback
                    if callback is not None:
                        callback(kind, line)
            except ValueError:  # pragma: no cover - stream closed under us
                pass
            finally:
                stream.close()

        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        self._readers.append(thread)


def _environment(env: Mapping[str, str] | None) -> dict[str, str] | None:
    """Merge into the inherited environment, the way Symfony Process does."""
    if env is None:
        return None
    merged = dict(os.environ)
    for key, value in env.items():
        if value is None:  # pragma: no cover - defensive
            merged.pop(key, None)
        else:
            merged[str(key)] = str(value)
    return merged
