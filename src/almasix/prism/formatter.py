"""Format ``.prism.html`` sources (directive-aware, idempotent)."""

from __future__ import annotations

import re

_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

_OPEN_DIRECTIVES = frozenset(
    {
        "if",
        "unless",
        "isset",
        "empty",
        "for",
        "foreach",
        "forelse",
        "while",
        "section",
        "component",
        "slot",
        "push",
        "prepend",
        "once",
        "auth",
        "guest",
        "can",
        "canany",
        "cannot",
        "cannotany",
        "error",
        "cache",
        "python",
    }
)

_MID_DIRECTIVES = frozenset({"else", "elseif", "empty", "show"})

_CLOSE_DIRECTIVES = frozenset(
    {
        "endif",
        "endunless",
        "endisset",
        "endempty",
        "endfor",
        "endforeach",
        "endforelse",
        "endwhile",
        "endsection",
        "endcomponent",
        "endslot",
        "endpush",
        "endprepend",
        "endonce",
        "endauth",
        "endguest",
        "endcan",
        "endcanany",
        "endcannot",
        "endcannotany",
        "enderror",
        "endcache",
        "endpython",
    }
)

# ``@empty`` opens a block when it has args; as a bare mid-token inside
# ``@forelse`` it is treated as mid. Detected via presence of ``(``.
_DIRECTIVE_LINE = re.compile(r"^(\s*)@([A-Za-z_][\w]*)\b(.*)$")
_OPEN_TAG = re.compile(r"^(\s*)<([A-Za-z][\w:-]*)([^>]*)>\s*$")
_CLOSE_TAG = re.compile(r"^(\s*)</([A-Za-z][\w:-]*)\s*>\s*$")
_SELF_CLOSE = re.compile(r"/>\s*$")


def format_prism(source: str, *, indent_size: int = 4, line_length: int = 120) -> str:
    """Return a formatted Prism template.

    Line-based and directive-aware. Does not reindent content between
    ``@python`` and ``@endpython``. ``line_length`` is reserved for future
    attribute wrapping; simple cases leave long lines intact.
    """
    del line_length  # reserved API; keep signature stable for editors / CLI
    if indent_size < 1:
        raise ValueError("indent_size must be >= 1")

    lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Preserve a final newline decision from the source.
    had_trailing_newline = source.endswith("\n") or source.endswith("\r\n")
    if lines and lines[-1] == "" and had_trailing_newline:
        lines = lines[:-1]

    out: list[str] = []
    depth = 0
    in_python = False
    pad = " " * indent_size

    for raw in lines:
        if in_python:
            stripped = raw.lstrip()
            if stripped.startswith("@endpython"):
                in_python = False
                depth = max(0, depth - 1)
                out.append(f"{pad * depth}@endpython")
            else:
                # Preserve inner content exactly (including blank lines / tabs).
                out.append(raw)
            continue

        stripped = raw.strip()
        if stripped == "":
            out.append("")
            continue

        directive = _DIRECTIVE_LINE.match(stripped)
        if directive is not None:
            name = directive.group(2)
            rest = directive.group(3)
            rebuilt = f"@{name}{rest.rstrip()}"

            if name in _CLOSE_DIRECTIVES:
                depth = max(0, depth - 1)
                out.append(f"{pad * depth}{rebuilt}")
                continue

            if name == "empty" and not rest.lstrip().startswith("("):
                # mid-block inside @forelse
                depth = max(0, depth - 1)
                out.append(f"{pad * depth}{rebuilt}")
                depth += 1
                continue

            if name in _MID_DIRECTIVES and name != "empty":
                depth = max(0, depth - 1)
                out.append(f"{pad * depth}{rebuilt}")
                depth += 1
                continue

            if name == "empty" and rest.lstrip().startswith("("):
                out.append(f"{pad * depth}{rebuilt}")
                depth += 1
                continue

            if name in _OPEN_DIRECTIVES:
                out.append(f"{pad * depth}{rebuilt}")
                depth += 1
                if name == "python":
                    in_python = True
                continue

            # Standalone directives (@csrf, @yield, @stack, …)
            out.append(f"{pad * depth}{rebuilt}")
            continue

        close = _CLOSE_TAG.match(stripped)
        if close is not None:
            depth = max(0, depth - 1)
            out.append(f"{pad * depth}</{close.group(2)}>")
            continue

        open_tag = _OPEN_TAG.match(stripped)
        if open_tag is not None:
            tag = open_tag.group(2)
            attrs = open_tag.group(3)
            rebuilt = f"<{tag}{attrs}>"
            out.append(f"{pad * depth}{rebuilt}")
            if (
                tag.lower() not in _VOID_TAGS
                and not _SELF_CLOSE.search(attrs)
                and not attrs.rstrip().endswith("/")
            ):
                depth += 1
            continue

        # Plain text / mixed line — indent to current depth, keep inner spacing.
        out.append(f"{pad * depth}{stripped}")

    result = "\n".join(out)
    if had_trailing_newline or not source:
        result += "\n"
    elif source and not result.endswith("\n") and "\n" in source:
        # multi-line without trailing newline: keep that shape
        pass
    return result
