"""Framework-aware LSP feature logic (protocol-agnostic results)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

from almasix.lsp.analysis import (
    CallKind,
    CursorContext,
    StringCall,
    call_at,
    context_at,
    directive_at,
    find_calls,
    find_prism_calls,
    find_python_calls,
    prism_helper_call_at,
    template_var_at,
)
from almasix.lsp.directives import PRISM_DIRECTIVES, directive_hover, directive_snippet
from almasix.lsp.env_context import display_value
from almasix.lsp.index import (
    AppIndex,
    config_file_for_key,
    controller_methods,
    resolve_controller_action,
    resolve_controller_path,
    view_path_for_name,
)
from almasix.lsp.model_context import infer_model_name, known_model_names
from almasix.lsp.schema_context import resolve_table
from almasix.lsp.view_context import merge_vars_for_view, view_name_for_template
from almasix.prism.formatter import format_prism

# Directories never descended into while scanning for view references.
_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".idea",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "storage",
        "vendor",
        "website",
        "editors",
        "docs",
    }
)

# Relative roots under the app (or monorepo) that may contain view() / @include.
_REFERENCE_SCAN_DIRS = (
    "app",
    "routes",
    "resources/views",
    "database",
    "bootstrap",
    "tests",
)


@dataclass(frozen=True)
class CompletionItem:
    label: str
    kind: CallKind
    detail: str = ""
    #: Text inserted on accept; defaults to ``label`` when unset.
    insert_text: str | None = None
    #: ``plain`` or ``snippet`` (LSP InsertTextFormat).
    insert_text_format: str = "plain"
    #: Optional replace range; when set, clients must not guess from the token.
    start_line: int | None = None
    start_character: int | None = None
    end_line: int | None = None
    end_character: int | None = None
    filter_text: str | None = None


@dataclass(frozen=True)
class DiagnosticItem:
    message: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    severity: int = 1  # Error
    code: str | None = None


@dataclass(frozen=True)
class HoverItem:
    contents: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int


@dataclass(frozen=True)
class LocationItem:
    path: Path
    start_line: int = 0
    start_character: int = 0
    end_line: int = 0
    end_character: int = 0


@dataclass(frozen=True)
class DocumentLinkItem:
    target: Path
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    tooltip: str = ""


@dataclass(frozen=True)
class CodeActionItem:
    title: str
    kind: str
    view_name: str
    create_path: Path
    start_line: int
    start_character: int
    end_line: int
    end_character: int


def _filter_prefix(names: list[str], prefix: str) -> list[str]:
    if not prefix:
        return names
    lower = prefix.lower()
    return [name for name in names if name.lower().startswith(lower)]


def completions(
    index: AppIndex,
    source: str,
    line: int,
    character: int,
    *,
    language: str,
    uri_path: Path | None = None,
) -> list[CompletionItem]:
    """Suggest names for the call under the cursor."""
    ctx = context_at(source, line, character, language=language)
    if ctx is None:
        return []
    if ctx.kind == "attr":
        ctx = _resolve_attr_context(index, source, line, character, ctx)
        if ctx is None:
            return []
    return completions_for_context(index, ctx, uri_path=uri_path)


def _resolve_attr_context(
    index: AppIndex,
    source: str,
    line: int,
    character: int,
    ctx: CursorContext,
) -> CursorContext | None:
    """Attach the model/table hint for ``user.|`` once the index is available."""
    if not ctx.receiver:
        return None
    model = infer_model_name(
        source,
        _caret_offset(source, line, character),
        ctx.receiver,
        models=known_model_names(index.tables),
    )
    if model is None:
        return None
    return replace(ctx, table=model)


def _caret_offset(source: str, line: int, character: int) -> int:
    """Byte offset of ``(line, character)`` in ``source`` (best-effort)."""
    if line < 0:
        return 0
    start = 0
    for _ in range(line):
        nl = source.find("\n", start)
        if nl < 0:
            return len(source)
        start = nl + 1
    return min(start + max(character, 0), len(source))


def completions_for_context(
    index: AppIndex,
    ctx: CursorContext,
    *,
    uri_path: Path | None = None,
) -> list[CompletionItem]:
    if ctx.kind == "var":
        return _completions_for_var(index, ctx, uri_path=uri_path)
    if ctx.kind == "prism":
        # Explicit Ctrl+Space in plain markup: offer the whole Prism surface.
        items = [
            _directive_completion(name, ctx)
            for name in _filter_prefix(sorted(PRISM_DIRECTIVES), ctx.prefix.lstrip("@"))
        ]
        items.extend(_completions_for_var(index, ctx, uri_path=uri_path))
        return items
    if ctx.kind == "directive":
        names = _filter_prefix(sorted(PRISM_DIRECTIVES), ctx.prefix)
        return [_directive_completion(name, ctx) for name in names]
    if ctx.kind == "vite":
        names = _filter_prefix(sorted(index.vite_entries), ctx.prefix)
        return [
            _string_completion(
                name,
                "vite",
                ctx,
                detail=str(index.vite_entries[name]),
            )
            for name in names
        ]
    if ctx.kind in {"url", "asset"}:
        # Soft suggestions: common public paths + vite entries.
        candidates = sorted(
            {
                *index.vite_entries,
                "css/app.css",
                "js/app.js",
                "images/",
                "favicon.ico",
            }
        )
        names = _filter_prefix(candidates, ctx.prefix)
        return [_string_completion(name, ctx.kind, ctx) for name in names]
    if ctx.kind in {"view", "include", "extends"}:
        names = _filter_prefix(sorted(index.views), ctx.prefix)
        return [
            _string_completion(name, ctx.kind, ctx, detail=str(index.views[name])) for name in names
        ]
    if ctx.kind == "route":
        names = _filter_prefix(sorted(index.routes), ctx.prefix)
        return [
            _string_completion(
                name,
                "route",
                ctx,
                detail=f"{' '.join(index.routes[name].methods)} {index.routes[name].uri}",
            )
            for name in names
        ]
    if ctx.kind == "env":
        return _completions_for_env(index, ctx)
    if ctx.kind == "table":
        names = _filter_prefix(sorted(index.tables), ctx.prefix)
        return [
            _string_completion(
                name,
                "table",
                ctx,
                detail=index.tables[name].detail,
            )
            for name in names
        ]
    if ctx.kind == "column":
        return _completions_for_column(index, ctx)
    if ctx.kind == "attr":
        return _completions_for_attr(index, ctx)
    if ctx.kind == "config":
        names = _filter_prefix(list(index.config_keys), ctx.prefix)
        return [_string_completion(name, "config", ctx) for name in names]
    if ctx.kind == "trans":
        names = _filter_prefix(list(index.translation_keys), ctx.prefix)
        return [_string_completion(name, "trans", ctx) for name in names]
    if ctx.kind == "middleware":
        names = _filter_prefix(list(index.middleware_aliases), ctx.prefix)
        return [_string_completion(name, "middleware", ctx) for name in names]
    if ctx.kind == "action" and ctx.controller:
        path = resolve_controller_path(index, ctx.controller)
        if path is None:
            return []
        names = _filter_prefix(sorted(controller_methods(path)), ctx.prefix)
        return [
            _string_completion(
                name,
                "action",
                ctx,
                detail=f"{ctx.controller}.{name}",
            )
            for name in names
        ]
    return []


def format_document(
    source: str,
    *,
    language: str,
    uri_path: Path | None = None,
) -> str | None:
    """Return a fully formatted Prism document, or ``None`` when not applicable.

    Uses the same ``format_prism`` implementation as ``smith prism:format`` so
    Ctrl+Alt+L / format-on-save stay identical to the CLI.
    """
    lang = language.lower()
    is_prism = lang in {"prism", "prism-html"} or (
        uri_path is not None and uri_path.name.endswith(".prism.html")
    )
    if not is_prism:
        return None
    return format_prism(source)


def _directive_completion(name: str, ctx: CursorContext) -> CompletionItem:
    """``@if`` → snippet ``@if($1)…@endif``, replacing from the ``@`` onward.

    JetBrains treats ``@if`` as one token; without an explicit text-edit range
    the client replaces that whole token with a bare ``if`` and the sigil is lost.
    """
    return CompletionItem(
        label=f"@{name}",
        kind="directive",
        detail=PRISM_DIRECTIVES[name],
        insert_text=directive_snippet(name, indent=ctx.line_indent),
        insert_text_format="snippet",
        filter_text=f"@{name}",
        start_line=ctx.start_line,
        start_character=ctx.start_character,
        end_line=ctx.end_line,
        end_character=ctx.end_character,
    )


def _string_completion(
    name: str,
    kind: CallKind,
    ctx: CursorContext,
    *,
    detail: str = "",
) -> CompletionItem:
    """Route / view / vite string args with an explicit replace range.

    ``wrap_quotes`` means the replace range covers the call's ``(…)`` and the
    insert is ``('name')`` — not a zero-width ``'name'`` that some clients
    mis-apply against the surrounding ``{{ }}`` token.
    """
    insert = f"('{name}')" if ctx.wrap_quotes else name
    return CompletionItem(
        label=name,
        kind=kind,
        detail=detail,
        insert_text=insert,
        filter_text=name,
        start_line=ctx.start_line,
        start_character=ctx.start_character,
        end_line=ctx.end_line,
        end_character=ctx.end_character,
    )


def _completions_for_var(
    index: AppIndex,
    ctx: CursorContext,
    *,
    uri_path: Path | None,
) -> list[CompletionItem]:
    view_name = None
    if uri_path is not None:
        view_name = view_name_for_template(index.views, uri_path)
    merged = merge_vars_for_view(
        view_name,
        view_data=index.view_data,
        helpers=list(index.view_helpers),
        shared=index.view_shared,
    )
    names = _filter_prefix(sorted(merged), ctx.prefix)
    return [
        _string_completion(name, "var", ctx, detail=merged[name].detail) for name in names
    ]


def _completions_for_env(index: AppIndex, ctx: CursorContext) -> list[CompletionItem]:
    names = _filter_prefix(sorted(index.env_keys), ctx.prefix)
    items: list[CompletionItem] = []
    for name in names:
        info = index.env_keys[name]
        shown = display_value(name, info.value)
        detail = f"{info.detail} = {shown}" if shown else info.detail
        items.append(_string_completion(name, "env", ctx, detail=detail))
    return items


def _completions_for_column(index: AppIndex, ctx: CursorContext) -> list[CompletionItem]:
    """Columns of the table in context, or every column when it cannot be pinned down."""
    table = resolve_table(ctx.table, index.tables)
    if table is not None:
        info = index.tables[table]
        names = _filter_prefix(sorted(info.columns), ctx.prefix)
        return [
            _string_completion(name, "column", ctx, detail=info.columns[name].detail)
            for name in names
        ]

    seen: dict[str, str] = {}
    for info in index.tables.values():
        for name, column in info.columns.items():
            seen.setdefault(name, column.detail)
    names = _filter_prefix(sorted(seen), ctx.prefix)
    return [_string_completion(name, "column", ctx, detail=seen[name]) for name in names]


def _completions_for_attr(index: AppIndex, ctx: CursorContext) -> list[CompletionItem]:
    """Model instance attributes from the indexed schema (migrations + fillable)."""
    table = resolve_table(ctx.table, index.tables)
    if table is None:
        return []
    info = index.tables[table]
    names = _filter_prefix(sorted(info.columns), ctx.prefix)
    return [
        _string_completion(name, "attr", ctx, detail=info.columns[name].detail)
        for name in names
    ]


def diagnostics_python(index: AppIndex, source: str) -> list[DiagnosticItem]:
    """Unknown ``view("…")`` (and translation keys when ``lang/`` exists)."""
    items: list[DiagnosticItem] = []
    for call in find_calls(source, language="python"):
        if call.kind == "view":
            if call.value in index.views:
                continue
            items.append(
                DiagnosticItem(
                    message=f"Unknown view [{call.value}].",
                    start_line=call.start_line,
                    start_character=call.start_character,
                    end_line=call.end_line,
                    end_character=call.end_character,
                    code="unknown-view",
                )
            )
        elif call.kind == "trans" and index.has_lang:
            if call.value in index.translation_keys:
                continue
            items.append(
                DiagnosticItem(
                    message=f"Unknown translation key [{call.value}].",
                    start_line=call.start_line,
                    start_character=call.start_character,
                    end_line=call.end_line,
                    end_character=call.end_character,
                    code="unknown-trans",
                )
            )
    return items


def hover(
    index: AppIndex,
    source: str,
    line: int,
    character: int,
    *,
    language: str,
    uri_path: Path | None = None,
) -> HoverItem | None:
    """Hover for Prism directives, template vars, and known string-keyed helpers."""
    lang = language.lower()
    if lang in {"prism", "html", "prism-html"}:
        helper = prism_helper_call_at(source, line, character)
        if helper is not None:
            text = _hover_for_call(index, helper)
            if text is not None:
                return HoverItem(
                    contents=text,
                    start_line=helper.start_line,
                    start_character=helper.start_character,
                    end_line=helper.end_line,
                    end_character=helper.end_character,
                )
        var = template_var_at(source, line, character)
        if var is not None:
            info = _resolve_template_var(index, var.name, uri_path=uri_path)
            if info is not None:
                loc = f"\n\n`{info.path}:{info.line + 1}`" if info.path else ""
                return HoverItem(
                    contents=f"**{info.kind}** `{info.name}`\n\n{info.detail}{loc}",
                    start_line=var.start_line,
                    start_character=var.start_character,
                    end_line=var.end_line,
                    end_character=var.end_character,
                )
        name = directive_at(source, line, character)
        if name is not None:
            text = directive_hover(name)
            if text is not None:
                return HoverItem(
                    contents=text,
                    start_line=line,
                    start_character=max(0, character - len(name)),
                    end_line=line,
                    end_character=character + 1,
                )

    call = call_at(source, line, character, language=language)
    if call is None:
        return None
    text = _hover_for_call(index, call)
    if text is None:
        return None
    return HoverItem(
        contents=text,
        start_line=call.start_line,
        start_character=call.start_character,
        end_line=call.end_line,
        end_character=call.end_character,
    )


def _hover_for_call(index: AppIndex, call: StringCall) -> str | None:
    if call.kind in {"view", "include", "extends"}:
        path = index.views.get(call.value)
        if path is None:
            return f"**view** `{call.value}`\n\n_Not found in resources/views._"
        return f"**view** `{call.value}`\n\n`{path}`"
    if call.kind == "route":
        info = index.routes.get(call.value)
        if info is None:
            return f"**route** `{call.value}`\n\n_Unknown named route._"
        methods = " | ".join(info.methods)
        loc = f"\n\n`{info.path}:{info.line + 1}`" if info.path else ""
        return f"**route** `{call.value}`\n\n`{methods}` `{info.uri}`{loc}"
    if call.kind == "config":
        known = call.value in index.config_keys
        status = "indexed" if known else "not in config/*.py"
        path = config_file_for_key(index, call.value)
        extra = f"\n\n`{path}`" if path else ""
        return f"**config** `{call.value}`\n\n_{status}_{extra}"
    if call.kind == "trans":
        known = call.value in index.translation_keys
        status = "indexed" if known else "not in lang/"
        return f"**translation** `{call.value}`\n\n_{status}_"
    if call.kind == "middleware":
        known = call.value in index.middleware_aliases
        status = "alias" if known else "unknown alias"
        return f"**middleware** `{call.value}`\n\n_{status}_"
    if call.kind == "env":
        info = index.env_keys.get(call.value)
        if info is None:
            return (
                f"**env** `{call.value}`\n\n_Not in .env / .env.example and not read by config/._"
            )
        lines = [f"**env** `{call.value}`", info.detail]
        shown = display_value(call.value, info.value)
        if shown:
            lines.append(f"`{call.value}={shown}`")
        if info.used_by:
            lines.append("Read by " + ", ".join(f"`{origin}`" for origin in info.used_by[:5]))
        return "\n\n".join(lines)
    if call.kind == "table":
        table = index.tables.get(call.value)
        if table is None:
            return f"**table** `{call.value}`\n\n_No migration or model declares this table._"
        columns = ", ".join(f"`{name}`" for name in sorted(table.columns)[:12])
        loc = f"\n\n`{table.path}:{table.line + 1}`" if table.path else ""
        return f"**table** `{call.value}`\n\n{table.detail}\n\n{columns}{loc}"
    if call.kind == "column":
        column = _resolve_column(index, call.table, call.value)
        if column is None:
            return f"**column** `{call.value}`\n\n_Not found in the indexed schema._"
        loc = f"\n\n`{column.path}:{column.line + 1}`" if column.path else ""
        return f"**column** `{column.table}.{column.name}`\n\n{column.detail}{loc}"
    if call.kind == "vite":
        path = index.vite_entries.get(call.value)
        if path is None:
            return f"**vite** `{call.value}`\n\n_Entry not found in vite.config / resources/js._"
        return f"**vite** `{call.value}`\n\n`{path}`"
    if call.kind in {"url", "asset"}:
        return f"**{call.kind}** `{call.value}`"
    if call.kind == "action" and call.controller:
        resolved = resolve_controller_action(index, call.controller, call.value, source=None)
        if resolved is None:
            return (
                f"**action** `{call.controller}@{call.value}`\n\n"
                "_Controller not found under app/http/controllers._"
            )
        path, line = resolved
        return f"**action** `{call.controller}@{call.value}`\n\n`{path}:{line + 1}`"
    return None


def definition(
    index: AppIndex,
    source: str,
    line: int,
    character: int,
    *,
    language: str,
    uri_path: Path | None = None,
) -> LocationItem | None:
    """Go-to-definition for view / route / config / action / template variable."""
    lang = language.lower()
    if lang in {"prism", "html", "prism-html"}:
        helper = prism_helper_call_at(source, line, character)
        if helper is not None:
            loc = _definition_for_call(index, helper, source=source)
            if loc is not None:
                return loc
        var = template_var_at(source, line, character)
        if var is not None:
            info = _resolve_template_var(index, var.name, uri_path=uri_path)
            if info is not None and info.path is not None and info.path.is_file():
                return LocationItem(
                    path=info.path,
                    start_line=info.line,
                    end_line=info.line,
                )
    call = call_at(source, line, character, language=language)
    if call is None:
        return None
    return _definition_for_call(index, call, source=source)


def _definition_for_call(
    index: AppIndex,
    call: StringCall,
    *,
    source: str,
) -> LocationItem | None:
    if call.kind in {"view", "include", "extends"}:
        path = index.views.get(call.value)
        if path is None or not path.is_file():
            return None
        return LocationItem(path=path)
    if call.kind == "route":
        info = index.routes.get(call.value)
        if info is None or info.path is None or not info.path.is_file():
            return None
        return LocationItem(path=info.path, start_line=info.line, end_line=info.line)
    if call.kind == "config":
        path = config_file_for_key(index, call.value)
        if path is None or not path.is_file():
            return None
        return LocationItem(path=path)
    if call.kind == "env":
        info = index.env_keys.get(call.value)
        if info is None or info.path is None or not info.path.is_file():
            return None
        return LocationItem(path=info.path, start_line=info.line, end_line=info.line)
    if call.kind == "table":
        table = index.tables.get(call.value)
        if table is None or table.path is None or not table.path.is_file():
            return None
        return LocationItem(path=table.path, start_line=table.line, end_line=table.line)
    if call.kind == "column":
        column = _resolve_column(index, call.table, call.value)
        if column is None or column.path is None or not column.path.is_file():
            return None
        return LocationItem(path=column.path, start_line=column.line, end_line=column.line)
    if call.kind == "vite":
        path = index.vite_entries.get(call.value)
        if path is None or not path.is_file():
            return None
        return LocationItem(path=path)
    if call.kind in {"url", "asset"}:
        # Jump to the helper implementation when the path itself is not a file.
        for info in index.view_helpers:
            if info.name == call.kind and info.path is not None and info.path.is_file():
                return LocationItem(path=info.path, start_line=info.line, end_line=info.line)
        return None
    if call.kind == "action" and call.controller:
        resolved = resolve_controller_action(index, call.controller, call.value, source=source)
        if resolved is None:
            return None
        path, method_line = resolved
        return LocationItem(
            path=path,
            start_line=method_line,
            end_line=method_line,
        )
    return None


def _resolve_column(index: AppIndex, table_hint: str | None, column: str):
    """A column in the hinted table, else the first table that has that name."""
    table = resolve_table(table_hint, index.tables)
    if table is not None:
        return index.tables[table].columns.get(column)
    for info in index.tables.values():
        found = info.columns.get(column)
        if found is not None:
            return found
    return None


def _resolve_template_var(index: AppIndex, name: str, *, uri_path: Path | None):
    view_name = None
    if uri_path is not None:
        view_name = view_name_for_template(index.views, uri_path)
    merged = merge_vars_for_view(
        view_name,
        view_data=index.view_data,
        helpers=list(index.view_helpers),
        shared=index.view_shared,
    )
    return merged.get(name)


def document_links(
    index: AppIndex,
    source: str,
    *,
    language: str,
) -> list[DocumentLinkItem]:
    """Document links for view-like / route / config / action string arguments."""
    links: list[DocumentLinkItem] = []
    for call in find_calls(source, language=language):
        target: Path | None = None
        tooltip = ""
        if call.kind in {"view", "include", "extends"}:
            target = index.views.get(call.value)
            tooltip = f"Open view {call.value}"
        elif call.kind == "route":
            info = index.routes.get(call.value)
            target = info.path if info else None
            tooltip = f"Open route {call.value}"
        elif call.kind == "config":
            target = config_file_for_key(index, call.value)
            tooltip = f"Open config {call.value}"
        elif call.kind == "env":
            info = index.env_keys.get(call.value)
            target = info.path if info else None
            tooltip = f"Open {call.value} in {info.path.name}" if info and info.path else ""
        elif call.kind == "table":
            table = index.tables.get(call.value)
            target = table.path if table else None
            tooltip = f"Open table {call.value}"
        elif call.kind == "action" and call.controller:
            resolved = resolve_controller_action(index, call.controller, call.value, source=source)
            if resolved is not None:
                target = resolved[0]
                tooltip = f"Open {call.controller}@{call.value}"
        if target is None:
            continue
        links.append(
            DocumentLinkItem(
                target=target,
                start_line=call.start_line,
                start_character=call.start_character,
                end_line=call.end_line,
                end_character=call.end_character,
                tooltip=tooltip,
            )
        )
    return links


def _iter_reference_sources(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield ``(path, language)`` for files that may reference views.

    Scans only app-relevant subtrees and prunes heavy directories (``.venv``,
    ``node_modules``, ``website``, …) so find-references cannot hang when the
    workspace root is a monorepo.
    """
    if not root.is_dir():
        return

    bases: list[Path] = []
    for relative in _REFERENCE_SCAN_DIRS:
        candidate = root / relative
        if candidate.is_dir():
            bases.append(candidate)
    if not bases:
        # No conventional layout — still avoid a full-tree rglob("*").
        bases = [root]

    seen_files: set[Path] = set()
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = sorted(
                name
                for name in dirnames
                if name not in _SKIP_DIR_NAMES and not name.startswith(".")
            )
            for name in sorted(filenames):
                if name.endswith(".py"):
                    language = "python"
                elif name.endswith(".prism.html"):
                    language = "prism"
                else:
                    continue
                path = Path(dirpath, name)
                resolved = path.resolve()
                if resolved in seen_files:
                    continue
                seen_files.add(resolved)
                yield resolved, language


def find_view_references(
    index: AppIndex,
    view_name: str,
    *,
    extra_sources: list[tuple[Path, str, str]] | None = None,
) -> list[LocationItem]:
    """Find ``view("name")`` / ``@include('name')`` sites under the app root."""
    locations: list[LocationItem] = []
    seen: set[tuple[str, int, int]] = set()

    def _add(path: Path, call: StringCall) -> None:
        key = (str(path), call.start_line, call.start_character)
        if key in seen:
            return
        seen.add(key)
        locations.append(
            LocationItem(
                path=path,
                start_line=call.start_line,
                start_character=call.start_character,
                end_line=call.end_line,
                end_character=call.end_character,
            )
        )

    for path, text, language in extra_sources or []:
        for call in find_calls(text, language=language):
            if call.kind in {"view", "include", "extends"} and call.value == view_name:
                _add(path, call)

    for path, language in _iter_reference_sources(index.base_path):
        finder = find_python_calls if language == "python" else find_prism_calls
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover
            continue
        for call in finder(text):
            if call.kind in {"view", "include", "extends"} and call.value == view_name:
                _add(path, call)
    return locations


def references(
    index: AppIndex,
    source: str,
    line: int,
    character: int,
    *,
    language: str,
    document_path: Path | None = None,
) -> list[LocationItem]:
    """Find-references for a view name under the cursor."""
    call = call_at(source, line, character, language=language)
    if call is None or call.kind not in {"view", "include", "extends"}:
        return []
    extras: list[tuple[Path, str, str]] = []
    if document_path is not None:
        extras.append((document_path, source, language))
    return find_view_references(index, call.value, extra_sources=extras)


def code_actions_create_view(
    index: AppIndex,
    source: str,
    *,
    language: str = "python",
) -> list[CodeActionItem]:
    """Propose creating a missing ``.prism.html`` for unknown ``view("…")`` diagnostics."""
    actions: list[CodeActionItem] = []
    for diag in diagnostics_python(index, source):
        if diag.code != "unknown-view":
            continue
        # Message shape: Unknown view [name].
        start = diag.message.find("[")
        end = diag.message.find("]")
        if start < 0 or end < 0:  # pragma: no cover - message always bracketed
            continue
        name = diag.message[start + 1 : end]
        if not name or name in index.views:  # pragma: no cover - filtered by diagnostics
            continue
        path = view_path_for_name(index.base_path, name)
        actions.append(
            CodeActionItem(
                title=f"Create view [{name}]",
                kind="quickfix",
                view_name=name,
                create_path=path,
                start_line=diag.start_line,
                start_character=diag.start_character,
                end_line=diag.end_line,
                end_character=diag.end_character,
            )
        )
    return actions


def create_view_file(path: Path) -> None:
    """Write an empty Prism template (parents created as needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
