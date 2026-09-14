"""IDE helpers — type stubs, local editor install, and symbol index (M47)."""

from __future__ import annotations

from almasix.ide.index import build_ide_index, dump_index_json, index_to_dict
from almasix.ide.install import IdeInstallResult, install_editor_config
from almasix.ide.stubs import StubResult, generate_stubs

__all__ = [
    "IdeInstallResult",
    "StubResult",
    "build_ide_index",
    "dump_index_json",
    "generate_stubs",
    "index_to_dict",
    "install_editor_config",
]
