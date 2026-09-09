"""IDE helpers — type stubs and local editor install (M47)."""

from __future__ import annotations

from almasix.ide.install import IdeInstallResult, install_editor_config
from almasix.ide.stubs import StubResult, generate_stubs

__all__ = [
    "IdeInstallResult",
    "StubResult",
    "generate_stubs",
    "install_editor_config",
]
