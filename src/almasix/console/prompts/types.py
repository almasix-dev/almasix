"""Shared types and interactive detection for Almasix Prompts."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any, TypeAlias

ValidateFn: TypeAlias = Callable[[Any], str | None]
Required: TypeAlias = bool | str


def is_interactive() -> bool:
    """True when prompts can use a TTY UI (Laravel Prompts fallback gate)."""
    if os.environ.get("ALMASIX_PROMPTS_INTERACTIVE", "").lower() in {"0", "false", "no"}:
        return False
    if os.environ.get("CI", "").lower() in {"1", "true", "yes"}:
        return False
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def required_message(required: Required) -> str | None:
    if required is False:
        return None
    if required is True:
        return "Required."
    return str(required)


def run_validation(value: Any, *, required: Required, validate: ValidateFn | None) -> str | None:
    if required_message(required) and (value is None or value == "" or value == []):
        return required_message(required)
    if validate is None:
        return None
    return validate(value)
