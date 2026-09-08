"""Compile ``.prism.html`` source into a Python render function.

Blade-parity surface (growing): echo, layouts, includes, control flow.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

RenderFn = Callable[[dict[str, Any], Any], str]
DirectiveHandler = Callable[[str], str]

_COMMENT_RE = re.compile(r"\{\{--.*?--\}\}", re.DOTALL)
_STR = r"(?:'([^']*)'|\"([^\"]*)\")"
# Directive words that open/close blocks (matched after @).
# Balanced-paren openers are scanned in ``_iter_tags``.
_TAG_RE = re.compile(
    rf"\{{\!\!\s*(.+?)\s*\!\!\}}"
    rf"|\{{\{{\s*(.+?)\s*\}}\}}"
    rf"|@extends\s*\(\s*{_STR}\s*\)"
    rf"|@yield\s*\(\s*{_STR}\s*(?:,\s*{_STR})?\s*\)"
    rf"|@section\s*\(\s*{_STR}\s*,\s*{_STR}\s*\)"
    rf"|@section\s*\(\s*{_STR}\s*\)"
    rf"|@endsection\b"
    rf"|@show\b"
    rf"|@component\b"
    rf"|@endcomponent\b"
    rf"|@slot\s*\(\s*{_STR}\s*\)"
    rf"|@endslot\b"
    rf"|@elseif\b"
    rf"|@else\b"
    rf"|@endif\b"
    rf"|@if\b"
    rf"|@endunless\b"
    rf"|@unless\b"
    rf"|@endforelse\b"
    rf"|@forelse\b"
    rf"|@endforeach\b"
    rf"|@foreach\b"
    rf"|@endempty\b"
    rf"|@empty\b"
    rf"|@endfor\b"
    rf"|@for\b"
    rf"|@endwhile\b"
    rf"|@while\b"
    rf"|@push\s*\(\s*{_STR}\s*\)"
    rf"|@endpush\b"
    rf"|@prepend\s*\(\s*{_STR}\s*\)"
    rf"|@endprepend\b"
    rf"|@stack\s*\(\s*{_STR}\s*\)"
    rf"|@once\b"
    rf"|@endonce\b"
    rf"|@parent\b"
    rf"|@lang\b"
    rf"|@choice\b"
    rf"|@props\b"
    rf"|@aware\b"
    rf"|@python\b"
    rf"|@endpython\b"
    rf"|@includeUnless\b"
    rf"|@includeWhen\b"
    rf"|@includeIf\b"
    rf"|@include\b"
    rf"|@each\b"
    rf"|@endisset\b"
    rf"|@isset\b"
    rf"|@csrf\b"
    rf"|@enderror\b"
    rf"|@error\b"
    rf"|@endauth\b"
    rf"|@auth\b"
    rf"|@endguest\b"
    rf"|@guest\b"
    rf"|@endcannotany\b"
    rf"|@cannotany\b"
    rf"|@endcanany\b"
    rf"|@canany\b"
    rf"|@endcannot\b"
    rf"|@cannot\b"
    rf"|@endcan\b"
    rf"|@can\b"
    rf"|@dump\b"
    rf"|@dd\b"
    rf"|@asset\b"
    rf"|@endcache\b"
    rf"|@cache\b",
    re.DOTALL,
)

# Always require balanced ``(...)`` when present as openers.
_BALANCED_ALWAYS = frozenset(
    {
        "@component",
        "@include",
        "@includeIf",
        "@includeWhen",
        "@includeUnless",
        "@each",
        "@isset",
        "@asset",
        "@cache",
        "@if",
        "@elseif",
        "@unless",
        "@for",
        "@while",
        "@foreach",
        "@forelse",
        "@lang",
        "@choice",
        "@props",
        "@aware",
        "@can",
        "@cannot",
        "@canany",
        "@cannotany",
    }
)
# Balanced only when the next non-space character is ``(``.
_BALANCED_IF_PAREN = frozenset({"@empty", "@csrf", "@error", "@dump", "@dd"})


class _TagMatch:
    """Minimal match object with balanced directive spans."""

    __slots__ = ("_source", "_start", "_end", "_re_match")

    def __init__(self, source: str, start: int, end: int, re_match: re.Match[str]) -> None:
        self._source = source
        self._start = start
        self._end = end
        self._re_match = re_match

    def start(self, group: int = 0) -> int:  # noqa: ARG002
        return self._start

    def end(self, group: int = 0) -> int:  # noqa: ARG002
        return self._end

    def group(self, idx: int | str = 0) -> str | None:
        if idx == 0:
            return self._source[self._start : self._end]
        return self._re_match.group(idx)  # pragma: no cover

    def groups(self) -> tuple[str | None, ...]:
        return self._re_match.groups()  # pragma: no cover


def _balanced_paren_end(source: str, open_paren: int) -> int:
    """Return index after the ``)`` matching ``source[open_paren] == '('``."""
    depth = 0
    in_str: str | None = None
    i = open_paren
    while i < len(source):
        ch = source[i]
        if in_str:
            if ch == "\\" and in_str != ")":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in {'"', "'"}:
            in_str = ch
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise SyntaxError("Unbalanced parentheses in Prism directive")


def _token_name(match: re.Match[str] | _TagMatch) -> str:
    """Return the leading ``@name`` / ``{{`` token without arguments."""
    raw = match.group(0) or ""
    if raw.startswith("{{") or raw.startswith("{!!"):
        return raw[:2] if raw.startswith("{{") else "{!!"
    m = re.match(r"(@\w+)", raw.lstrip())
    return m.group(1) if m else raw.lstrip()


def _iter_tags(
    source: str,
    pos: int = 0,
    *,
    extra_balanced: set[str] | None = None,
):
    """Yield tag matches; balanced-paren openers include full ``(...)`` spans."""
    extra = {t if t.startswith("@") else f"@{t}" for t in (extra_balanced or set())}
    extra_re: re.Pattern[str] | None = None
    if extra:
        names = sorted((t[1:] for t in extra), key=len, reverse=True)
        extra_re = re.compile("|".join(rf"@{re.escape(n)}\b" for n in names))

    while pos < len(source):
        match = _TAG_RE.search(source, pos)
        extra_match = extra_re.search(source, pos) if extra_re else None
        if match is None and extra_match is None:
            return
        if match is None:
            chosen: re.Match[str] | None = extra_match
        elif extra_match is None:
            chosen = match
        else:
            chosen = match if match.start() <= extra_match.start() else extra_match
        assert chosen is not None

        token = _token_name(chosen)
        need_balanced = token in _BALANCED_ALWAYS
        # Custom directives and optional-arg tags only balance when ``(`` follows.
        if token in _BALANCED_IF_PAREN or token in extra:
            rest = source[chosen.end() :]
            if rest.lstrip().startswith("("):
                need_balanced = True

        if need_balanced:
            rest = source[chosen.end() :]
            stripped = rest.lstrip()
            if not stripped.startswith("("):
                if token == "@component":
                    raise SyntaxError("@component requires (name, attrs) arguments")
                raise SyntaxError(f"{token} requires (...) arguments")
            open_at = chosen.end() + (len(rest) - len(stripped))
            end = _balanced_paren_end(source, open_at)
            yield _TagMatch(source, chosen.start(), end, chosen)
            pos = end
        else:
            if isinstance(chosen, re.Match) and chosen is match and match is not None:
                yield match
                pos = match.end()
            else:
                yield _TagMatch(source, chosen.start(), chosen.end(), chosen)
                pos = chosen.end()


def _py_str(value: str) -> str:
    return repr(value)


def compile_template(
    source: str,
    *,
    name: str = "<prism>",
    directives: dict[str, DirectiveHandler] | None = None,
) -> RenderFn:
    """Compile template source into ``render(context, engine) -> str``."""
    from almasix.prism.xtags import expand_x_tags

    source = _COMMENT_RE.sub("", source)
    source = expand_x_tags(source)
    dirs = directives or {}
    parent, sections, body = _split_extends(source, directives=dirs)
    if parent is not None:
        return _compile_child(parent, sections, name=name, directives=dirs)
    return _compile_fragment(body, name=name, directives=dirs)


def _split_extends(
    source: str,
    *,
    directives: dict[str, DirectiveHandler] | None = None,
) -> tuple[str | None, dict[str, str], str]:
    """Return ``(parent, sections, remainder)`` for an extending template."""
    dirs = directives or {}
    extra = {f"@{k}" for k in dirs}
    parent: str | None = None
    sections: dict[str, str] = {}
    pos = 0
    body_parts: list[str] = []
    stack: list[tuple[str, int]] = []

    for match in _iter_tags(source, extra_balanced=extra):
        start, end = match.start(), match.end()
        text = source[pos:start]
        if not stack:
            body_parts.append(text)
        pos = end
        kind = _tag_kind(match, directives=dirs)

        if kind == "extends":
            if stack:
                raise SyntaxError("@extends must be at the top level")
            parent = _extends_name(match)
            continue

        if kind == "section_inline":
            if stack:
                raise SyntaxError("inline @section cannot nest")
            sec_name, sec_value = _section_inline_args(match)
            sections[sec_name] = sec_value
            continue

        if kind == "section_open":
            stack.append((_section_open_name(match), start))
            continue

        if kind in {"endsection", "show"}:
            if not stack:
                raise SyntaxError(f"Unexpected @{kind}")
            sec_name, sec_start = stack.pop()
            open_match = next(
                m
                for m in _iter_tags(source, sec_start, extra_balanced=extra)
                if m.start() == sec_start
            )
            content = source[open_match.end() : start]
            if stack:
                raise SyntaxError("Nested @section is not supported yet")
            sections[sec_name] = content
            continue

        if stack:
            continue

        body_parts.append(match.group(0))

    if stack:
        raise SyntaxError(f"Unclosed @section('{stack[-1][0]}')")

    body_parts.append(source[pos:])
    body = "".join(body_parts)
    if parent is not None:
        if not sections and body.strip():
            sections["content"] = body
        return parent, sections, ""
    return None, sections, body


def _tag_kind(
    match: re.Match[str] | _TagMatch,
    *,
    directives: dict[str, DirectiveHandler] | None = None,
) -> str:
    token = (match.group(0) or "").lstrip()
    mapping = (
        ("{!!", "raw"),
        ("{{", "echo"),
        ("@extends", "extends"),
        ("@includeUnless", "includeUnless"),
        ("@includeWhen", "includeWhen"),
        ("@includeIf", "includeIf"),
        ("@include", "include"),
        ("@each", "each"),
        ("@yield", "yield"),
        ("@endcomponent", "endcomponent"),
        ("@component", "component"),
        ("@endslot", "endslot"),
        ("@slot", "slot"),
        ("@elseif", "elseif"),
        ("@else", "else"),
        ("@endif", "endif"),
        ("@if", "if"),
        ("@unless", "unless"),
        ("@endunless", "endunless"),
        ("@forelse", "forelse"),
        ("@foreach", "foreach"),
        ("@endempty", "endempty"),
        ("@empty", None),  # empty vs empty_var
        ("@endforelse", "endforelse"),
        ("@endforeach", "endforeach"),
        ("@for", "for"),
        ("@endfor", "endfor"),
        ("@while", "while"),
        ("@endwhile", "endwhile"),
        ("@endpush", "endpush"),
        ("@push", "push"),
        ("@endprepend", "endprepend"),
        ("@prepend", "prepend"),
        ("@stack", "stack"),
        ("@endonce", "endonce"),
        ("@once", "once"),
        ("@parent", "parent"),
        ("@lang", "lang"),
        ("@choice", "choice"),
        ("@props", "props"),
        ("@aware", "aware"),
        ("@python", "python"),
        ("@endpython", "endpython"),
        ("@endisset", "endisset"),
        ("@isset", "isset"),
        ("@csrf", "csrf"),
        ("@enderror", "enderror"),
        ("@error", "error"),
        ("@endauth", "endauth"),
        ("@auth", "auth"),
        ("@endguest", "endguest"),
        ("@guest", "guest"),
        ("@endcannotany", "endcannotany"),
        ("@cannotany", "cannotany"),
        ("@endcanany", "endcanany"),
        ("@canany", "canany"),
        ("@endcannot", "endcannot"),
        ("@cannot", "cannot"),
        ("@endcan", "endcan"),
        ("@can", "can"),
        ("@dump", "dump"),
        ("@dd", "dd"),
        ("@asset", "asset"),
        ("@endcache", "endcache"),
        ("@cache", "cache"),
        ("@endsection", "endsection"),
        ("@show", "show"),
        ("@section", None),
    )
    for prefix, kind in mapping:
        if token.startswith(prefix):
            if kind is not None:
                return kind
            if prefix == "@empty":
                return "empty_var" if "(" in token else "empty"
            head = token.split(")", 1)[0]
            return "section_inline" if "," in head else "section_open"
    name = _token_name(match)
    dir_name = name[1:] if name.startswith("@") else name
    if directives and dir_name in directives:
        return "custom"
    raise SyntaxError(f"Unknown Prism tag: {match.group(0)!r}")


def _section_inline_args(match: re.Match[str] | _TagMatch) -> tuple[str, str]:
    m = re.search(
        r"@section\s*\(\s*(?:'([^']*)'|\"([^\"]*)\")\s*,\s*(?:'([^']*)'|\"([^\"]*)\")\s*\)",
        match.group(0) or "",
    )
    assert m is not None
    name = m.group(1) if m.group(1) is not None else m.group(2)
    value = m.group(3) if m.group(3) is not None else m.group(4)
    return name, value or ""


def _section_open_name(match: re.Match[str] | _TagMatch) -> str:
    m = re.search(r"@section\s*\(\s*(?:'([^']*)'|\"([^\"]*)\")\s*\)", match.group(0) or "")
    assert m is not None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _extends_name(match: re.Match[str] | _TagMatch) -> str:
    m = re.search(r"@extends\s*\(\s*(?:'([^']*)'|\"([^\"]*)\")\s*\)", match.group(0) or "")
    assert m is not None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _compile_child(
    parent: str,
    sections: dict[str, str],
    *,
    name: str,
    directives: dict[str, DirectiveHandler] | None = None,
) -> RenderFn:
    dirs = directives or {}
    compiled_sections = {
        sec_name: _compile_fragment(
            sec_body, name=f"{name}#{sec_name}", section_name=sec_name, directives=dirs
        )
        for sec_name, sec_body in sections.items()
    }

    def render(context: dict[str, Any], engine: Any) -> str:
        # Sections from a further child override this level; @parent sees this level.
        incoming = dict(context.get("__sections") or {})
        bag: dict[str, Any] = {}
        for key, fn in compiled_sections.items():
            if key in incoming:
                override = incoming[key]

                def _make(override=override, base_fn=fn, key=key):
                    def _call(ctx: dict[str, Any], eng: Any) -> str:
                        parents = dict(ctx.get("__parent_sections") or {})
                        parents[key] = base_fn(ctx, eng)
                        child_ctx = {**ctx, "__parent_sections": parents}
                        if callable(override):
                            try:
                                return override(child_ctx, eng)
                            except TypeError:
                                return override()
                        return str(override)
                    return _call

                bag[key] = _make()
            else:
                bag[key] = fn
        for key, value in incoming.items():
            bag.setdefault(key, value)
        child_ctx = {**context, "__sections": bag}
        return engine.render(parent, child_ctx)

    render.__name__ = f"cal_child_{_safe_name(name)}"
    render.__qualname__ = render.__name__
    return render


def _compile_fragment(
    source: str,
    *,
    name: str,
    section_name: str | None = None,
    directives: dict[str, DirectiveHandler] | None = None,
) -> RenderFn:
    """Compile a fragment (no @extends) to a render function."""
    dirs = directives or {}
    extra = {f"@{k}" for k in dirs}
    closures: dict[str, RenderFn] = {}
    code_lines = [
        "def render(context, engine):",
        "    from almasix.prism.escape import e as __e",
        "    from almasix.prism.loop import Loop as __Loop",
        "    from almasix.translation import __, trans_choice",
        "    __b = []",
        "    __w = __b.append",
        "    from almasix.auth.access.helpers import gate_allows as __gate_allows, gate_any as __gate_any",
        "    __ns = dict(context)",
        "    __ns['__gate_allows'] = __gate_allows",
        "    __ns['__gate_any'] = __gate_any",
        "    def __sync():",
        "        __ns.update(context)",
        "        context.update({k: v for k, v in __ns.items() if not str(k).startswith('__')})",
        "    def __eval(__expr):",
        "        __sync()",
        "        return eval(__expr, {'__builtins__': {}}, __ns)",
        "    def __exec(__src):",
        "        __sync()",
        "        exec(__src, {'__builtins__': {}}, __ns)",
        "        context.update({k: v for k, v in __ns.items() if not str(k).startswith('__')})",
        "    def __yield(__name, __default=''):",
        "        __sections = context.get('__sections') or {}",
        "        __sec = __sections.get(__name)",
        "        if callable(__sec):",
        "            try:",
        "                return __sec(context, engine)",
        "            except TypeError:",
        "                return __sec()",
        "        if __sec is None:",
        "            return __default",
        "        return str(__sec)",
        "    def __include(__name, __data=None):",
        "        child = dict(context)",
        "        if __data:",
        "            child.update(dict(__data))",
        "        return engine.render(__name, child)",
        "    __stacks = context.get('__stacks')",
        "    if __stacks is None:",
        "        from almasix.prism.stacks import StackBag",
        "        __stacks = StackBag()",
        "        context['__stacks'] = __stacks",
    ]

    indent = 1
    python_mode = False
    python_buf: list[str] = []
    matches = list(_iter_tags(source, extra_balanced=extra))
    i = 0
    pos = 0

    def emit(line: str) -> None:
        code_lines.append(("    " * indent) + line)

    def emit_text(text: str) -> None:
        nonlocal python_mode
        if not text:
            return
        if python_mode:
            python_buf.append(text)
        else:
            emit(f"__w({_py_str(text)})")

    def emit_code(code: str) -> None:
        for line in code.splitlines():
            emit(line)

    while i < len(matches):
        match = matches[i]
        emit_text(source[pos : match.start()])
        pos = match.end()
        kind = _tag_kind(match, directives=dirs)

        if python_mode:
            if kind == "endpython":
                body = "".join(python_buf)
                emit(f"__exec({_py_str(_dedent_python(body))})")
                python_buf.clear()
                python_mode = False
            else:
                python_buf.append(match.group(0) or "")
            i += 1
            continue

        if kind == "component":
            depth = 1
            j = i + 1
            while j < len(matches) and depth:
                k = _tag_kind(matches[j], directives=dirs)
                if k == "component":
                    depth += 1
                elif k == "endcomponent":
                    depth -= 1
                j += 1
            if depth:
                raise SyntaxError("Unclosed @component")
            end_match = matches[j - 1]
            body = source[match.end() : end_match.start()]
            comp_name, attrs_expr = _component_args(match)
            default_body, named = _split_slots(body, directives=dirs)
            default_key = f"__slot_{len(closures)}"
            closures[default_key] = _compile_fragment(
                default_body, name=f"{name}#{comp_name}#slot", directives=dirs
            )
            named_keys: dict[str, str] = {}
            for slot_name, slot_body in named.items():
                key = f"__slot_{len(closures)}"
                closures[key] = _compile_fragment(
                    slot_body, name=f"{name}#{comp_name}#{slot_name}", directives=dirs
                )
                named_keys[slot_name] = key
            named_literal = (
                "{"
                + ", ".join(
                    f"{_py_str(k)}: (lambda __f={v}, __c=None: __f("
                    f"__c if __c is not None else context, engine))"
                    for k, v in named_keys.items()
                )
                + "}"
            )
            emit(
                f"__w(engine.render_component({_py_str(comp_name)}, context, "
                f"(lambda __c=None: {default_key}("
                f"__c if __c is not None else context, engine)), {named_literal}, "
                f"dict(__eval({_py_str(attrs_expr)}))))"
            )
            pos = end_match.end()
            i = j
            continue

        if kind in {"push", "prepend", "once"}:
            close = {"push": "endpush", "prepend": "endprepend", "once": "endonce"}[kind]
            depth = 1
            j = i + 1
            while j < len(matches) and depth:
                k = _tag_kind(matches[j], directives=dirs)
                if k == kind:
                    depth += 1
                elif k == close:
                    depth -= 1
                j += 1
            if depth:
                raise SyntaxError(f"Unclosed @{kind}")
            end_match = matches[j - 1]
            body = source[match.end() : end_match.start()]
            body_key = f"__slot_{len(closures)}"
            closures[body_key] = _compile_fragment(
                body, name=f"{name}#{kind}", directives=dirs
            )
            if kind == "once":
                once_key = f"{name}:once:{len(closures)}"
                emit(f"if __stacks.once({_py_str(once_key)}):")
                indent += 1
                emit(f"__w({body_key}(context, engine))")
                indent -= 1
            else:
                stack_name = _str_arg(match, kind)
                prepend = "True" if kind == "prepend" else "False"
                emit(
                    f"__stacks.push({_py_str(stack_name)}, {body_key}(context, engine), "
                    f"prepend={prepend})"
                )
            pos = end_match.end()
            i = j
            continue

        if kind == "cache":
            depth = 1
            j = i + 1
            while j < len(matches) and depth:
                k = _tag_kind(matches[j], directives=dirs)
                if k == "cache":
                    depth += 1
                elif k == "endcache":
                    depth -= 1
                j += 1
            if depth:
                raise SyntaxError("Unclosed @cache")
            end_match = matches[j - 1]
            body = source[match.end() : end_match.start()]
            body_key = f"__slot_{len(closures)}"
            closures[body_key] = _compile_fragment(
                body, name=f"{name}#cache", directives=dirs
            )
            key_expr = _paren_inner(match.group(0) or "")
            emit(
                f"__w(engine.remember_fragment(str(__eval({_py_str(key_expr)})), "
                f"lambda: {body_key}(context, engine)))"
            )
            pos = end_match.end()
            i = j
            continue

        if kind == "raw":
            emit(f"__w(str(__eval({_py_str(match.group(1).strip())})))")
        elif kind == "echo":
            emit(f"__w(__e(__eval({_py_str(match.group(2).strip())})))")
        elif kind == "include":
            view, data = _include_args(match)
            data_arg = data if data else "None"
            emit(f"__w(__include({_py_str(view)}, {data_arg}))")
        elif kind == "includeIf":
            view, data = _include_args(match, directive="includeIf")
            data_arg = data if data else "None"
            emit(f"if engine.exists({_py_str(view)}):")
            indent += 1
            emit(f"__w(__include({_py_str(view)}, {data_arg}))")
            indent -= 1
        elif kind == "includeWhen":
            cond, view, data = _include_cond_args(match, "includeWhen")
            data_arg = data if data else "None"
            emit(f"if __eval({_py_str(cond)}):")
            indent += 1
            emit(f"__w(__include({_py_str(view)}, {data_arg}))")
            indent -= 1
        elif kind == "includeUnless":
            cond, view, data = _include_cond_args(match, "includeUnless")
            data_arg = data if data else "None"
            emit(f"if not __eval({_py_str(cond)}):")
            indent += 1
            emit(f"__w(__include({_py_str(view)}, {data_arg}))")
            indent -= 1
        elif kind == "each":
            view, items_expr, item_name, empty_view = _each_args(match)
            emit(f"__each_items = list(__eval({_py_str(items_expr)}))")
            emit("if __each_items:")
            indent += 1
            emit("for __each_item in __each_items:")
            indent += 1
            emit(f"__w(__include({_py_str(view)}, {{{_py_str(item_name)}: __each_item}}))")
            indent -= 2
            if empty_view is not None:
                emit("else:")
                indent += 1
                emit(f"__w(__include({_py_str(empty_view)}))")
                indent -= 1
        elif kind == "yield":
            yname, default = _yield_args(match)
            emit(f"__w(str(__yield({_py_str(yname)}, {_py_str(default)})))")
        elif kind == "if":
            cond = _directive_expr(match, r"@if\s*\((.+)\)")
            emit(f"if __eval({_py_str(cond)}):")
            indent += 1
        elif kind == "elseif":
            cond = _directive_expr(match, r"@elseif\s*\((.+)\)")
            indent -= 1
            emit(f"elif __eval({_py_str(cond)}):")
            indent += 1
        elif kind == "else":
            indent -= 1
            emit("else:")
            indent += 1
        elif kind == "endif":
            indent -= 1
        elif kind == "unless":
            cond = _directive_expr(match, r"@unless\s*\((.+)\)")
            emit(f"if not __eval({_py_str(cond)}):")
            indent += 1
        elif kind == "endunless":
            indent -= 1
        elif kind == "isset":
            expr = _paren_inner(match.group(0) or "")
            emit(f"if __eval({_py_str(expr)}) is not None:")
            indent += 1
        elif kind == "endisset":
            indent -= 1
        elif kind == "empty_var":
            expr = _paren_inner(match.group(0) or "")
            emit(f"if not __eval({_py_str(expr)}):")
            indent += 1
        elif kind == "endempty":
            indent -= 1
        elif kind == "foreach":
            iterable, var = _foreach_args(match, "foreach")
            emit("__parent_loop = __ns.get('loop')")
            emit(f"__loop = __Loop(__eval({_py_str(iterable)}), __parent_loop)")
            emit("__ns['loop'] = __loop")
            emit(f"for {var} in __loop:")
            indent += 1
            emit(f"__ns[{_py_str(var)}] = {var}")
            emit("context['loop'] = __loop")
            emit(f"context[{_py_str(var)}] = {var}")
        elif kind == "endforeach":
            indent -= 1
            emit("__ns['loop'] = __parent_loop")
            emit("context['loop'] = __parent_loop")
        elif kind == "forelse":
            iterable, var = _foreach_args(match, "forelse")
            emit(f"__fe_items = list(__eval({_py_str(iterable)}))")
            emit("if __fe_items:")
            indent += 1
            emit("__parent_loop = __ns.get('loop')")
            emit("__loop = __Loop(__fe_items, __parent_loop)")
            emit("__ns['loop'] = __loop")
            emit(f"for {var} in __loop:")
            indent += 1
            emit(f"__ns[{_py_str(var)}] = {var}")
            emit("context['loop'] = __loop")
            emit(f"context[{_py_str(var)}] = {var}")
        elif kind == "empty":
            indent -= 2
            emit("else:")
            indent += 1
        elif kind == "endforelse":
            indent -= 1
            emit("__ns['loop'] = locals().get('__parent_loop')")
            emit("context['loop'] = __ns.get('loop')")
        elif kind == "for":
            header = _directive_expr(match, r"@for\s*\((.+)\)")
            emit(f"for {header}:")
            indent += 1
            emit(
                "__ns.update({k: v for k, v in locals().items() "
                "if isinstance(k, str) and not k.startswith('_') "
                "and k not in ('context', 'engine')})"
            )
            emit(
                "context.update({k: __ns[k] for k in list(__ns) "
                "if not str(k).startswith('__')})"
            )
        elif kind == "endfor":
            indent -= 1
        elif kind == "while":
            cond = _directive_expr(match, r"@while\s*\((.+)\)")
            emit(f"while __eval({_py_str(cond)}):")
            indent += 1
            emit(
                "__ns.update({k: v for k, v in locals().items() "
                "if isinstance(k, str) and not k.startswith('_') "
                "and k not in ('context', 'engine')})"
            )
            emit(
                "context.update({k: __ns[k] for k in list(__ns) "
                "if not str(k).startswith('__')})"
            )
        elif kind == "endwhile":
            indent -= 1
        elif kind == "stack":
            emit(f"__w(__stacks.render({_py_str(_str_arg(match, 'stack'))}))")
        elif kind == "parent":
            sec = section_name or ""
            emit(
                "__w(str((context.get('__parent_sections') or {}).get("
                + _py_str(sec)
                + ", '')))"
            )
        elif kind == "lang":
            args = _directive_expr(match, r"@lang\s*\((.+)\)")
            emit(f"__w(__e(str(__({args}))))")
        elif kind == "choice":
            args = _directive_expr(match, r"@choice\s*\((.+)\)")
            emit(f"__w(__e(str(trans_choice({args}))))")
        elif kind == "csrf":
            emit(
                "__w('<input type=\"hidden\" name=\"_token\" value=\"' + "
                "__e(str(context.get('csrf_token') or '')) + '\">')"
            )
        elif kind == "error":
            field = _str_arg(match, "error")
            emit(
                f"if context.get('errors') and {_py_str(field)} in "
                f"(context.get('errors') or {{}}):"
            )
            indent += 1
            emit(f"__err = context['errors'][{_py_str(field)}]")
            emit(
                "message = (__err[0] if isinstance(__err, (list, tuple)) "
                "and __err else str(__err))"
            )
            emit("__ns['message'] = message")
            emit("context['message'] = message")
        elif kind == "enderror":
            indent -= 1
        elif kind == "auth":
            emit("if context.get('auth_user') or context.get('__authenticated'):")
            indent += 1
        elif kind == "endauth":
            indent -= 1
        elif kind == "guest":
            emit("if not (context.get('auth_user') or context.get('__authenticated')):")
            indent += 1
        elif kind == "endguest":
            indent -= 1
        elif kind == "can":
            args = _directive_expr(match, r"@can\s*\((.+)\)")
            emit(f"if __eval({_py_str(f'__gate_allows({args})')}):")
            indent += 1
        elif kind == "endcan":
            indent -= 1
        elif kind == "cannot":
            args = _directive_expr(match, r"@cannot\s*\((.+)\)")
            emit(f"if not __eval({_py_str(f'__gate_allows({args})')}):")
            indent += 1
        elif kind == "endcannot":
            indent -= 1
        elif kind == "canany":
            args = _directive_expr(match, r"@canany\s*\((.+)\)")
            emit(f"if __eval({_py_str(f'__gate_any({args})')}):")
            indent += 1
        elif kind == "endcanany":
            indent -= 1
        elif kind == "cannotany":
            args = _directive_expr(match, r"@cannotany\s*\((.+)\)")
            emit(f"if not __eval({_py_str(f'__gate_any({args})')}):")
            indent += 1
        elif kind == "endcannotany":
            indent -= 1
        elif kind == "dump":
            args = _paren_inner(match.group(0) or "")
            emit("from almasix.debug import render_dump_html as __dump_html")
            if args.strip():
                emit(f"__dump_raw = __eval({_py_str(f'({args})')})")
                emit(
                    "__dump_vals = __dump_raw if isinstance(__dump_raw, tuple) "
                    "else (__dump_raw,)"
                )
            else:
                emit("__dump_vals = ()")
            emit(f"__w(__dump_html(__dump_vals, source={_py_str(name)}))")
        elif kind == "dd":
            args = _paren_inner(match.group(0) or "")
            emit("from almasix.debug import dd as __almasix_dd")
            if args.strip():
                emit(f"__dd_raw = __eval({_py_str(f'({args})')})")
                emit(
                    "__dd_vals = __dd_raw if isinstance(__dd_raw, tuple) "
                    "else (__dd_raw,)"
                )
                emit("__almasix_dd(*__dd_vals)")
            else:
                emit("__almasix_dd()")
        elif kind == "asset":
            args = _paren_inner(match.group(0) or "")
            emit(f"__w(__e(str(__eval({_py_str(f'asset({args})')}))))")
        elif kind == "props":
            args = _directive_expr(match, r"@props\s*\((.+)\)")
            emit(f"__prop_defaults = {args}")
            emit("from almasix.prism.attributes import AttributeBag as __AB")
            emit("__attr_bag = context.get('attributes') or __AB()")
            emit("for __pk, __pv in dict(__prop_defaults).items():")
            indent += 1
            emit("__val = __attr_bag.get(__pk, __pv)")
            emit("context[__pk] = __val")
            emit("__ns[__pk] = __val")
            emit("context.setdefault('__component_data', {})[__pk] = __val")
            emit("context.setdefault('__passed_attrs', set()).add(__pk)")
            indent -= 1
            emit("context['attributes'] = __attr_bag.except_(*dict(__prop_defaults).keys())")
            emit("__ns['attributes'] = context['attributes']")
        elif kind == "aware":
            args = _directive_expr(match, r"@aware\s*\((.+)\)")
            emit(f"__aware_spec = {args}")
            emit("__aware_parent = context.get('__aware_parent') or {}")
            emit("__passed = context.get('__passed_attrs') or set()")
            emit("if isinstance(__aware_spec, dict):")
            indent += 1
            emit("__aware_items = list(__aware_spec.items())")
            indent -= 1
            emit("else:")
            indent += 1
            emit("__aware_items = [(__k, __k) for __k in list(__aware_spec)]")
            indent -= 1
            emit("for __child_key, __parent_key in __aware_items:")
            indent += 1
            emit("if __child_key in __passed:")
            indent += 1
            emit("continue")
            indent -= 1
            emit("if __parent_key in __aware_parent:")
            indent += 1
            emit("__val = __aware_parent[__parent_key]")
            emit("context[__child_key] = __val")
            emit("__ns[__child_key] = __val")
            emit("context.setdefault('__component_data', {})[__child_key] = __val")
            indent -= 1
            indent -= 1
        elif kind == "custom":
            dir_name = _token_name(match)[1:]
            expr = _paren_inner(match.group(0) or "")
            emit_code(dirs[dir_name](expr))
        elif kind == "python":
            python_mode = True
            python_buf.clear()
        elif kind in {
            "extends", "section_inline", "section_open", "endsection", "show",
            "slot", "endslot", "endcomponent",
            "endpush", "endprepend", "endonce", "endcache",
        }:
            raise SyntaxError(f"Unexpected @{kind} in this position")
        else:
            raise SyntaxError(f"Unhandled Prism tag: {match.group(0)!r}")  # pragma: no cover
        i += 1

    emit_text(source[pos:])
    if python_mode:
        raise SyntaxError("Unclosed @python block")
    if indent != 1:
        raise SyntaxError("Unbalanced control structures in Prism template")
    code_lines.append("    return ''.join(__b)")

    local: dict[str, Any] = dict(closures)
    try:
        exec(compile("\n".join(code_lines), name, "exec"), local, local)
    except SyntaxError as exc:  # pragma: no cover
        raise SyntaxError(f"Failed to compile Prism template {name}: {exc}") from exc
    render = local["render"]
    render.__name__ = f"cal_{_safe_name(name)}"
    render.__qualname__ = render.__name__
    return render


def _split_slots(
    body: str,
    *,
    directives: dict[str, DirectiveHandler] | None = None,
) -> tuple[str, dict[str, str]]:
    """Split a component body into default slot content and named slots."""
    dirs = directives or {}
    extra = {f"@{k}" for k in dirs}
    named: dict[str, str] = {}
    parts: list[str] = []
    pos = 0
    for match in _iter_tags(body, extra_balanced=extra):
        # Nested @slot opens are consumed by the depth scan below; skip them.
        if match.start() < pos:
            continue
        kind = _tag_kind(match, directives=dirs)
        if kind != "slot":
            continue
        parts.append(body[pos : match.start()])
        slot_name = _slot_name(match)
        depth = 1
        end = None
        for inner in _iter_tags(body, match.end(), extra_balanced=extra):
            ik = _tag_kind(inner, directives=dirs)
            if ik == "slot":
                depth += 1
            elif ik == "endslot":
                depth -= 1
                if depth == 0:
                    end = inner
                    break
        if end is None:
            raise SyntaxError(f"Unclosed @slot('{slot_name}')")
        named[slot_name] = body[match.end() : end.start()]
        pos = end.end()
    parts.append(body[pos:])
    return "".join(parts), named


def _slot_name(match: re.Match[str] | _TagMatch) -> str:
    m = re.search(r"@slot\s*\(\s*(?:'([^']*)'|\"([^\"]*)\")\s*\)", match.group(0) or "")
    assert m is not None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _component_args(match: re.Match[str] | _TagMatch) -> tuple[str, str]:
    inner = _paren_inner(match.group(0) or "")
    m = re.match(r"(?:'([^']+)'|\"([^\"]+)\")\s*(?:,\s*(.+))?$", inner.strip(), re.DOTALL)
    if not m:
        raise SyntaxError(f"Invalid @component args: {inner!r}")
    cname = m.group(1) if m.group(1) is not None else m.group(2)
    attrs_expr = (m.group(3) or "{}").strip()
    return cname, attrs_expr


def _dedent_python(body: str) -> str:
    lines = body.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return ""
    indents = [len(line) - len(line.lstrip(" ")) for line in lines if line.strip()]
    pad = min(indents) if indents else 0
    return "\n".join(line[pad:] if line.strip() else "" for line in lines)


def _directive_expr(match: re.Match[str] | _TagMatch, pattern: str) -> str:
    m = re.search(pattern, match.group(0) or "", re.DOTALL)
    assert m is not None
    return m.group(1).strip()


def _paren_inner(token: str) -> str:
    i = token.find("(")
    if i < 0:  # pragma: no cover
        return ""
    if not token.rstrip().endswith(")"):  # pragma: no cover
        return ""
    return token[i + 1 : token.rfind(")")].strip()


def _split_top_args(inner: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    in_str: str | None = None
    start = 0
    i = 0
    while i < len(inner):
        ch = inner[i]
        if in_str:
            if ch == "\\" and in_str != ")":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in {"'", '"'}:
            in_str = ch
            i += 1
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(inner[start:i].strip())
            start = i + 1
        i += 1
    parts.append(inner[start:].strip())
    return [p for p in parts if p != "" or len(parts) == 1]


def _parse_str_literal(value: str) -> str:
    s = value.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in {"'", '"'}:
        return s[1:-1]
    raise SyntaxError(f"Expected string literal, got {value!r}")


def _include_args(
    match: re.Match[str] | _TagMatch,
    *,
    directive: str = "include",
) -> tuple[str, str | None]:
    inner = _paren_inner(match.group(0) or "")
    parts = _split_top_args(inner)
    if not parts:  # pragma: no cover - _split_top_args always yields ≥1 part
        raise SyntaxError(f"@{directive} requires a view name")
    view = _parse_str_literal(parts[0])
    data = parts[1] if len(parts) > 1 else None
    return view, data


def _include_cond_args(
    match: re.Match[str] | _TagMatch,
    directive: str,
) -> tuple[str, str, str | None]:
    inner = _paren_inner(match.group(0) or "")
    parts = _split_top_args(inner)
    if len(parts) < 2:
        raise SyntaxError(f"@{directive} requires (cond, 'view')")
    cond = parts[0]
    view = _parse_str_literal(parts[1])
    data = parts[2] if len(parts) > 2 else None
    return cond, view, data


def _each_args(
    match: re.Match[str] | _TagMatch,
) -> tuple[str, str, str, str | None]:
    inner = _paren_inner(match.group(0) or "")
    parts = _split_top_args(inner)
    if len(parts) < 3:
        raise SyntaxError("@each requires ('view', items, 'item')")
    view = _parse_str_literal(parts[0])
    items = parts[1]
    item = _parse_str_literal(parts[2])
    empty = _parse_str_literal(parts[3]) if len(parts) > 3 else None
    return view, items, item, empty


def _foreach_args(match: re.Match[str] | _TagMatch, name: str) -> tuple[str, str]:
    m = re.search(rf"@{name}\s*\((.+?)\s+as\s+(\w+)\)", match.group(0) or "", re.DOTALL)
    assert m is not None
    return m.group(1).strip(), m.group(2)


def _yield_args(match: re.Match[str] | _TagMatch) -> tuple[str, str]:
    m = re.search(
        r"@yield\s*\(\s*(?:'([^']*)'|\"([^\"]*)\")\s*(?:,\s*(?:'([^']*)'|\"([^\"]*)\"))?\s*\)",
        match.group(0) or "",
    )
    assert m is not None
    name = m.group(1) if m.group(1) is not None else m.group(2)
    if m.group(3) is not None or m.group(4) is not None:
        default = m.group(3) if m.group(3) is not None else m.group(4)
    else:
        default = ""
    return name, default or ""


def _str_arg(match: re.Match[str] | _TagMatch, directive: str) -> str:
    m = re.search(
        rf"@{directive}\s*\(\s*(?:'([^']*)'|\"([^\"]*)\")\s*\)",
        match.group(0) or "",
    )
    assert m is not None
    return m.group(1) if m.group(1) is not None else m.group(2)


def _safe_name(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z_]+", "_", name)
