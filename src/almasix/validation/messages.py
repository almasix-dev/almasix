"""Translate Pydantic validation errors into Laravel-shaped messages."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

# Pydantic error types mapped onto Laravel rule names, so apps override messages
# with familiar keys ("email.required") instead of Pydantic internals.
_RULES: dict[str, str] = {
    "missing": "required",
    "string_type": "string",
    "int_type": "integer",
    "int_parsing": "integer",
    "int_from_float": "integer",
    "float_type": "numeric",
    "float_parsing": "numeric",
    "decimal_parsing": "numeric",
    "bool_type": "boolean",
    "bool_parsing": "boolean",
    "list_type": "array",
    "string_too_short": "min",
    "too_short": "min",
    "greater_than_equal": "min",
    "string_too_long": "max",
    "too_long": "max",
    "less_than_equal": "max",
    "greater_than": "gt",
    "less_than": "lt",
    "string_pattern_mismatch": "regex",
    "literal_error": "in",
    "enum": "in",
    "url_type": "url",
    "url_parsing": "url",
    "uuid_type": "uuid",
    "uuid_parsing": "uuid",
    "date_type": "date",
    "date_parsing": "date",
    "datetime_type": "date",
    "datetime_parsing": "date",
    "json_invalid": "json",
    "value_error": "custom",
}

# Which flavour of the size messages applies, keyed by Pydantic error type.
_SIZE_KINDS = {
    "string_too_short": "string",
    "string_too_long": "string",
    "too_short": "array",
    "too_long": "array",
    "greater_than_equal": "numeric",
    "less_than_equal": "numeric",
}


class _Blanks(dict):
    """Render unknown placeholders as empty rather than raising."""

    def __missing__(self, key: str) -> str:
        return ""


def humanize(field: str) -> str:
    """`first_name` -> `first name`, keeping dotted paths intact."""
    return field.replace("_", " ")


def _field_path(location: tuple[Any, ...]) -> str:
    return ".".join(str(part) for part in location)


def _params(error: dict[str, Any], attribute: str) -> dict[str, Any]:
    context = dict(error.get("ctx") or {})
    params: dict[str, Any] = {"attribute": attribute, **context}
    for key in ("min_length", "ge", "gt"):
        if key in context:
            params.setdefault("min", context[key])
    for key in ("max_length", "le", "lt"):
        if key in context:
            params.setdefault("max", context[key])
    return params


def message_for(
    error: dict[str, Any],
    *,
    messages: dict[str, str] | None = None,
    attributes: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Return `(field, message)` for one Pydantic error."""
    field = _field_path(error.get("loc", ()))
    error_type = str(error.get("type", ""))
    rule = _RULES.get(error_type, error_type)

    overrides = messages or {}
    attribute = (attributes or {}).get(field) or humanize(field)
    params = _params(error, attribute)

    override = overrides.get(f"{field}.{rule}") or overrides.get(field)
    if override is not None:
        # App overrides may use str.format `{attribute}` or Laravel `:attribute`.
        text = override
        try:
            text = override.format_map(_Blanks(params))
        except (ValueError, KeyError):
            pass
        from almasix.translation import get_translator

        return field, get_translator().make_replacements(text, params)

    if rule == "custom":
        # Custom validators surface their own text; drop Pydantic's prefix.
        raw = str(error.get("msg", "")).removeprefix("Value error, ")
        return field, raw or f"The {attribute} is invalid."

    kind = _SIZE_KINDS.get(error_type)

    from almasix.translation import get_translator

    translator = get_translator()
    keys: list[str] = []
    if kind:
        keys.append(f"validation.{rule}.{kind}")
    if rule in {"min", "max"}:
        keys.append(f"validation.{rule}.numeric")
    keys.append(f"validation.{rule}")

    template = None
    for candidate in keys:
        resolved = translator.get(candidate)
        if isinstance(resolved, str) and resolved != candidate:
            template = resolved
            break

    if template is None:
        return field, str(error.get("msg", "")) or f"The {attribute} is invalid."

    return field, translator.make_replacements(template, params)


def translate(
    error: ValidationError,
    *,
    messages: dict[str, str] | None = None,
    attributes: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """Convert a Pydantic `ValidationError` into `{field: [messages]}`."""
    bag: dict[str, list[str]] = {}
    for item in error.errors():
        field, text = message_for(item, messages=messages, attributes=attributes)
        bag.setdefault(field, []).append(text)
    return bag
