"""``log()`` / ``Log`` — Laravel-shaped logging for applications.

Prefer ``Log.info(...)`` (or ``log().info(...)``) over reaching for the
manager factory. Channels and shared context stay one hop away:

    Log.info("Application started")
    Log.channel("stderr").warning("Something odd")
    Log.with_(request_id="abc").info("Checked out")
"""

from __future__ import annotations

import logging
from typing import Any

from almasix.log.manager import get_logger

# Between INFO and WARNING — shows as SUCCESS in the default formatter.
SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")


class LogWriter:
    """Channel-bound writer with optional shared context."""

    def __init__(
        self,
        channel: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self._channel = channel
        self._context: dict[str, Any] = dict(context or {})

    def with_(self, **context: Any) -> LogWriter:
        """Return a writer that merges ``context`` into every subsequent log call."""
        merged = {**self._context, **context}
        return LogWriter(self._channel, merged)

    # Laravel alias style
    def with_context(self, context: dict[str, Any] | None = None, **kwargs: Any) -> LogWriter:
        data = {**(context or {}), **kwargs}
        return self.with_(**data)

    def _logger(self) -> logging.Logger:
        return get_logger(self._channel)

    def _emit(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        extra = dict(kwargs.pop("extra", {}) or {})
        if self._context:
            extra = {**self._context, **extra}
        if extra:
            kwargs["extra"] = extra
            # Surface context in the message when the formatter has no %(context)s.
            ctx = " ".join(f"{key}={value!r}" for key, value in extra.items())
            message = f"{message} [{ctx}]"
        self._logger().log(level, message, *args, **kwargs)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.INFO, message, *args, **kwargs)

    def notice(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.INFO, message, *args, **kwargs)

    def success(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Application success line — between info and warning in severity."""
        self._emit(SUCCESS, message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.CRITICAL, message, *args, **kwargs)

    def alert(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.CRITICAL, message, *args, **kwargs)

    def emergency(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.CRITICAL, message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._emit(logging.ERROR, message, *args, **kwargs)

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(level, message, *args, **kwargs)


class Log:
    """Static façade — ``Log.info`` / ``Log.debug`` / ``Log.channel`` / …

    Mirrors Laravel's ``Log`` facade so application code reads like::

        from almasix.log import Log

        Log.info("Ready")
        Log.debug("payload", extra={"id": 7})
        Log.channel("stderr").warning("odd")
        Log.with_(user_id=1).success("Checked out")
    """

    @classmethod
    def channel(cls, name: str | None = None) -> LogWriter:
        return LogWriter(name)

    @classmethod
    def stack(cls, channels: list[str] | tuple[str, ...] | str) -> LogWriter:
        """Write through the first named channel (stack fan-out is config-side).

        Laravel's ``Log::stack([...])`` builds an on-the-fly stack. Almasix apps
        declare stacks in ``config/logging.py``; this returns a writer for the
        first channel so call sites stay familiar.
        """
        if isinstance(channels, str):
            return LogWriter(channels)
        names = [str(name) for name in channels]
        return LogWriter(names[0] if names else None)

    @classmethod
    def build(cls, channel: str | None = None) -> LogWriter:
        return LogWriter(channel)

    @classmethod
    def with_(cls, **context: Any) -> LogWriter:
        return LogWriter().with_(**context)

    @classmethod
    def with_context(cls, context: dict[str, Any] | None = None, **kwargs: Any) -> LogWriter:
        return LogWriter().with_context(context, **kwargs)

    @classmethod
    def debug(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().debug(message, *args, **kwargs)

    @classmethod
    def info(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().info(message, *args, **kwargs)

    @classmethod
    def notice(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().notice(message, *args, **kwargs)

    @classmethod
    def success(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().success(message, *args, **kwargs)

    @classmethod
    def warning(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().warning(message, *args, **kwargs)

    @classmethod
    def error(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().error(message, *args, **kwargs)

    @classmethod
    def critical(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().critical(message, *args, **kwargs)

    @classmethod
    def alert(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().alert(message, *args, **kwargs)

    @classmethod
    def emergency(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().emergency(message, *args, **kwargs)

    @classmethod
    def exception(cls, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().exception(message, *args, **kwargs)

    @classmethod
    def log(cls, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        LogWriter().log(level, message, *args, **kwargs)


def log(channel: str | None = None) -> LogWriter:
    """Return a log writer for ``channel`` (or the default channel)."""
    return LogWriter(channel)


def logger(message: str | None = None, context: dict[str, Any] | None = None) -> LogWriter | None:
    """Write a debug line, or return the writer when given no message (Laravel ``logger``)."""
    if message is None:
        return LogWriter()
    LogWriter().debug(message, extra=context or {})
    return None


def info(message: str, context: dict[str, Any] | None = None) -> None:
    """Write an informational line to the default channel (Laravel ``info``)."""
    LogWriter().info(message, extra=context or {})
