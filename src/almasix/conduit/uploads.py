"""File upload helpers for Conduit components."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from almasix.config import config


def _cfg(key: str, default: Any = None) -> Any:
    try:
        value = config(key, default)
    except RuntimeError:
        return default
    return default if value is None else value


def store_upload(file: Any, *, directory: str = "conduit-uploads") -> str:
    """Persist an uploaded file-like / UploadFile; return path relative to disk root."""
    base = Path(_cfg("filesystem.disks.local.root", "storage/app"))
    target_dir = base / directory
    target_dir.mkdir(parents=True, exist_ok=True)
    name = getattr(file, "filename", None) or f"upload-{uuid4().hex}"
    safe = Path(str(name)).name
    dest = target_dir / f"{uuid4().hex[:8]}-{safe}"
    if hasattr(file, "file"):
        data = file.file.read()
    elif hasattr(file, "read"):
        data = file.read()
    elif isinstance(file, (bytes, bytearray)):
        data = bytes(file)
    else:
        data = b""
    dest.write_bytes(data)
    try:
        return str(dest.relative_to(base))
    except ValueError:
        return str(dest)
