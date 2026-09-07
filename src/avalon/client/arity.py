"""Callback arity detection — Laravel closures often ignore trailing arguments."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any


def accepts_two_arguments(callback: Callable[..., Any]) -> bool:
    """True when ``callback`` can take a second positional argument."""
    try:
        parameters = inspect.signature(callback).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins without signatures
        return False
    if any(p.kind is p.VAR_POSITIONAL for p in parameters.values()):
        return True
    positional = [
        p for p in parameters.values() if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    return len(positional) >= 2
