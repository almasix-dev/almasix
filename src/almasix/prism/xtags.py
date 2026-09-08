"""Rewrite ``<x-name>`` / ``<x-slot>`` tags into Prism directives."""

from __future__ import annotations

import re
from typing import Any

_X_SLOT_NAMED = re.compile(
    r"<x-slot\s*:([a-zA-Z_][\w-]*)(\s[^>]*)?>(.*?)</x-slot\s*>",
    re.DOTALL | re.IGNORECASE,
)
_X_SLOT_ATTR = re.compile(
    r'<x-slot\s+name=(?:"([^"]+)"|\'([^\']+)\')(\s[^>]*)?>(.*?)</x-slot\s*>',
    re.DOTALL | re.IGNORECASE,
)
_X_OPEN = re.compile(r"<x-([a-zA-Z0-9_.-]+)(\s[^>]*)?>", re.IGNORECASE)
_X_SELF = re.compile(
    r"<x-([a-zA-Z0-9_.-]+)(\s[^>]*)?\s*/>",
    re.IGNORECASE,
)
_ATTR = re.compile(
    r"""([:@]?[a-zA-Z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
)
_ECHO_ONLY = re.compile(r"^\s*\{\{\s*(.+?)\s*\}\}\s*$", re.DOTALL)


def expand_x_tags(source: str) -> str:
    """Convert Blade-style ``<x-*>`` / ``<x-slot>`` into ``@component`` / ``@slot``."""
    source = _expand_x_slots(source)
    # Innermost component tags first so nesting works in one compile pass.
    while True:
        nxt = _expand_one_self(source)
        if nxt != source:
            source = nxt
            continue
        nxt = _expand_one_block(source)
        if nxt == source:
            break
        source = nxt
    return source


def _expand_x_slots(source: str) -> str:
    def repl_named(match: re.Match[str]) -> str:
        name = match.group(1).replace("-", "_")
        body = match.group(3)
        return f"@slot('{name}')\n{body}\n@endslot"

    def repl_attr(match: re.Match[str]) -> str:
        name = (match.group(1) or match.group(2) or "").replace("-", "_")
        body = match.group(4)
        return f"@slot('{name}')\n{body}\n@endslot"

    source = _X_SLOT_NAMED.sub(repl_named, source)
    source = _X_SLOT_ATTR.sub(repl_attr, source)
    return source


def _expand_one_self(source: str) -> str:
    match = _X_SELF.search(source)
    if not match:
        return source
    name = _component_name(match.group(1))
    attrs_expr = _attrs_expr(match.group(2) or "")
    replacement = f"@component({name!r}, {attrs_expr})\n@endcomponent"
    return source[: match.start()] + replacement + source[match.end() :]


def _expand_one_block(source: str) -> str:
    """Replace the innermost ``<x-name>…</x-name>`` pair."""
    candidates: list[tuple[int, int, int, str]] = []
    for open_match in _X_OPEN.finditer(source):
        name = open_match.group(1)
        if name.lower() == "slot":  # pragma: no cover
            continue
        close_re = re.compile(rf"</x-{re.escape(name)}\s*>", re.IGNORECASE)
        open_re = re.compile(
            rf"<x-{re.escape(name)}(?:\s[^>]*)?>",
            re.IGNORECASE,
        )
        depth = 1
        pos = open_match.end()
        end_match = None
        while depth and pos < len(source):
            next_open = open_re.search(source, pos)
            next_close = close_re.search(source, pos)
            if next_close is None:  # pragma: no cover
                break
            if next_open is not None and next_open.start() < next_close.start():
                depth += 1
                pos = next_open.end()
            else:
                depth -= 1
                if depth == 0:
                    end_match = next_close
                    break
                pos = next_close.end()
        if end_match is None:
            continue
        body = source[open_match.end() : end_match.start()]
        cname = _component_name(name)
        attrs_expr = _attrs_expr(open_match.group(2) or "")
        replacement = f"@component({cname!r}, {attrs_expr})\n{body}\n@endcomponent"
        span = end_match.end() - open_match.start()
        candidates.append((span, open_match.start(), end_match.end(), replacement))

    if not candidates:
        return source
    _, start, end, replacement = min(candidates, key=lambda item: item[0])
    return source[:start] + replacement + source[end:]


def _component_name(raw: str) -> str:
    """``forms.input`` / ``api-link`` → dotted snake for view resolution."""
    name = raw.replace(":", ".")
    parts = [p.replace("-", "_") for p in name.split(".")]
    return ".".join(parts)


def _attrs_expr(raw: str) -> str:
    attrs = _parse_attrs(raw)
    if not attrs:
        return "{}"
    parts: list[str] = []
    for key, value in attrs.items():
        if isinstance(value, _Expr):
            parts.append(f"{key!r}: {value.code}")
        elif value is True:
            parts.append(f"{key!r}: True")
        else:
            parts.append(f"{key!r}: {value!r}")
    return "{" + ", ".join(parts) + "}"


class _Expr:
    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        self.code = code


def _parse_attrs(raw: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for match in _ATTR.finditer(raw):
        key = match.group(1)
        dynamic = key.startswith(":") or key.startswith("@")
        key = key.lstrip(":@")
        if match.group(2) is not None:
            value: Any = match.group(2)
        elif match.group(3) is not None:
            value = match.group(3)
        elif match.group(4) is not None:  # pragma: no cover
            value = match.group(4)
        else:  # pragma: no cover
            value = True
        if dynamic and isinstance(value, str):
            attrs[key] = _Expr(value.strip())
        elif isinstance(value, str):
            echo = _ECHO_ONLY.match(value)
            if echo:
                attrs[key] = _Expr(echo.group(1).strip())
            else:
                attrs[key] = value
        else:  # pragma: no cover
            attrs[key] = value

    for token in re.findall(r"(?<![\w:.-])([a-zA-Z_][\w:.-]*)(?=(\s|$|/))", raw):
        name = token if isinstance(token, str) else token[0]
        if name in attrs or name in {"x"}:
            continue
        if not re.search(rf"{re.escape(name)}\s*=", raw):
            attrs.setdefault(name, True)
    return attrs
