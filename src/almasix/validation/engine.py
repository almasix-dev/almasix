"""Attribute validation engine — runs parsed RuleBase lists over a payload."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from almasix.validation.parser import parse_ruleset
from almasix.validation.rules.base import RuleBase, data_get, is_blank


class AttributeValidator:
    """Validate ``data`` against a field → rules mapping (Laravel Validator core)."""

    def __init__(
        self,
        data: Mapping[str, Any],
        rules: Mapping[str, Any],
        *,
        messages: Mapping[str, str] | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> None:
        self._data = dict(data)
        self._rules = parse_ruleset(dict(rules))
        self._messages = dict(messages or {})
        self._attributes = dict(attributes or {})
        self._errors: dict[str, list[str]] | None = None
        self._validated: dict[str, Any] | None = None

    def passes(self) -> bool:
        return not self.fails()

    def fails(self) -> bool:
        self._run()
        return bool(self._errors)

    def errors(self) -> dict[str, list[str]]:
        self._run()
        return dict(self._errors or {})

    def validated(self) -> dict[str, Any]:
        self._run()
        if self._errors:
            from almasix.validation.form_request import ValidationException

            raise ValidationException(dict(self._errors))
        assert self._validated is not None
        return dict(self._validated)

    validate = validated

    def _run(self) -> None:
        if self._errors is not None:
            return
        errors: dict[str, list[str]] = {}
        excluded: set[str] = set()
        working = deepcopy(self._data)

        for attribute, rule_list in self._rules.items():
            if attribute in excluded:
                continue

            sometimes = any(getattr(r, "is_sometimes", False) for r in rule_list)
            if sometimes and attribute not in working:
                continue

            for rule in rule_list:
                if _is_exclude_rule(rule):
                    if _should_exclude(rule, attribute, working):
                        excluded.add(attribute)
                        working.pop(attribute, None)
                    continue

            if attribute in excluded:
                continue

            value = data_get(working, attribute, _MISSING)
            present = value is not _MISSING
            actual = None if not present else value

            nullable = any(getattr(r, "is_nullable", False) for r in rule_list)
            if nullable and is_blank(actual if present else None):
                if present:
                    working[attribute] = actual
                continue

            bail = False
            for rule in rule_list:
                if getattr(rule, "is_bail", False):
                    bail = True
                    continue
                if _is_exclude_rule(rule):
                    continue
                if getattr(rule, "is_nullable", False) or getattr(rule, "is_sometimes", False):
                    continue

                if not getattr(rule, "implicit", False) and is_blank(actual if present else None):
                    continue

                ok = rule.passes(attribute, actual if present else None, working)
                if ok:
                    if getattr(rule, "name", "") == "prohibits":
                        for other in rule.params().get("other", "").split(","):
                            other = other.strip()
                            if other:
                                excluded.add(other)
                                working.pop(other, None)
                    continue

                message = _format_message(
                    attribute,
                    rule,
                    actual if present else None,
                    working,
                    messages=self._messages,
                    attributes=self._attributes,
                )
                errors.setdefault(attribute, []).append(message)
                if bail:
                    break

        self._errors = errors
        if errors:
            self._validated = None
        else:
            # Only keys that were ruled, minus excluded.
            result = {}
            for attribute in self._rules:
                if attribute in excluded:
                    continue
                if attribute in working:
                    result[attribute] = working[attribute]
                elif attribute in self._data:
                    result[attribute] = self._data[attribute]
            self._validated = result


_MISSING = object()

_EXCLUDE_NAMES = frozenset(
    {"exclude", "exclude_if", "exclude_unless", "exclude_with", "exclude_without"}
)


def _is_exclude_rule(rule: RuleBase) -> bool:
    return (
        rule.name in _EXCLUDE_NAMES
        or getattr(rule, "exclude", False)
        or getattr(rule, "is_exclude", False)
    )


def _should_exclude(rule: RuleBase, attribute: str, data: Mapping[str, Any]) -> bool:
    name = rule.name
    params = rule.params() if hasattr(rule, "params") else {}

    if name == "exclude":
        return True

    if name == "exclude_if":
        # builtins stores exclude_if as (other, target) or params
        pair = getattr(rule, "exclude_if", None)
        if pair:
            other, target = pair[0], pair[1]
            return str(data_get(data, str(other))) == str(target)
        other = params.get("other")
        values = params.get("values") or params.get("value")
        if other is None:
            return False
        current = str(data_get(data, str(other)))
        if isinstance(values, (list, tuple)):
            return current in {str(v) for v in values}
        return current == str(values)

    if name == "exclude_unless":
        pair = getattr(rule, "exclude_unless", None)
        if pair:
            other, target = pair[0], pair[1]
            return str(data_get(data, str(other))) != str(target)
        other = params.get("other")
        values = params.get("values") or params.get("value")
        if other is None:
            return False
        current = str(data_get(data, str(other)))
        if isinstance(values, (list, tuple)):
            return current not in {str(v) for v in values}
        return current != str(values)

    if name == "exclude_with":
        other = getattr(rule, "exclude_with", None) or params.get("other")
        return other is not None and not is_blank(data_get(data, str(other)))

    if name == "exclude_without":
        other = getattr(rule, "exclude_without", None) or params.get("other")
        return other is not None and is_blank(data_get(data, str(other)))

    return False


def _format_message(
    attribute: str,
    rule: RuleBase,
    value: Any,
    data: Mapping[str, Any],
    *,
    messages: Mapping[str, str],
    attributes: Mapping[str, str],
) -> str:
    from almasix.translation import get_translator
    from almasix.validation.messages import humanize

    rule_name = rule.name
    custom = rule.message()
    attribute_label = attributes.get(attribute) or humanize(attribute)
    params = {"attribute": attribute_label, **rule.params()}
    # Normalize common placeholders
    if "other" in params and isinstance(params["other"], str):
        params["other"] = attributes.get(params["other"]) or humanize(params["other"])
    if "values" in params and isinstance(params["values"], (list, tuple)):
        params["values"] = ", ".join(str(v) for v in params["values"])
    kind = None
    if hasattr(rule, "size_kind"):
        kind = rule.size_kind(value)

    override = messages.get(f"{attribute}.{rule_name}") or messages.get(attribute)
    translator = get_translator()
    if override is not None:
        return translator.make_replacements(override, params)
    if custom:
        return translator.make_replacements(custom, params)

    keys: list[str] = []
    if kind:
        keys.append(f"validation.{rule_name}.{kind}")
    keys.append(f"validation.{rule_name}")
    for key in keys:
        resolved = translator.get(key)
        if isinstance(resolved, str) and resolved != key:
            # Map :min/:max for size rules using value placeholder when needed
            if "value" in params and "min" not in params:
                params.setdefault("min", params["value"])
            if "value" in params and "max" not in params:
                params.setdefault("max", params["value"])
            return translator.make_replacements(resolved, params)
    return f"The {attribute_label} is invalid."


__all__ = ["AttributeValidator"]
