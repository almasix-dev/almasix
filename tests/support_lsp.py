"""Helpers to drive almasix-lsp over the LSP wire protocol (JSON-RPC + Content-Length)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from pygls.uris import from_fs_path


class LspWireSession:
    """In-process stdio session against a pygls server (counts toward coverage)."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self._to_server_r, self._to_server_w = _pipe_pair()
        self._from_server_r, self._from_server_w = _pipe_pair()
        self._thread = threading.Thread(target=self._run, name="almasix-lsp-test", daemon=True)
        self._id = 0
        self._pending: dict[int, dict[str, Any]] = {}
        self._notifications: list[dict[str, Any]] = []
        self._buffer = b""
        self._thread.start()

    def _run(self) -> None:
        try:
            self._server.start_io(self._to_server_r, self._from_server_w)
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._to_server_w.close()
        except Exception:
            pass
        try:
            self._from_server_w.close()
        except Exception:
            pass
        self._thread.join(timeout=5)

    def request(self, method: str, params: Any, *, timeout: float = 10.0) -> Any:
        self._id += 1
        msg_id = self._id
        self._send({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
        return self._wait_response(msg_id, timeout=timeout)

    def notify(self, method: str, params: Any) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _send(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._to_server_w.write(header + body)
        self._to_server_w.flush()

    def _wait_response(self, msg_id: int, *, timeout: float) -> Any:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if msg_id in self._pending:
                message = self._pending.pop(msg_id)
                if "error" in message:
                    raise AssertionError(f"LSP error: {message['error']}")
                return message.get("result")
            self._read_available()
            time.sleep(0.01)
        raise TimeoutError(f"No response for request id={msg_id}")

    def _read_available(self) -> None:
        import select

        while True:
            ready, _, _ = select.select([self._from_server_r], [], [], 0)
            if not ready:
                return
            chunk = self._from_server_r.read1(65536)
            if not chunk:
                return
            self._buffer += chunk
            while True:
                message = self._pop_message()
                if message is None:
                    break
                if "id" in message and ("result" in message or "error" in message):
                    self._pending[int(message["id"])] = message
                else:
                    self._notifications.append(message)

    def _pop_message(self) -> dict[str, Any] | None:
        sep = b"\r\n\r\n"
        idx = self._buffer.find(sep)
        if idx < 0:
            return None
        header = self._buffer[:idx].decode("ascii", errors="replace")
        length = None
        for line in header.split("\r\n"):
            if line.lower().startswith("content-length:"):
                length = int(line.split(":", 1)[1].strip())
        if length is None:
            self._buffer = self._buffer[idx + len(sep) :]
            return None
        start = idx + len(sep)
        if len(self._buffer) < start + length:
            return None
        body = self._buffer[start : start + length]
        self._buffer = self._buffer[start + length :]
        return json.loads(body.decode("utf-8"))


def _pipe_pair():
    import os

    r_fd, w_fd = os.pipe()
    return os.fdopen(r_fd, "rb"), os.fdopen(w_fd, "wb")


def initialize_session(
    session: LspWireSession,
    root: Path,
    *,
    process_id: int | None = None,
) -> dict[str, Any]:
    uri = from_fs_path(str(root.resolve()))
    assert uri is not None
    result = session.request(
        "initialize",
        {
            "processId": process_id,
            "rootUri": uri,
            "rootPath": str(root.resolve()),
            "capabilities": {
                "textDocument": {
                    "completion": {"completionItem": {"snippetSupport": True}},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "definition": {"linkSupport": True},
                    "documentLink": {"tooltipSupport": True},
                    "publishDiagnostics": {},
                },
                "workspace": {"workspaceFolders": True},
            },
            "workspaceFolders": [{"uri": uri, "name": root.name}],
        },
    )
    session.notify("initialized", {})
    return result


def open_document(
    session: LspWireSession,
    path: Path,
    text: str,
    *,
    language_id: str = "python",
) -> str:
    uri = from_fs_path(str(path.resolve()))
    assert uri is not None
    session.notify(
        "textDocument/didOpen",
        {
            "textDocument": {
                "uri": uri,
                "languageId": language_id,
                "version": 1,
                "text": text,
            }
        },
    )
    return uri
