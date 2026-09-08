"""Publish framework error views into the application."""

from __future__ import annotations

import shutil
from pathlib import Path

BUNDLES = ("default", "tailwind", "bootstrap")


class ErrorsPublishError(ValueError):
    """Invalid errors:publish request."""


def framework_errors_path(bundle: str = "default") -> Path:
    """Return ``…/views/<bundle>/errors`` holding ``{status}.prism.html`` stubs."""
    if bundle not in BUNDLES:
        raise ErrorsPublishError(
            f"Unknown error view bundle {bundle!r}. Choose one of: {', '.join(BUNDLES)}"
        )
    root = Path(__file__).resolve().parent / "views" / bundle / "errors"
    return root


def framework_views_root(bundle: str = "default") -> Path:
    """Return the Prism path root for ``bundle`` (contains ``errors/``)."""
    if bundle not in BUNDLES:
        raise ErrorsPublishError(
            f"Unknown error view bundle {bundle!r}. Choose one of: {', '.join(BUNDLES)}"
        )
    return Path(__file__).resolve().parent / "views" / bundle


def publish_errors(
    base_path: Path,
    *,
    bundle: str = "default",
    force: bool = False,
) -> Path:
    """Copy a framework error-view bundle into ``resources/views/errors/``."""
    source = framework_errors_path(bundle)
    if not source.is_dir():
        raise ErrorsPublishError(f"Bundle directory missing: {source}")
    dest = Path(base_path) / "resources" / "views" / "errors"
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = dest / relative
        if target.exists() and not force:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return dest
