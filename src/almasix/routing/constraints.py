"""Route parameter constraints — Laravel's `where`, enforced while routing.

A constraint is not a check inside the handler. `/{id}` constrained to digits
must *not match* `/posts/hello`, so that `/posts/{slug}` registered after it
can. Starlette expresses that with path convertors, so each distinct regex is
registered as one, named after a hash of the pattern itself: the same
constraint on a thousand routes registers a single convertor, and two
different ones never collide.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from starlette.convertors import CONVERTOR_TYPES, Convertor, register_url_convertor

#: `{name}`, `{name?}`, `{name:field}`, `{name:field?}`.
PARAMETER_RE = re.compile(
    r"\{(?P<name>[A-Za-z_][A-Za-z0-9_]*)(?::(?P<field>[A-Za-z0-9_]+))?(?P<optional>\?)?\}"
)

#: Convertors Starlette ships. A `{post:int}` means the converter, not a
#: binding field — see `binding_field_of`.
BUILTIN_CONVERTORS = frozenset({"str", "path", "int", "float", "uuid"})

#: Laravel's `whereUuid` / `whereUlid` / `whereAlpha` patterns.
UUID_PATTERN = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
ULID_PATTERN = r"[0-7][0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{25}"
NUMBER_PATTERN = r"[0-9]+"
ALPHA_PATTERN = r"[a-zA-Z]+"
ALPHA_NUMERIC_PATTERN = r"[a-zA-Z0-9]+"


class _PatternConvertor(Convertor[str]):
    """A registered regex. Values stay strings; casting is the model's job."""

    def __init__(self, pattern: str) -> None:
        self.regex = pattern

    def convert(self, value: str) -> str:
        return value

    def to_string(self, value: str) -> str:
        return str(value)


def convertor_for(pattern: str) -> str:
    """Register ``pattern`` as a path convertor and return its name."""
    digest = hashlib.sha1(pattern.encode("utf-8")).hexdigest()[:12]
    name = f"almasix_{digest}"
    if name not in CONVERTOR_TYPES:
        register_url_convertor(name, _PatternConvertor(pattern))
    return name


def in_pattern(values: Any) -> str:
    """Laravel's `whereIn` — an alternation of the literal values."""
    return "|".join(re.escape(str(value)) for value in values)


def parameter_names(uri: str) -> list[str]:
    """Every parameter in ``uri``, in the order it appears."""
    return [match.group("name") for match in PARAMETER_RE.finditer(uri)]


def optional_parameters(uri: str) -> list[str]:
    """The parameters written `{name?}`."""
    return [match.group("name") for match in PARAMETER_RE.finditer(uri) if match.group("optional")]


def binding_fields(uri: str) -> dict[str, str]:
    """`{user:slug}` -> ``{"user": "slug"}``, skipping Starlette's convertors."""
    found: dict[str, str] = {}
    for match in PARAMETER_RE.finditer(uri):
        field = match.group("field")
        if field and field not in BUILTIN_CONVERTORS:
            found[match.group("name")] = field
    return found


def compile_uri(uri: str, wheres: dict[str, str]) -> tuple[str, ...]:
    """Compile an Almasix URI into the Starlette paths that answer it.

    One path normally, and one more for each optional parameter — Starlette has
    no optional segment, so `/user/{name?}` is registered as `/user/{name}` and
    `/user`, and the handler's own default fills in the second.
    """
    base = _rewrite(uri, wheres)
    optional = optional_parameters(uri)
    if not optional:
        return (base,)

    paths = [base]
    trimmed = uri
    # Trailing optionals drop right to left, so `/a/{b?}/{c?}` answers
    # `/a/{b}/{c}`, `/a/{b}`, and `/a`.
    for _ in reversed(optional):
        trimmed = _drop_last_segment(trimmed)
        paths.append(_rewrite(trimmed, wheres))
    return tuple(dict.fromkeys(paths))


def _rewrite(uri: str, wheres: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group("name")
        field = match.group("field")
        pattern = wheres.get(name)
        if pattern:
            return f"{{{name}:{convertor_for(pattern)}}}"
        if field and field in BUILTIN_CONVERTORS:
            return f"{{{name}:{field}}}"
        return f"{{{name}}}"

    return PARAMETER_RE.sub(replace, uri)


def _drop_last_segment(uri: str) -> str:
    head, _, _ = uri.rstrip("/").rpartition("/")
    return head or "/"
