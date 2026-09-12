"""Parse Laravel-style rule strings and lists into RuleBase instances."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from almasix.validation.rules.base import RuleBase
from almasix.validation.rules.registry import make_rule


def parse_rule_string(expression: str) -> list[RuleBase]:
    """Parse ``required|min:3|in:a,b`` into rule instances."""
    parts = _split_pipes(expression)
    return [_parse_one(part) for part in parts if part]


def parse_field_rules(rules: str | RuleBase | Sequence[Any]) -> list[RuleBase]:
    if isinstance(rules, RuleBase):
        return [rules]
    if isinstance(rules, str):
        return parse_rule_string(rules)
    out: list[RuleBase] = []
    for item in rules:
        if isinstance(item, RuleBase):
            out.append(item)
        elif isinstance(item, str):
            out.extend(parse_rule_string(item))
        else:
            raise TypeError(f"Unsupported rule item: {type(item)!r}")
    return out


def parse_ruleset(rules: dict[str, Any]) -> dict[str, list[RuleBase]]:
    return {field: parse_field_rules(spec) for field, spec in rules.items()}


def _split_pipes(expression: str) -> list[str]:
    """Split on ``|`` not escaped as ``\\|``."""
    parts: list[str] = []
    buf: list[str] = []
    escaped = False
    for ch in expression:
        if escaped:
            buf.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "|":
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf).strip())
    return parts


def _parse_one(part: str) -> RuleBase:
    if ":" in part:
        name, _, rest = part.partition(":")
        name = name.strip().lower()
        # regex: pattern may contain commas — keep as one parameter unless Rule.regex style
        if name in {"regex", "not_regex"}:
            return make_rule(name, rest)
        params = [p.strip() for p in rest.split(",")]
        return make_rule(name, *params)
    return make_rule(part.strip().lower())


__all__ = ["parse_field_rules", "parse_rule_string", "parse_ruleset"]
