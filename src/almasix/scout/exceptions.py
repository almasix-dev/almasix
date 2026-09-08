"""What search says when it cannot do what was asked."""

from __future__ import annotations


class ScoutException(RuntimeError):
    """Base class for search failures."""


class UnsupportedEngineException(ScoutException):
    """Raised when `config/scout.py` names an engine nobody registered."""


class SearchException(ScoutException):
    """Raised when a search service answers with an error."""
