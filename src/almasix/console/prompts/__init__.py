"""Almasix Prompts — Laravel Prompts-shaped interactive console UI."""

from __future__ import annotations

from almasix.console.prompts.busy import Progress, progress, spin
from almasix.console.prompts.choices import multiselect, search, select, suggest
from almasix.console.prompts.confirm import confirm, pause
from almasix.console.prompts.inputs import number, password, text, textarea
from almasix.console.prompts.messages import (
    alert,
    clear,
    error,
    info,
    intro,
    note,
    outro,
    table,
    warning,
)

__all__ = [
    "Progress",
    "alert",
    "clear",
    "confirm",
    "error",
    "info",
    "intro",
    "multiselect",
    "note",
    "number",
    "outro",
    "password",
    "pause",
    "progress",
    "search",
    "select",
    "spin",
    "suggest",
    "table",
    "text",
    "textarea",
    "warning",
]
