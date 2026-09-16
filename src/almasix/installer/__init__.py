"""Installer CLI (`almasix new`, …)."""

from almasix.installer.cli import app
from almasix.installer.errors import ScaffoldError
from almasix.installer.scaffold import scaffold_app

__all__ = ["ScaffoldError", "app", "scaffold_app"]
