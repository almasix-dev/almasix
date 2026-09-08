"""Concurrency exceptions."""

from __future__ import annotations


class ConcurrencyException(Exception):
    """Base concurrency error."""


class UnsupportedDriverException(ConcurrencyException):
    """The configured driver does not exist, or cannot run here."""


class TaskFailedException(ConcurrencyException):
    """A task failed in a child process and could not be sent back intact.

    Exceptions are returned to the parent by pickling them. When that is not
    possible — a custom exception with an unpicklable payload, say — this
    stands in for it, carrying the original text.
    """
