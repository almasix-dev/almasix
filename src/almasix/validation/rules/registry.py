"""Canonical Laravel 12 available-validation-rules list + factory registry."""

from __future__ import annotations

from collections.abc import Callable

from almasix.validation.rules.base import RuleBase

# Flat sorted list — docs, parity matrix, and tests must stay in sync.
LARAVEL_RULES: tuple[str, ...] = (
    "accepted",
    "accepted_if",
    "active_url",
    "after",
    "after_or_equal",
    "alpha",
    "alpha_dash",
    "alpha_num",
    "any_of",
    "array",
    "ascii",
    "bail",
    "before",
    "before_or_equal",
    "between",
    "boolean",
    "confirmed",
    "contains",
    "current_password",
    "date",
    "date_equals",
    "date_format",
    "decimal",
    "declined",
    "declined_if",
    "different",
    "digits",
    "digits_between",
    "dimensions",
    "distinct",
    "doesnt_contain",
    "doesnt_end_with",
    "doesnt_start_with",
    "email",
    "encoding",
    "ends_with",
    "enum",
    "exclude",
    "exclude_if",
    "exclude_unless",
    "exclude_with",
    "exclude_without",
    "exists",
    "extensions",
    "file",
    "filled",
    "gt",
    "gte",
    "hex_color",
    "image",
    "in",
    "in_array",
    "in_array_keys",
    "integer",
    "ip",
    "ipv4",
    "ipv6",
    "json",
    "list",
    "lowercase",
    "lt",
    "lte",
    "mac_address",
    "max",
    "max_digits",
    "mimes",
    "mimetypes",
    "min",
    "min_digits",
    "missing",
    "missing_if",
    "missing_unless",
    "missing_with",
    "missing_with_all",
    "multiple_of",
    "not_in",
    "not_regex",
    "nullable",
    "numeric",
    "present",
    "present_if",
    "present_unless",
    "present_with",
    "present_with_all",
    "prohibited",
    "prohibited_if",
    "prohibited_if_accepted",
    "prohibited_if_declined",
    "prohibited_unless",
    "prohibits",
    "regex",
    "required",
    "required_array_keys",
    "required_if",
    "required_if_accepted",
    "required_if_declined",
    "required_unless",
    "required_with",
    "required_with_all",
    "required_without",
    "required_without_all",
    "same",
    "size",
    "sometimes",
    "starts_with",
    "string",
    "timezone",
    "ulid",
    "unique",
    "uppercase",
    "url",
    "uuid",
)

_FACTORIES: dict[str, Callable[..., RuleBase]] = {}


def register(name: str, factory: Callable[..., RuleBase]) -> None:
    _FACTORIES[name] = factory


def make_rule(name: str, *parameters: str) -> RuleBase:
    factory = _FACTORIES.get(name)
    if factory is None:
        raise ValueError(f"Unknown validation rule: {name}")
    return factory(*parameters)


def registered_names() -> frozenset[str]:
    return frozenset(_FACTORIES)


__all__ = [
    "LARAVEL_RULES",
    "make_rule",
    "register",
    "registered_names",
]
