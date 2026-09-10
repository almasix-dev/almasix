"""pygls language server wiring for Almasix."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.uris import from_fs_path, to_fs_path

from almasix.lsp import features as feat
from almasix.lsp.index import AppIndex, build_index, find_app_root

SERVER_NAME = "almasix-lsp"
SERVER_VERSION = "0.1.0"


class AlmasixLanguageServer(LanguageServer):
    """Language server that indexes a booted Almasix application."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(SERVER_NAME, SERVER_VERSION, *args, **kwargs)
        self.index = AppIndex(base_path=Path.cwd(), error="Index not built yet.")
        self._workspace_root: Path | None = None


def create_server() -> AlmasixLanguageServer:
    """Build a configured ``AlmasixLanguageServer`` with feature handlers."""
    server = AlmasixLanguageServer()

    @server.feature(types.INITIALIZE)
    def initialize(ls: AlmasixLanguageServer, params: types.InitializeParams) -> None:
        root = _resolve_workspace_root(params)
        ls._workspace_root = root
        ls.index = _safe_build_index(ls, root)

    @server.feature(types.INITIALIZED)
    def initialized(ls: AlmasixLanguageServer, _params: types.InitializedParams) -> None:
        if ls.index.error:
            ls.window_show_message(
                types.ShowMessageParams(
                    type=types.MessageType.Error,
                    message=ls.index.error,
                )
            )
        else:
            ls.window_show_message(
                types.ShowMessageParams(
                    type=types.MessageType.Info,
                    message=(
                        f"Almasix LSP indexed {len(ls.index.views)} views, "
                        f"{len(ls.index.routes)} routes, "
                        f"{len(ls.index.config_keys)} config keys, "
                        f"{len(ls.index.middleware_aliases)} middleware, "
                        f"{len(ls.index.translation_keys)} translations."
                    ),
                )
            )

    @server.feature(
        types.TEXT_DOCUMENT_COMPLETION,
        types.CompletionOptions(trigger_characters=['"', "'", ".", "@"]),
    )
    def completion(
        ls: AlmasixLanguageServer, params: types.CompletionParams
    ) -> types.CompletionList:
        doc = ls.workspace.get_text_document(params.text_document.uri)
        items = feat.completions(
            ls.index,
            doc.source,
            params.position.line,
            params.position.character,
            language=_language_id(doc),
        )
        return types.CompletionList(
            is_incomplete=False,
            items=[
                types.CompletionItem(
                    label=item.label,
                    kind=_completion_kind(item.kind),
                    detail=item.detail or None,
                    insert_text=item.label,
                )
                for item in items
            ],
        )

    @server.feature(types.TEXT_DOCUMENT_HOVER)
    def hover(ls: AlmasixLanguageServer, params: types.HoverParams) -> types.Hover | None:
        doc = ls.workspace.get_text_document(params.text_document.uri)
        item = feat.hover(
            ls.index,
            doc.source,
            params.position.line,
            params.position.character,
            language=_language_id(doc),
        )
        if item is None:
            return None
        return types.Hover(
            contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=item.contents),
            range=types.Range(
                start=types.Position(line=item.start_line, character=item.start_character),
                end=types.Position(line=item.end_line, character=item.end_character),
            ),
        )

    @server.feature(types.TEXT_DOCUMENT_DEFINITION)
    def definition(
        ls: AlmasixLanguageServer, params: types.DefinitionParams
    ) -> types.Location | None:
        doc = ls.workspace.get_text_document(params.text_document.uri)
        item = feat.definition(
            ls.index,
            doc.source,
            params.position.line,
            params.position.character,
            language=_language_id(doc),
        )
        return _location(item)

    @server.feature(types.TEXT_DOCUMENT_REFERENCES)
    def references(
        ls: AlmasixLanguageServer, params: types.ReferenceParams
    ) -> list[types.Location]:
        doc = ls.workspace.get_text_document(params.text_document.uri)
        path = to_fs_path(params.text_document.uri)
        doc_path = Path(path) if path else None
        items = feat.references(
            ls.index,
            doc.source,
            params.position.line,
            params.position.character,
            language=_language_id(doc),
            document_path=doc_path,
        )
        out: list[types.Location] = []
        for item in items:
            loc = _location(item)
            if loc is not None:
                out.append(loc)
        return out

    @server.feature(
        types.TEXT_DOCUMENT_CODE_ACTION,
        types.CodeActionOptions(code_action_kinds=[types.CodeActionKind.QuickFix]),
    )
    def code_action(
        ls: AlmasixLanguageServer, params: types.CodeActionParams
    ) -> list[types.CodeAction]:
        doc = ls.workspace.get_text_document(params.text_document.uri)
        if _language_id(doc).lower() not in {"python", "py"}:
            return []
        actions = feat.code_actions_create_view(ls.index, doc.source, language="python")
        out: list[types.CodeAction] = []
        for action in actions:
            # Only offer when the range overlaps the diagnostic.
            if not _ranges_overlap(
                params.range,
                action.start_line,
                action.start_character,
                action.end_line,
                action.end_character,
            ):
                continue
            out.append(
                types.CodeAction(
                    title=action.title,
                    kind=types.CodeActionKind.QuickFix,
                    diagnostics=[
                        types.Diagnostic(
                            range=types.Range(
                                start=types.Position(
                                    line=action.start_line, character=action.start_character
                                ),
                                end=types.Position(
                                    line=action.end_line, character=action.end_character
                                ),
                            ),
                            message=f"Unknown view [{action.view_name}].",
                            severity=types.DiagnosticSeverity.Error,
                            source=SERVER_NAME,
                            code="unknown-view",
                        )
                    ],
                    command=types.Command(
                        title=action.title,
                        command="almasix.createView",
                        arguments=[str(action.create_path), action.view_name],
                    ),
                )
            )
        return out

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_LINK)
    def document_link(
        ls: AlmasixLanguageServer, params: types.DocumentLinkParams
    ) -> list[types.DocumentLink]:
        doc = ls.workspace.get_text_document(params.text_document.uri)
        links = feat.document_links(ls.index, doc.source, language=_language_id(doc))
        out: list[types.DocumentLink] = []
        for link in links:
            target = from_fs_path(str(link.target))
            if target is None:  # pragma: no cover - path always filesystem-local
                continue
            out.append(
                types.DocumentLink(
                    range=types.Range(
                        start=types.Position(line=link.start_line, character=link.start_character),
                        end=types.Position(line=link.end_line, character=link.end_character),
                    ),
                    target=target,
                    tooltip=link.tooltip or None,
                )
            )
        return out

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(ls: AlmasixLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
        _publish_diagnostics(ls, params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(ls: AlmasixLanguageServer, params: types.DidChangeTextDocumentParams) -> None:
        _publish_diagnostics(ls, params.text_document.uri)

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def did_save(ls: AlmasixLanguageServer, params: types.DidSaveTextDocumentParams) -> None:
        root = ls._workspace_root or find_app_root()
        if root is not None:
            ls.index = _safe_build_index(ls, root)
        _publish_diagnostics(ls, params.text_document.uri)

    @server.command("almasix.rebuildIndex")
    def rebuild_index(ls: AlmasixLanguageServer, _args: list[Any] | None = None) -> str:
        root = ls._workspace_root or find_app_root()
        ls.index = _safe_build_index(ls, root)
        if ls.index.error:
            return ls.index.error
        return (
            f"Indexed {len(ls.index.views)} views, {len(ls.index.routes)} routes, "
            f"{len(ls.index.config_keys)} config keys."
        )

    @server.command("almasix.showAppInfo")
    def show_app_info(ls: AlmasixLanguageServer, _args: list[Any] | None = None) -> str:
        index = ls.index
        if index.error:
            return index.error
        message = (
            f"Almasix app: {index.base_path}\n"
            f"  views={len(index.views)} routes={len(index.routes)} "
            f"config={len(index.config_keys)} models={len(index.models)} "
            f"middleware={len(index.middleware_aliases)} "
            f"translations={len(index.translation_keys)}"
        )
        ls.window_show_message(
            types.ShowMessageParams(type=types.MessageType.Info, message=message)
        )
        return message

    @server.command("almasix.createView")
    def create_view(ls: AlmasixLanguageServer, path: str, name: str = "") -> str:
        target = Path(str(path))
        feat.create_view_file(target)
        root = ls._workspace_root or find_app_root()
        if root is not None:
            ls.index = _safe_build_index(ls, root)
        label = name or target.name
        return f"Created view {label} at {target}"

    return server


def _location(item: feat.LocationItem | None) -> types.Location | None:
    if item is None:
        return None
    uri = from_fs_path(str(item.path))
    if uri is None:  # pragma: no cover - path always filesystem-local
        return None
    return types.Location(
        uri=uri,
        range=types.Range(
            start=types.Position(line=item.start_line, character=item.start_character),
            end=types.Position(line=item.end_line, character=item.end_character),
        ),
    )


def _ranges_overlap(
    client_range: types.Range,
    start_line: int,
    start_character: int,
    end_line: int,
    end_character: int,
) -> bool:
    """True when the client's selection touches the diagnostic range."""
    c_start = (client_range.start.line, client_range.start.character)
    c_end = (client_range.end.line, client_range.end.character)
    d_start = (start_line, start_character)
    d_end = (end_line, end_character)
    return c_start <= d_end and d_start <= c_end


def _safe_build_index(ls: AlmasixLanguageServer, root: Path | None) -> AppIndex:
    token = "almasix-index"
    began = False
    try:
        ls.work_done_progress.begin(
            token,
            types.WorkDoneProgressBegin(
                title="Almasix",
                message="Indexing application…",
                percentage=0,
            ),
        )
        began = True
    except Exception:  # pragma: no cover - client may omit progress support
        began = False
    try:
        return build_index(root)
    finally:
        if began:
            try:
                ls.work_done_progress.end(token, types.WorkDoneProgressEnd(message="Index ready"))
            except Exception:  # pragma: no cover
                pass


def _resolve_workspace_root(params: types.InitializeParams) -> Path | None:
    if params.workspace_folders:
        for folder in params.workspace_folders:
            path = to_fs_path(folder.uri)
            if path is None:  # pragma: no cover - invalid URI from client
                continue
            found = find_app_root(Path(path))
            if found is not None:
                return found
    root_uri = params.root_uri
    if root_uri:
        path = to_fs_path(root_uri)
        if path is not None:
            found = find_app_root(Path(path))
            if found is not None:
                return found
            return Path(path).resolve()
    if params.root_path:
        found = find_app_root(Path(params.root_path))
        if found is not None:
            return found
        return Path(params.root_path).resolve()
    return find_app_root()


def _language_id(doc: Any) -> str:
    return getattr(doc, "language_id", None) or "plaintext"


def _completion_kind(kind: str) -> types.CompletionItemKind:
    if kind in {"view", "include", "extends"}:
        return types.CompletionItemKind.File
    if kind == "route":
        return types.CompletionItemKind.Reference
    if kind in {"config", "trans", "middleware"}:
        return types.CompletionItemKind.Value
    return types.CompletionItemKind.Text


def _publish_diagnostics(ls: AlmasixLanguageServer, uri: str) -> None:
    doc = ls.workspace.get_text_document(uri)
    language = _language_id(doc)
    if language.lower() not in {"python", "py"}:
        ls.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=[])
        )
        return
    items = feat.diagnostics_python(ls.index, doc.source)
    diagnostics = [
        types.Diagnostic(
            range=types.Range(
                start=types.Position(line=d.start_line, character=d.start_character),
                end=types.Position(line=d.end_line, character=d.end_character),
            ),
            message=d.message,
            severity=types.DiagnosticSeverity.Error,
            source=SERVER_NAME,
            code=d.code,
        )
        for d in items
    ]
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
    )
