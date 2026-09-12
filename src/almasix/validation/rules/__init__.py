"""Laravel-shaped validation rules — registry, base contracts, and the fluent `Rule` builder.

Importing this package registers every built-in rule (`almasix.validation.rules.builtins`
runs its `register_all()` at import time), then exposes:

- `LARAVEL_RULES` — the canonical, sorted tuple of every rule name Almasix ships.
- `RuleBase` — the base class every rule (built-in or app-defined) subclasses.
- `make_rule(name, *parameters)` — build a rule instance from its string form.
- `Rule` — a fluent factory matching Laravel's `Rule::` style, e.g. `Rule.email()`,
  `Rule.min(3)`, `Rule.exists("users", "email")`. `in` is a Python keyword, so
  the `in` rule is reachable as `Rule.in_(...)`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from almasix.validation.rules import builtins  # noqa: F401 - registers every built-in rule
from almasix.validation.rules.base import RuleBase, data_get, is_blank
from almasix.validation.rules.registry import LARAVEL_RULES, make_rule, register, registered_names


class Rule:
    """Fluent Laravel-style rule builder.

    Every name in :data:`LARAVEL_RULES` is available as a static method here,
    named identically except for ``in`` (a Python keyword), which is exposed
    as :meth:`Rule.in_`::

        Rule.email("dns")
        Rule.min(3)
        Rule.between(1, 10)
        Rule.in_("draft", "published")
        Rule.exists("users", "email")
    """


def _rule_factory(rule_name: str) -> Callable[..., RuleBase]:
    def factory(*parameters: Any) -> RuleBase:
        return make_rule(rule_name, *(str(parameter) for parameter in parameters))

    factory.__name__ = rule_name
    factory.__qualname__ = f"Rule.{rule_name}"
    factory.__doc__ = f"Build the `{rule_name}` validation rule (Laravel `Rule::{rule_name}()`)."
    return factory


for _rule_name in LARAVEL_RULES:
    setattr(
        Rule, "in_" if _rule_name == "in" else _rule_name, staticmethod(_rule_factory(_rule_name))
    )
del _rule_name


__all__ = [
    "LARAVEL_RULES",
    "Rule",
    "RuleBase",
    "data_get",
    "is_blank",
    "make_rule",
    "register",
    "registered_names",
]
