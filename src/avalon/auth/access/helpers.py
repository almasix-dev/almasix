"""Functional helpers: ``gate`` / ``authorize`` / Caliburn ``@can``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from avalon.auth.access.facade import Gate
from avalon.auth.access.gate import Gate as AccessGate
from avalon.auth.access.response import AuthorizationResponse


def resolve_gate() -> AccessGate:
    """Return the bound gate, or a process-local instance."""
    existing = Gate._gate
    if existing is not None:
        return existing
    instance = AccessGate()
    Gate.set_gate(instance)
    return instance


def gate() -> AccessGate:
    return Gate.get_gate()


def authorize(ability: str, arguments: Any = None) -> AuthorizationResponse:
    return Gate.authorize(ability, arguments)


def gate_allows(ability: str, *arguments: Any) -> bool:
    if not arguments:
        return Gate.allows(ability)
    if len(arguments) == 1:
        return Gate.allows(ability, arguments[0])
    return Gate.allows(ability, list(arguments))


def gate_any(abilities: Sequence[str], *arguments: Any) -> bool:
    payload: Any
    if not arguments:
        payload = None
    elif len(arguments) == 1:
        payload = arguments[0]
    else:
        payload = list(arguments)
    return Gate.any(list(abilities), payload)
