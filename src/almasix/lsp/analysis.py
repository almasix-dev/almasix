"""Locate string-keyed call sites in Python and Prism sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

CallKind = Literal[
    "view",
    "route",
    "config",
    "include",
    "extends",
    "trans",
    "middleware",
]


@dataclass(frozen=True)
class StringCall:
    """A string argument to a framework helper or Prism directive."""

    kind: CallKind
    value: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    start_offset: int
    end_offset: int


@dataclass(frozen=True)
class CursorContext:
    """What the cursor is typing inside a string-keyed call."""

    kind: CallKind
    prefix: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int


# ``__`` / ``trans`` → trans; ``.middleware(`` / ``middleware(`` → middleware.
_PY_CALL_RE = re.compile(
    r"""(?:\b(?P<kind>view|route|config|trans|__)\s*|\.(?P<mw>middleware)\s*)"""
    r"""\(\s*(?P<q>['"])(?P<value>.*?)(?P=q)""",
    re.DOTALL,
)

_PRISM_INCLUDE_RE = re.compile(
    r"""@(?P<kind>include(?:If|When|Unless)?|extends|lang)\s*\(\s*(?P<q>['"])(?P<value>.*?)(?P=q)""",
    re.DOTALL,
)

_PRISM_KIND_MAP: dict[str, CallKind] = {
    "include": "include",
    "includeIf": "include",
    "includeWhen": "include",
    "includeUnless": "include",
    "extends": "extends",
    "lang": "trans",
}

_PY_KIND_MAP: dict[str, CallKind] = {
    "view": "view",
    "route": "route",
    "config": "config",
    "trans": "trans",
    "__": "trans",
    "middleware": "middleware",
}


def _offset_to_position(source: str, offset: int) -> tuple[int, int]:
    line = source.count("\n", 0, offset)
    last_nl = source.rfind("\n", 0, offset)
    character = offset if last_nl < 0 else offset - last_nl - 1
    return line, character


def _find_calls(
    source: str,
    pattern: re.Pattern[str],
    *,
    kind_map: dict[str, CallKind],
) -> list[StringCall]:
    calls: list[StringCall] = []
    for match in pattern.finditer(source):
        raw_kind = match.groupdict().get("kind") or match.groupdict().get("mw")
        if raw_kind is None:  # pragma: no cover - regex always sets one group
            continue
        mapped = kind_map.get(raw_kind)
        if mapped is None:  # pragma: no cover - regex only emits mapped kinds
            continue
        value_start = match.start("value")
        value_end = match.end("value")
        sl, sc = _offset_to_position(source, value_start)
        el, ec = _offset_to_position(source, value_end)
        calls.append(
            StringCall(
                kind=mapped,
                value=match.group("value"),
                start_line=sl,
                start_character=sc,
                end_line=el,
                end_character=ec,
                start_offset=value_start,
                end_offset=value_end,
            )
        )
    return calls


def find_python_calls(source: str) -> list[StringCall]:
    """Find ``view`` / ``route`` / ``config`` / ``trans`` / ``middleware`` string args."""
    return _find_calls(source, _PY_CALL_RE, kind_map=_PY_KIND_MAP)


def find_prism_calls(source: str) -> list[StringCall]:
    """Find ``@include`` / ``@extends`` / ``@lang`` string arguments."""
    return _find_calls(source, _PRISM_INCLUDE_RE, kind_map=_PRISM_KIND_MAP)


def find_calls(source: str, *, language: str) -> list[StringCall]:
    """Dispatch by language id (``python`` / ``prism`` / ``html``)."""
    lang = language.lower()
    if lang in {"python", "py"}:
        return find_python_calls(source)
    if lang in {"prism", "html", "prism-html"}:
        return find_prism_calls(source)
    return find_python_calls(source) + find_prism_calls(source)


def call_at(source: str, line: int, character: int, *, language: str) -> StringCall | None:
    """Return the string call whose value range contains the cursor."""
    for call in find_calls(source, language=language):
        if _contains(call, line, character):
            return call
    return None


def context_at(source: str, line: int, character: int, *, language: str) -> CursorContext | None:
    """Completion context when the cursor is inside (or at the edge of) a string arg."""
    call = call_at(source, line, character, language=language)
    if call is None:
        return _open_string_context(source, line, character, language=language)
    prefix = _prefix_before_cursor(source, call, line, character)
    return CursorContext(
        kind=call.kind,
        prefix=prefix,
        start_line=call.start_line,
        start_character=call.start_character,
        end_line=call.end_line,
        end_character=call.end_character,
    )


def _contains(call: StringCall, line: int, character: int) -> bool:
    if line < call.start_line or line > call.end_line:
        return False
    if line == call.start_line and character < call.start_character:
        return False
    if line == call.end_line and character > call.end_character:
        return False
    return True


def _prefix_before_cursor(source: str, call: StringCall, line: int, character: int) -> str:
    lines = source.splitlines()
    if line >= len(lines):
        return call.value
    offset = 0
    for i, text in enumerate(lines):
        if i == line:
            offset += character
            break
        offset += len(text) + 1
    if offset < call.start_offset:
        return ""
    return source[call.start_offset : min(offset, call.end_offset)]


_OPEN_PY_RE = re.compile(
    r"""(?:\b(?P<kind>view|route|config|trans|__)\s*|\.(?P<mw>middleware)\s*)"""
    r"""\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)
_OPEN_PRISM_RE = re.compile(
    r"""@(?P<kind>include(?:If|When|Unless)?|extends|lang)\s*\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)


def _open_string_context(
    source: str, line: int, character: int, *, language: str
) -> CursorContext | None:
    lines = source.splitlines()
    if line >= len(lines):
        return None
    prefix_line = lines[line][:character]
    lang = language.lower()
    patterns: list[tuple[re.Pattern[str], dict[str, CallKind]]] = []
    if lang in {"python", "py", "plaintext"}:
        patterns.append((_OPEN_PY_RE, _PY_KIND_MAP))
    if lang in {"prism", "html", "prism-html", "plaintext"}:
        patterns.append((_OPEN_PRISM_RE, _PRISM_KIND_MAP))
    if not patterns:
        patterns = [(_OPEN_PY_RE, _PY_KIND_MAP), (_OPEN_PRISM_RE, _PRISM_KIND_MAP)]

    for pattern, kind_map in patterns:
        match = pattern.search(prefix_line)
        if match is None:
            continue
        raw = match.groupdict().get("kind") or match.groupdict().get("mw")
        if raw is None:  # pragma: no cover
            continue
        kind = kind_map.get(raw)
        if kind is None:  # pragma: no cover
            continue
        start_char = match.start("prefix")
        return CursorContext(
            kind=kind,
            prefix=match.group("prefix"),
            start_line=line,
            start_character=start_char,
            end_line=line,
            end_character=character,
        )
    return None


_DIRECTIVE_AT_RE = re.compile(r"@(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")


def directive_at(source: str, line: int, character: int) -> str | None:
    """Return the ``@name`` under the cursor in a Prism template, if any."""
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    text = lines[line]
    for match in _DIRECTIVE_AT_RE.finditer(text):
        start = match.start()
        end = match.end()
        if start <= character <= end:
            return match.group("name")
    return None
