"""Installer CLI (`almasix new`, …)."""

from almasix.installer.cli import app
from almasix.installer.scaffold import ScaffoldError, scaffold_app

__all__ = ["ScaffoldError", "app", "scaffold_app"]
