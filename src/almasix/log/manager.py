"""Log manager — Laravel-shaped channels over stdlib logging."""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from almasix.framework.application import Application

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


class LogManager:
    """Resolves named channels from ``config/logging.py``."""

    def __init__(self, app: Application) -> None:
        self.app = app
        self._loggers: dict[str, logging.Logger] = {}

    def channel(self, name: str | None = None) -> logging.Logger:
        channel = name or str(self.app.config.get("logging.default", "stack") or "stack")
        if channel not in self._loggers:
            self._loggers[channel] = self._build_channel(channel)
        return self._loggers[channel]

    def _build_channel(self, name: str) -> logging.Logger:
        channels = self.app.config.get("logging.channels", {}) or {}
        config = dict(channels.get(name) or {})
        if not config:
            config = {"driver": "stderr", "level": "debug"}
        driver = str(config.get("driver", "stderr"))
        level = _LEVELS.get(str(config.get("level", "debug")).lower(), logging.DEBUG)
        logger = logging.getLogger(f"almasix.channel.{name}")
        logger.handlers.clear()
        logger.setLevel(level)
        logger.propagate = False

        if driver == "stack":
            for child in list(config.get("channels") or ["stderr"]):
                child_logger = self.channel(str(child))
                for handler in child_logger.handlers:
                    logger.addHandler(handler)
            if not logger.handlers:
                logger.addHandler(self._stderr_handler(level))
        elif driver == "single":
            path = self._resolve_path(config.get("path", "storage/logs/almasix.log"))
            path.parent.mkdir(parents=True, exist_ok=True)
            handler: logging.Handler = logging.FileHandler(path, encoding="utf-8")
            handler.setLevel(level)
            handler.setFormatter(self._formatter())
            logger.addHandler(handler)
        elif driver == "daily":
            path = self._resolve_path(config.get("path", "storage/logs/almasix.log"))
            path.parent.mkdir(parents=True, exist_ok=True)
            days = int(config.get("days", 14) or 14)
            handler = TimedRotatingFileHandler(
                path,
                when="midnight",
                backupCount=days,
                encoding="utf-8",
            )
            handler.setLevel(level)
            handler.setFormatter(self._formatter())
            logger.addHandler(handler)
        elif driver == "null":
            logger.addHandler(logging.NullHandler())
        else:
            logger.addHandler(self._stderr_handler(level))

        return logger

    def _resolve_path(self, path: Any) -> Path:
        candidate = Path(str(path))
        if candidate.is_absolute():
            return candidate
        return Path(self.app.base_path) / candidate

    @staticmethod
    def _formatter() -> logging.Formatter:
        return logging.Formatter(
            "[%(asctime)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    @staticmethod
    def _stderr_handler(level: int) -> logging.Handler:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        return handler


_manager: LogManager | None = None


def set_log_manager(manager: LogManager | None) -> None:
    global _manager
    _manager = manager


def get_log_manager() -> LogManager | None:
    return _manager


def get_logger(channel: str | None = None) -> logging.Logger:
    if _manager is None:
        logger = logging.getLogger("almasix")
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(
                logging.Formatter("[%(levelname)s] %(message)s")
            )
            logger.addHandler(handler)
            logger.setLevel(logging.DEBUG)
            logger.propagate = False
        return logger
    return _manager.channel(channel)
