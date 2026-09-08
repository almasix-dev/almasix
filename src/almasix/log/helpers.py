"""``log()`` helper — Laravel-shaped façade over LogManager."""

from __future__ import annotations

import logging
from typing import Any

from almasix.log.manager import get_logger


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

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(logging.CRITICAL, message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("exc_info", True)
        self._emit(logging.ERROR, message, *args, **kwargs)

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        self._emit(level, message, *args, **kwargs)


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
