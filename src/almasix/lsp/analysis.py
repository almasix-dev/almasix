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
    "action",
    "var",
    "directive",
    "vite",
    "url",
    "asset",
    "env",
    "table",
    "column",
    # Model instance attribute: ``user.name`` / ``{{ article.is_ }}``.
    "attr",
    # Cursor is somewhere in a template with no narrower context — used for an
    # explicitly invoked (Ctrl+Space) completion.
    "prism",
]

#: Languages whose documents are dotenv files rather than code.
DOTENV_LANGUAGES = frozenset({"dotenv", "env", "properties", "ini"})


@dataclass(frozen=True)
class StringCall:
    """A string argument to a framework helper, Prism directive, or route action."""

    kind: CallKind
    value: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    start_offset: int
    end_offset: int
    controller: str | None = None
    #: Owning table for a ``column`` call, when it can be resolved.
    table: str | None = None


@dataclass(frozen=True)
class CursorContext:
    """What the cursor is typing inside a string-keyed call or template variable."""

    kind: CallKind
    prefix: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    controller: str | None = None
    table: str | None = None
    #: When True, string completions are inserted as ``'value'`` (typed ``route(``).
    wrap_quotes: bool = False
    #: Leading whitespace on the current line (before ``@`` / the caret).
    line_indent: str = ""
    #: Receiver of an attribute access (``user`` in ``user.name``).
    receiver: str | None = None


@dataclass(frozen=True)
class TemplateVarRef:
    """A simple identifier inside ``{{ }}`` / ``{!! !!}`` or a directive argument."""

    name: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    start_offset: int
    end_offset: int


# ``__`` / ``trans`` → trans; ``.middleware(`` / ``middleware(`` → middleware.
_PY_CALL_RE = re.compile(
    r"""(?:\b(?P<kind>view|route|config|trans|__|env)\s*|\.(?P<mw>middleware)\s*)"""
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
    "env": "env",
    "middleware": "middleware",
}

#: Calls whose first string argument is a table name.
_TABLE_ANCHORS = (
    r"\bSchema\.(?:create_if_not_exists|create|table|rename|drop_if_exists|drop|has_table)"
    r"|\bDB\.table"
    r"|\.constrained"
    r"|\.(?:left_|right_|cross_)?join"
)

#: Calls whose first string argument is a column name (table inferred from context).
_COLUMN_ANCHORS = (
    r"where_not_between|where_between|where_json_contains|where_json_length|where_not_null"
    r"|where_not_in|where_null|where_date|where_time|where_day|where_month|where_year"
    r"|where_not|where_in|or_where|where"
    r"|order_by_desc|order_by|group_by|having_between|having"
    r"|add_select|select|pluck|value|increment|decrement"
    r"|sum|avg|max|min|latest|oldest|distinct"
)

#: ``Schema.has_column("posts", "slug")`` — table first, then column.
_TABLE_THEN_COLUMN_ANCHORS = (
    r"\bSchema\.(?:has_columns|has_column|column_type|has_index"
    r"|when_table_has_column|when_table_doesnt_have_column)"
)

_TABLE_CALL_RE = re.compile(rf"""(?:{_TABLE_ANCHORS})\s*\(\s*(?P<q>['"])(?P<value>[^'"]*)(?P=q)""")

_COLUMN_CALL_RE = re.compile(
    rf"""\.(?:{_COLUMN_ANCHORS})\s*\(\s*(?P<q>['"])(?P<value>[^'"]*)(?P=q)"""
)

_TABLE_COLUMN_CALL_RE = re.compile(
    rf"""{_TABLE_THEN_COLUMN_ANCHORS}\s*\(\s*(?P<tq>['"])(?P<table>[^'"]*)(?P=tq)"""
    rf"""\s*,\s*(?P<q>['"])(?P<value>[^'"]*)(?P=q)"""
)

_OPEN_TABLE_RE = re.compile(rf"""(?:{_TABLE_ANCHORS})\s*\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$""")

_OPEN_COLUMN_RE = re.compile(rf"""\.(?:{_COLUMN_ANCHORS})\s*\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$""")

_OPEN_TABLE_COLUMN_RE = re.compile(
    rf"""{_TABLE_THEN_COLUMN_ANCHORS}\s*\(\s*(?P<tq>['"])(?P<table>[^'"]*)(?P=tq)"""
    rf"""\s*,\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)

#: ``DB.table("posts")`` names the table a later ``.where("…")`` filters.
_TABLE_HINT_RE = re.compile(r"""\bDB\.table\s*\(\s*['"](?P<hint>[^'"]+)['"]""")

#: ``Post.where(…)`` — a model class standing in for its table.
_MODEL_HINT_RE = re.compile(r"\b(?P<hint>[A-Z][A-Za-z0-9_]*)\s*\.")

#: Capitalised names that are never models.
_NOT_MODELS = frozenset({"DB", "Schema", "Blueprint", "Migration", "Path", "Model"})

# ``[ProgressController, "index"]`` — Almasix route action tuples.
_CONTROLLER_ACTION_RE = re.compile(
    r"""\[\s*(?P<ctrl>[A-Za-z_][\w]*)\s*,\s*(?P<q>['"])(?P<value>[^'"]*)(?P=q)"""
)


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
    """Find ``view`` / ``route`` / ``config`` / ``trans`` / ``env`` / table / column strings."""
    calls = _find_calls(source, _PY_CALL_RE, kind_map=_PY_KIND_MAP)
    calls.extend(find_controller_actions(source))
    calls.extend(find_database_calls(source))
    return calls


def find_database_calls(source: str) -> list[StringCall]:
    """Find table and column string arguments in schema and query-builder calls."""
    calls: list[StringCall] = []

    for match in _TABLE_COLUMN_CALL_RE.finditer(source):
        calls.append(_call_from(source, match, "column", table=match.group("table")))
    taken = {(call.start_offset, call.end_offset) for call in calls}

    for kind, pattern in (("table", _TABLE_CALL_RE), ("column", _COLUMN_CALL_RE)):
        for match in pattern.finditer(source):
            span = (match.start("value"), match.end("value"))
            if span in taken:
                continue
            table = database_table_hint(source, match.start("value")) if kind == "column" else None
            calls.append(_call_from(source, match, kind, table=table))
            taken.add(span)
    return calls


def _call_from(
    source: str,
    match: re.Match[str],
    kind: CallKind,
    *,
    table: str | None = None,
) -> StringCall:
    value_start = match.start("value")
    value_end = match.end("value")
    sl, sc = _offset_to_position(source, value_start)
    el, ec = _offset_to_position(source, value_end)
    return StringCall(
        kind=kind,
        value=match.group("value"),
        start_line=sl,
        start_character=sc,
        end_line=el,
        end_character=ec,
        start_offset=value_start,
        end_offset=value_end,
        table=table,
    )


def database_table_hint(source: str, offset: int, *, lookbehind: int = 400) -> str | None:
    """Nearest table or model name before a column argument, if any.

    Returns a raw hint — ``"posts"`` from ``DB.table("posts")`` or ``"Post"``
    from ``Post.where(…)``. Resolving a class name to its table needs the
    index, so that happens in the feature layer.
    """
    window_start = max(0, offset - lookbehind)
    window = source[window_start:offset]
    best: str | None = None
    best_at = -1
    for pattern in (_TABLE_HINT_RE, _MODEL_HINT_RE):
        for match in pattern.finditer(window):
            hint = match.group("hint")
            if hint in _NOT_MODELS:
                continue
            if match.start() > best_at:
                best, best_at = hint, match.start()
    return best


def find_controller_actions(source: str) -> list[StringCall]:
    """Find ``[SomeController, "method"]`` route action string arguments."""
    calls: list[StringCall] = []
    for match in _CONTROLLER_ACTION_RE.finditer(source):
        value_start = match.start("value")
        value_end = match.end("value")
        sl, sc = _offset_to_position(source, value_start)
        el, ec = _offset_to_position(source, value_end)
        calls.append(
            StringCall(
                kind="action",
                value=match.group("value"),
                start_line=sl,
                start_character=sc,
                end_line=el,
                end_character=ec,
                start_offset=value_start,
                end_offset=value_end,
                controller=match.group("ctrl"),
            )
        )
    return calls


def find_prism_calls(source: str) -> list[StringCall]:
    """Find ``@include`` / ``@extends`` / ``@lang`` string arguments."""
    return _find_calls(source, _PRISM_INCLUDE_RE, kind_map=_PRISM_KIND_MAP)


def find_calls(source: str, *, language: str) -> list[StringCall]:
    """Dispatch by language id (``python`` / ``prism`` / ``html`` / ``dotenv``)."""
    lang = language.lower()
    if lang in DOTENV_LANGUAGES:
        return find_dotenv_references(source)
    if lang in {"python", "py"}:
        return find_python_calls(source)
    if lang in {"prism", "html", "prism-html"}:
        return find_prism_calls(source)
    return find_python_calls(source) + find_prism_calls(source)


#: ``${OTHER_KEY}`` inside a value — the interpolation python-dotenv expands.
_DOTENV_REFERENCE_RE = re.compile(r"\$\{(?P<value>[A-Za-z_][A-Za-z0-9_]*)\}")

#: The key being assigned on a line: ``KEY=value`` / ``export KEY=value``.
_DOTENV_ASSIGN_RE = re.compile(
    r"^(?P<lead>\s*(?:export\s+)?)(?P<value>[A-Za-z_][A-Za-z0-9_]*)(?=\s*=)",
    re.MULTILINE,
)

_OPEN_DOTENV_REFERENCE_RE = re.compile(r"\$\{(?P<prefix>[A-Za-z_][A-Za-z0-9_]*)?$")

_OPEN_DOTENV_KEY_RE = re.compile(r"^\s*(?:export\s+)?(?P<prefix>[A-Za-z_][A-Za-z0-9_]*)?$")


def find_dotenv_references(source: str) -> list[StringCall]:
    """Env keys in a dotenv file: the key each line assigns, and ``${…}`` uses."""
    calls: list[StringCall] = []
    for pattern in (_DOTENV_ASSIGN_RE, _DOTENV_REFERENCE_RE):
        for match in pattern.finditer(source):
            line_start = source.rfind("\n", 0, match.start()) + 1
            if source[line_start:].lstrip().startswith("#"):
                continue
            calls.append(_call_from(source, match, "env"))
    return calls


def dotenv_context_at(source: str, line: int, character: int) -> CursorContext | None:
    """Completion inside ``${…}``, or while typing a key at the start of a line."""
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    prefix_line = lines[line][:character]
    if prefix_line.lstrip().startswith("#"):
        return None

    for pattern in (_OPEN_DOTENV_REFERENCE_RE, _OPEN_DOTENV_KEY_RE):
        if pattern is _OPEN_DOTENV_KEY_RE and "=" in prefix_line:
            continue
        match = pattern.search(prefix_line)
        if match is None:
            continue
        prefix = match.group("prefix") or ""
        return CursorContext(
            kind="env",
            prefix=prefix,
            start_line=line,
            start_character=character - len(prefix),
            end_line=line,
            end_character=character,
        )
    return None


def call_at(source: str, line: int, character: int, *, language: str) -> StringCall | None:
    """Return the string call whose value range contains the cursor."""
    for call in find_calls(source, language=language):
        if _contains(call, line, character):
            return call
    return None


def context_at(source: str, line: int, character: int, *, language: str) -> CursorContext | None:
    """Completion context when the cursor is inside (or at the edge of) a string arg."""
    lang = language.lower()
    if lang in DOTENV_LANGUAGES:
        open_ctx = dotenv_context_at(source, line, character)
        if open_ctx is not None:
            return open_ctx
        call = call_at(source, line, character, language=language)
        if call is None:
            return None
        return CursorContext(
            kind=call.kind,
            prefix=_prefix_before_cursor(source, call, line, character),
            start_line=call.start_line,
            start_character=call.start_character,
            end_line=call.end_line,
            end_character=call.end_character,
        )
    if lang in {"prism", "html", "prism-html"}:
        return _prism_context_at(source, line, character, language=language)
    call = call_at(source, line, character, language=language)
    if call is not None:
        prefix = _prefix_before_cursor(source, call, line, character)
        return CursorContext(
            kind=call.kind,
            prefix=prefix,
            start_line=call.start_line,
            start_character=call.start_character,
            end_line=call.end_line,
            end_character=call.end_character,
            controller=call.controller,
            table=call.table,
        )
    open_ctx = _open_string_context(source, line, character, language=language)
    if open_ctx is not None:
        return open_ctx
    return attribute_context_at(source, line, character)


def _prism_context_at(source: str, line: int, character: int, *, language: str) -> CursorContext:
    """Narrowest context in a template, falling back to ``prism`` (offer everything).

    Never returns ``None``: an explicit Ctrl+Space in a template should always
    have something to say, even in the middle of plain markup.
    """
    # Helper string args (``route("…")``) win over the surrounding echo.
    helper_ctx = prism_helper_context_at(source, line, character)
    if helper_ctx is not None:
        return helper_ctx
    call = call_at(source, line, character, language=language)
    if call is not None:
        return CursorContext(
            kind=call.kind,
            prefix=_prefix_before_cursor(source, call, line, character),
            start_line=call.start_line,
            start_character=call.start_character,
            end_line=call.end_line,
            end_character=call.end_character,
            controller=call.controller,
        )
    open_ctx = _open_string_context(source, line, character, language=language)
    if open_ctx is not None:
        return open_ctx
    dir_ctx = directive_name_context_at(source, line, character)
    if dir_ctx is not None:
        return dir_ctx
    attr_ctx = attribute_context_at(source, line, character, in_island=True)
    if attr_ctx is not None:
        return attr_ctx
    var_ctx = template_var_context_at(source, line, character)
    if var_ctx is not None:
        return var_ctx

    lines = source.splitlines()
    prefix_line = lines[line][:character] if 0 <= line < len(lines) else ""
    match = re.search(r"([A-Za-z_][\w]*)$", prefix_line)
    prefix = match.group(1) if match else ""
    start_character = character - len(prefix)
    return CursorContext(
        kind="prism",
        prefix=prefix,
        start_line=line,
        start_character=start_character,
        end_line=line,
        end_character=character,
        line_indent=_leading_ws(prefix_line[:start_character]),
    )


_IDENT_RE = re.compile(r"[A-Za-z_][\w]*")
_DIRECTIVE_ARG_RE = re.compile(
    r"@(?P<dir>if|elseif|unless|isset|empty|forelse|foreach|for|while)\s*\("
)


def template_var_at(source: str, line: int, character: int) -> TemplateVarRef | None:
    """Return the simple identifier under the cursor in an echo / directive arg."""
    offset = _position_to_offset(source, line, character)
    if offset is None:
        return None
    island = _echo_island_at(source, offset)
    if island is None:
        island = _directive_arg_island_at(source, offset)
    if island is None:
        return None
    start, end = island
    for match in _IDENT_RE.finditer(source, start, end):
        if match.start() <= offset <= match.end():
            sl, sc = _offset_to_position(source, match.start())
            el, ec = _offset_to_position(source, match.end())
            return TemplateVarRef(
                name=match.group(0),
                start_line=sl,
                start_character=sc,
                end_line=el,
                end_character=ec,
                start_offset=match.start(),
                end_offset=match.end(),
            )
    return None


def template_var_context_at(source: str, line: int, character: int) -> CursorContext | None:
    """Completion context inside ``{{ }}`` / ``{!! !!}`` or ``@if(…)`` args."""
    offset = _position_to_offset(source, line, character)
    if offset is None:
        return None
    island = _echo_island_at(source, offset)
    if island is None:
        island = _directive_arg_island_at(source, offset)
    if island is None:
        return None
    start, _end = island
    before = source[start:offset]
    # Dotted attributes are handled by ``attribute_context_at``.
    if re.search(r"\.\s*[A-Za-z_][\w]*$", before) or re.search(r"\.\s*$", before):
        return None
    match = re.search(r"([A-Za-z_][\w]*)$", before)
    prefix = match.group(1) if match else ""
    prefix_start = offset - len(prefix)
    sl, sc = _offset_to_position(source, prefix_start)
    el, ec = _offset_to_position(source, offset)
    return CursorContext(
        kind="var",
        prefix=prefix,
        start_line=sl,
        start_character=sc,
        end_line=el,
        end_character=ec,
    )


_ATTR_ACCESS_RE = re.compile(
    r"(?P<recv>[A-Za-z_][\w]*)\.(?P<prefix>[A-Za-z_][\w]*)?$"
)


def attribute_context_at(
    source: str,
    line: int,
    character: int,
    *,
    in_island: bool = False,
) -> CursorContext | None:
    """``user.|`` / ``user.na|`` — replace range is only the attribute segment."""
    offset = _position_to_offset(source, line, character)
    if offset is None:
        return None
    if in_island:
        island = _echo_island_at(source, offset)
        if island is None:
            island = _directive_arg_island_at(source, offset)
        if island is None:
            return None
        before = source[island[0] : offset]
    else:
        line_start = source.rfind("\n", 0, offset) + 1
        before = source[line_start:offset]
        # Skip when the caret is clearly inside a string literal on this line.
        if _inside_line_string(before):
            return None

    match = _ATTR_ACCESS_RE.search(before)
    if match is None:
        return None
    recv = match.group("recv")
    if recv in _NOT_MODELS:
        return None
    prefix = match.group("prefix") or ""
    prefix_start = offset - len(prefix)
    sl, sc = _offset_to_position(source, prefix_start)
    el, ec = _offset_to_position(source, offset)
    return CursorContext(
        kind="attr",
        prefix=prefix,
        start_line=sl,
        start_character=sc,
        end_line=el,
        end_character=ec,
        receiver=recv,
    )


def _inside_line_string(before: str) -> bool:
    """True when ``before`` ends inside an unclosed ``'`` / ``"`` on the line."""
    in_single = False
    in_double = False
    i = 0
    while i < len(before):
        ch = before[i]
        if ch == "\\" and (in_single or in_double):
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return in_single or in_double


# Helpers may be written as ``{{ route('x') }}``, ``@route('x')`` or inside a
# directive argument, so these are matched anywhere in the template rather than
# only inside an echo island.
# Longest names first so ``route_is(`` is not read as ``route``.
_PRISM_HELPER_NAMES = (
    r"signed_route|route_is|route|secure_url|url|secure_asset|asset|vite|config|__|trans"
)

_PRISM_HELPER_RE = re.compile(
    rf"""@?\b(?P<kind>{_PRISM_HELPER_NAMES})\s*\(\s*(?P<q>['"])(?P<value>[^'"]*)""",
    re.DOTALL,
)

_PRISM_HELPER_KIND_MAP: dict[str, CallKind] = {
    "route": "route",
    "signed_route": "route",
    "route_is": "route",
    "url": "url",
    "secure_url": "url",
    "asset": "asset",
    "secure_asset": "asset",
    "vite": "vite",
    "config": "config",
    "__": "trans",
    "trans": "trans",
}

_OPEN_PRISM_HELPER_RE = re.compile(
    rf"""@?\b(?P<kind>{_PRISM_HELPER_NAMES})\s*\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)

#: ``route(`` with no quote yet — still offer names (inserted as ``'name'``).
_OPEN_PRISM_HELPER_BARE_RE = re.compile(rf"""@?\b(?P<kind>{_PRISM_HELPER_NAMES})\s*\(\s*$""")

_OPEN_DIRECTIVE_RE = re.compile(r"@(?P<prefix>[A-Za-z_][\w]*)$")


def prism_helper_context_at(source: str, line: int, character: int) -> CursorContext | None:
    """Completion inside ``route("…")`` / ``vite("…")`` string args in a template."""
    offset = _position_to_offset(source, line, character)
    if offset is None:
        return None
    call = prism_helper_call_at(source, line, character)
    if call is not None:
        sl, sc = _offset_to_position(source, call.start_offset)
        el, ec = _offset_to_position(source, offset)
        return CursorContext(
            kind=call.kind,
            prefix=source[call.start_offset : offset],
            start_line=sl,
            start_character=sc,
            end_line=el,
            end_character=ec,
        )
    # Still typing the argument, so there is no closing quote to match yet.
    line_start = source.rfind("\n", 0, offset) + 1
    before = source[line_start:offset]
    open_match = _OPEN_PRISM_HELPER_RE.search(before)
    if open_match is not None:
        kind = _PRISM_HELPER_KIND_MAP.get(open_match.group("kind"))
        if kind is None:  # pragma: no cover
            return None
        prefix = open_match.group("prefix")
        sl, sc = _offset_to_position(source, offset - len(prefix))
        el, ec = _offset_to_position(source, offset)
        return CursorContext(
            kind=kind,
            prefix=prefix,
            start_line=sl,
            start_character=sc,
            end_line=el,
            end_character=ec,
        )
    bare = _OPEN_PRISM_HELPER_BARE_RE.search(before)
    if bare is None:
        return None
    kind = _PRISM_HELPER_KIND_MAP.get(bare.group("kind"))
    if kind is None:  # pragma: no cover
        return None
    # Replace the ``(…)`` span with ``('name')`` so clients never treat the
    # surrounding ``{{`` echo as part of the completion token.
    paren_offset = line_start + before.rfind("(")
    end_offset = offset
    if end_offset < len(source) and source[end_offset] == ")":
        end_offset += 1
    sl, sc = _offset_to_position(source, paren_offset)
    el, ec = _offset_to_position(source, end_offset)
    return CursorContext(
        kind=kind,
        prefix="",
        start_line=sl,
        start_character=sc,
        end_line=el,
        end_character=ec,
        wrap_quotes=True,
    )


def prism_helper_call_at(source: str, line: int, character: int) -> StringCall | None:
    """``route("name")`` etc. under the cursor anywhere in a template."""
    offset = _position_to_offset(source, line, character)
    if offset is None:
        return None
    for match in _PRISM_HELPER_RE.finditer(source):
        value_start = match.start("value")
        close = source.find(match.group("q"), value_start)
        value_end = close if close >= 0 else match.end("value")
        if not (value_start <= offset <= value_end):
            continue
        kind = _PRISM_HELPER_KIND_MAP.get(match.group("kind"))
        if kind is None:  # pragma: no cover - regex only emits mapped kinds
            continue
        sl, sc = _offset_to_position(source, value_start)
        el, ec = _offset_to_position(source, value_end)
        return StringCall(
            kind=kind,
            value=source[value_start:value_end],
            start_line=sl,
            start_character=sc,
            end_line=el,
            end_character=ec,
            start_offset=value_start,
            end_offset=value_end,
        )
    return None


def directive_name_context_at(source: str, line: int, character: int) -> CursorContext | None:
    """Completion for ``@dir…`` while typing a directive name.

    The replace range starts at ``@`` so accepting a snippet cannot strip the
    sigil when the editor treats ``@if`` as a single token.
    """
    lines = source.splitlines()
    if line < 0 or line >= len(lines):
        return None
    prefix_line = lines[line][:character]
    match = _OPEN_DIRECTIVE_RE.search(prefix_line)
    if match is None:
        return None
    return CursorContext(
        kind="directive",
        prefix=match.group("prefix"),
        start_line=line,
        start_character=match.start(),  # include the ``@``
        end_line=line,
        end_character=character,
        line_indent=_leading_ws(prefix_line[: match.start()]),
    )


def _leading_ws(text: str) -> str:
    """Spaces / tabs at the start of ``text``."""
    i = 0
    while i < len(text) and text[i] in " \t":
        i += 1
    return text[:i]


def _position_to_offset(source: str, line: int, character: int) -> int | None:
    lines = source.splitlines(keepends=True)
    if line < 0:
        return None
    if line > len(lines):
        return None
    if line == len(lines):
        return len(source) if character == 0 else None
    offset = sum(len(lines[i]) for i in range(line)) + character
    return min(max(0, offset), len(source))


def _echo_island_at(source: str, offset: int) -> tuple[int, int] | None:
    """Inner ``(start, end)`` of ``{{ … }}`` / ``{!! … !!}`` containing offset."""
    open_pos = -1
    open_kind: str | None = None
    i = min(offset, len(source) - 1) if source else -1
    while i >= 0:
        if source.startswith("{{--", i):
            i -= 1
            continue
        if source.startswith("{!!", i):
            open_pos = i
            open_kind = "raw"
            break
        if source.startswith("{{", i):
            open_pos = i
            open_kind = "echo"
            break
        i -= 1
    if open_pos < 0 or open_kind is None:
        return None
    if open_kind == "raw":
        inner_start = open_pos + 3
        close = source.find("!!}", inner_start)
    else:
        inner_start = open_pos + 2
        close = source.find("}}", inner_start)
    inner_end = close if close >= 0 else len(source)
    if offset < inner_start or offset > inner_end:
        return None
    return inner_start, inner_end


def _directive_arg_island_at(source: str, offset: int) -> tuple[int, int] | None:
    """Inner ``(start, end)`` of ``@if(…)``-style args containing offset."""
    matches = list(_DIRECTIVE_ARG_RE.finditer(source[: offset + 1]))
    if not matches:
        return None
    match = matches[-1]
    paren = match.end() - 1
    if paren < 0 or paren >= len(source) or source[paren] != "(":
        return None
    depth = 0
    end = len(source)
    for i in range(paren, len(source)):
        c = source[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    inner_start = paren + 1
    if not (inner_start <= offset <= end):
        return None
    return inner_start, end


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
    r"""(?:\b(?P<kind>view|route|config|trans|__|env)\s*|\.(?P<mw>middleware)\s*)"""
    r"""\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)
_OPEN_PRISM_RE = re.compile(
    r"""@(?P<kind>include(?:If|When|Unless)?|extends|lang)\s*\(\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)
_OPEN_ACTION_RE = re.compile(
    r"""\[\s*(?P<ctrl>[A-Za-z_][\w]*)\s*,\s*(?P<q>['"])(?P<prefix>[^'"]*)$"""
)


def _open_string_context(
    source: str, line: int, character: int, *, language: str
) -> CursorContext | None:
    lines = source.splitlines()
    if line >= len(lines):
        return None
    prefix_line = lines[line][:character]
    lang = language.lower()

    if lang in {"python", "py", "plaintext"} or lang not in {
        "prism",
        "html",
        "prism-html",
    }:
        action = _OPEN_ACTION_RE.search(prefix_line)
        if action is not None:
            return CursorContext(
                kind="action",
                prefix=action.group("prefix"),
                start_line=line,
                start_character=action.start("prefix"),
                end_line=line,
                end_character=character,
                controller=action.group("ctrl"),
            )

    if lang in {"python", "py", "plaintext"}:
        db_ctx = _open_database_context(source, line, character, prefix_line)
        if db_ctx is not None:
            return db_ctx

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
        return CursorContext(
            kind=kind,
            prefix=match.group("prefix"),
            start_line=line,
            start_character=match.start("prefix"),
            end_line=line,
            end_character=character,
        )
    return None


def _open_database_context(
    source: str,
    line: int,
    character: int,
    prefix_line: str,
) -> CursorContext | None:
    """Table / column completion while the argument is still being typed."""
    # `Schema.has_column("posts", "…")` names its own table, so it wins.
    match = _OPEN_TABLE_COLUMN_RE.search(prefix_line)
    if match is not None:
        return _open_context(match, line, character, "column", table=match.group("table"))
    match = _OPEN_TABLE_RE.search(prefix_line)
    if match is not None:
        return _open_context(match, line, character, "table")
    match = _OPEN_COLUMN_RE.search(prefix_line)
    if match is not None:
        offset = _position_to_offset(source, line, character)
        hint = database_table_hint(source, offset) if offset is not None else None
        return _open_context(match, line, character, "column", table=hint)
    return None


def _open_context(
    match: re.Match[str],
    line: int,
    character: int,
    kind: CallKind,
    *,
    table: str | None = None,
) -> CursorContext:
    return CursorContext(
        kind=kind,
        prefix=match.group("prefix"),
        start_line=line,
        start_character=match.start("prefix"),
        end_line=line,
        end_character=character,
        table=table,
    )


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
