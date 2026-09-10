"""Framework-aware LSP feature logic (protocol-agnostic results)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
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
)
from almasix.lsp.directives import directive_hover
from almasix.lsp.index import (
    AppIndex,
    config_file_for_key,
    controller_methods,
    resolve_controller_action,
    resolve_controller_path,
    view_path_for_name,
)

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
) -> list[CompletionItem]:
    """Suggest names for the call under the cursor."""
    ctx = context_at(source, line, character, language=language)
    if ctx is None:
        return []
    return completions_for_context(index, ctx)


def completions_for_context(index: AppIndex, ctx: CursorContext) -> list[CompletionItem]:
    if ctx.kind in {"view", "include", "extends"}:
        names = _filter_prefix(sorted(index.views), ctx.prefix)
        return [
            CompletionItem(label=name, kind=ctx.kind, detail=str(index.views[name]))
            for name in names
        ]
    if ctx.kind == "route":
        names = _filter_prefix(sorted(index.routes), ctx.prefix)
        return [
            CompletionItem(
                label=name,
                kind="route",
                detail=f"{' '.join(index.routes[name].methods)} {index.routes[name].uri}",
            )
            for name in names
        ]
    if ctx.kind == "config":
        names = _filter_prefix(list(index.config_keys), ctx.prefix)
        return [CompletionItem(label=name, kind="config") for name in names]
    if ctx.kind == "trans":
        names = _filter_prefix(list(index.translation_keys), ctx.prefix)
        return [CompletionItem(label=name, kind="trans") for name in names]
    if ctx.kind == "middleware":
        names = _filter_prefix(list(index.middleware_aliases), ctx.prefix)
        return [CompletionItem(label=name, kind="middleware") for name in names]
    if ctx.kind == "action" and ctx.controller:
        path = resolve_controller_path(index, ctx.controller)
        if path is None:
            return []
        names = _filter_prefix(sorted(controller_methods(path)), ctx.prefix)
        return [
            CompletionItem(
                label=name,
                kind="action",
                detail=f"{ctx.controller}.{name}",
            )
            for name in names
        ]
    return []


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
) -> HoverItem | None:
    """Hover for Prism directives and known string-keyed helpers."""
    lang = language.lower()
    if lang in {"prism", "html", "prism-html"}:
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
) -> LocationItem | None:
    """Go-to-definition for view / route / config / controller action strings."""
    call = call_at(source, line, character, language=language)
    if call is None:
        return None
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
