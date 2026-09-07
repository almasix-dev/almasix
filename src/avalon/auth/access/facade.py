"""Static ``Gate`` façade over :class:`~avalon.auth.access.gate.Gate`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from avalon.auth.access.gate import Gate as AccessGate
from avalon.auth.access.response import AuthorizationResponse

GuessCallback = Callable[[type], str | type | Sequence[str | type] | None]


class Gate:
    """App-facing authorization helpers."""

    _gate: AccessGate | None = None

    @classmethod
    def set_gate(cls, gate: AccessGate | None) -> None:
        cls._gate = gate

    @classmethod
    def get_gate(cls) -> AccessGate:
        if cls._gate is None:
            from avalon.auth.access.helpers import resolve_gate

            cls._gate = resolve_gate()
        return cls._gate

    @classmethod
    def define(cls, ability: str, callback: Any) -> AccessGate:
        return cls.get_gate().define(ability, callback)

    @classmethod
    def policy(cls, model: type, policy: type) -> AccessGate:
        return cls.get_gate().policy(model, policy)

    @classmethod
    def register_policies(cls, policies: dict[type, type]) -> AccessGate:
        return cls.get_gate().register_policies(policies)

    @classmethod
    def resource(
        cls,
        name: str,
        policy: type,
        abilities: dict[str, str] | None = None,
    ) -> AccessGate:
        return cls.get_gate().resource(name, policy, abilities)

    @classmethod
    def before(cls, callback: Callable[..., Any]) -> AccessGate:
        return cls.get_gate().before(callback)

    @classmethod
    def after(cls, callback: Callable[..., Any]) -> AccessGate:
        return cls.get_gate().after(callback)

    @classmethod
    def guess_policy_names_using(cls, callback: GuessCallback) -> AccessGate:
        return cls.get_gate().guess_policy_names_using(callback)

    @classmethod
    def default_deny_response(cls, callback: Any) -> AccessGate:
        return cls.get_gate().default_deny_response(callback)

    @classmethod
    def has(cls, ability: str) -> bool:
        return cls.get_gate().has(ability)

    @classmethod
    def abilities(cls) -> dict[str, Any]:
        return cls.get_gate().abilities()

    @classmethod
    def policies(cls) -> dict[type, type]:
        return cls.get_gate().policies()

    @classmethod
    def flush(cls) -> None:
        cls.get_gate().flush()

    @classmethod
    def for_user(cls, user: Any) -> AccessGate:
        return cls.get_gate().for_user(user)

    @classmethod
    def allows(cls, ability: str, arguments: Any = None) -> bool:
        return cls.get_gate().allows(ability, arguments)

    @classmethod
    def denies(cls, ability: str, arguments: Any = None) -> bool:
        return cls.get_gate().denies(ability, arguments)

    @classmethod
    def check(cls, abilities: str | Sequence[str], arguments: Any = None) -> bool:
        return cls.get_gate().check(abilities, arguments)

    @classmethod
    def any(cls, abilities: Sequence[str], arguments: Any = None) -> bool:
        return cls.get_gate().any(abilities, arguments)

    @classmethod
    def none(cls, abilities: Sequence[str], arguments: Any = None) -> bool:
        return cls.get_gate().none(abilities, arguments)

    @classmethod
    def authorize(cls, ability: str, arguments: Any = None) -> AuthorizationResponse:
        return cls.get_gate().authorize(ability, arguments)

    @classmethod
    def inspect(cls, ability: str, arguments: Any = None) -> AuthorizationResponse:
        return cls.get_gate().inspect(ability, arguments)

    @classmethod
    def get_policy_for(cls, model: Any) -> Any | None:
        return cls.get_gate().get_policy_for(model)
