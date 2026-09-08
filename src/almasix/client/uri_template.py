"""RFC 6570 URI template expansion (used by ``with_url_parameters``).

Laravel expands ``withUrlParameters`` through a URI template implementation, so
``{+endpoint}/{page}`` behaves the same here: simple expansion percent-encodes
reserved characters, while the ``+`` and ``#`` operators keep them intact.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

_EXPRESSION = re.compile(r"\{([^{}]+)\}")
_UNRESERVED = "-._~"
_RESERVED = _UNRESERVED + ":/?#[]@!$&'()*+,;="

# operator -> (prefix, separator, keys are named, empty values keep "=")
_OPERATORS: dict[str, tuple[str, str, bool, bool]] = {
    "": ("", ",", False, False),
    "+": ("", ",", False, False),
    "#": ("#", ",", False, False),
    ".": (".", ".", False, False),
    "/": ("/", "/", False, False),
    ";": (";", ";", True, False),
    "?": ("?", "&", True, True),
    "&": ("&", "&", True, True),
}


def expand(template: str, variables: Mapping[str, Any]) -> str:
    """Expand ``{var}`` expressions in ``template`` using ``variables``."""
    return _EXPRESSION.sub(lambda match: _expand_expression(match.group(1), variables), template)


def _expand_expression(expression: str, variables: Mapping[str, Any]) -> str:
    operator = expression[0] if expression[0] in _OPERATORS and expression[0] != "" else ""
    if operator:
        expression = expression[1:]
    prefix, separator, named, keep_equals = _OPERATORS[operator]
    allow_reserved = operator in ("+", "#")

    parts: list[str] = []
    for spec in expression.split(","):
        name, explode, max_length = _parse_spec(spec)
        if name not in variables:
            continue
        value = variables[name]
        if value is None:
            continue
        rendered = _render(
            name, value, explode, max_length, named, keep_equals, separator, allow_reserved
        )
        if rendered is not None:
            parts.append(rendered)
    if not parts:
        return ""
    return prefix + separator.join(parts)


def _parse_spec(spec: str) -> tuple[str, bool, int | None]:
    explode = spec.endswith("*")
    if explode:
        spec = spec[:-1]
    max_length: int | None = None
    if ":" in spec:
        spec, _, length = spec.partition(":")
        max_length = int(length)
    return spec, explode, max_length


def _render(
    name: str,
    value: Any,
    explode: bool,
    max_length: int | None,
    named: bool,
    keep_equals: bool,
    separator: str,
    allow_reserved: bool,
) -> str | None:
    if isinstance(value, Mapping):
        return _render_mapping(name, value, explode, named, keep_equals, separator, allow_reserved)
    if isinstance(value, (list, tuple)) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    ):
        return _render_list(name, value, explode, named, keep_equals, separator, allow_reserved)
    text = _encode(_stringify(value), allow_reserved)
    if max_length is not None:
        text = text[:max_length]
    if named:
        return _pair(name, text, keep_equals)
    return text


def _render_mapping(
    name: str,
    value: Mapping[str, Any],
    explode: bool,
    named: bool,
    keep_equals: bool,
    separator: str,
    allow_reserved: bool,
) -> str | None:
    if not value:
        return None
    if explode:
        pairs = [
            f"{_encode(str(k), allow_reserved)}={_encode(_stringify(v), allow_reserved)}"
            for k, v in value.items()
        ]
        return separator.join(pairs)
    flat = ",".join(
        f"{_encode(str(k), allow_reserved)},{_encode(_stringify(v), allow_reserved)}"
        for k, v in value.items()
    )
    return _pair(name, flat, keep_equals) if named else flat


def _render_list(
    name: str,
    value: Sequence[Any],
    explode: bool,
    named: bool,
    keep_equals: bool,
    separator: str,
    allow_reserved: bool,
) -> str | None:
    items = [_encode(_stringify(item), allow_reserved) for item in value]
    if not items:
        return None
    if explode:
        if named:
            return separator.join(_pair(name, item, keep_equals) for item in items)
        return separator.join(items)
    joined = ",".join(items)
    return _pair(name, joined, keep_equals) if named else joined


def _pair(name: str, text: str, keep_equals: bool) -> str:
    if text == "" and not keep_equals:
        return name
    return f"{name}={text}"


def _stringify(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _encode(text: str, allow_reserved: bool) -> str:
    return quote(text, safe=_RESERVED if allow_reserved else _UNRESERVED)
