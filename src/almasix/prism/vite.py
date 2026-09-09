"""Vite integration — ``@vite`` tags for a built manifest or a dev server.

Laravel resolves entry points through ``vite()``; Almasix does the same. Two
modes, decided by whether ``public/hot`` exists:

* **Development.** The Vite dev server writes ``public/hot`` holding its origin,
  and tags point there so edits hot-reload. The scaffold's ``vite.config.js``
  writes that file from a small inline plugin, which is why no Node package is
  needed on the Python side.
* **Production.** ``npm run build`` writes ``public/build`` plus a manifest, and
  tags point at the hashed files the manifest names.

An entry that is missing from the manifest raises rather than emitting a link
to a file that is not there — a blank stylesheet in production is the bug this
avoids.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from almasix.prism.escape import e

#: Where the dev server records its origin, relative to the application root.
HOT_FILE = "public/hot"

#: Manifest locations Vite has used, newest first.
MANIFEST_PATHS = (".vite/manifest.json", "manifest.json")

_STYLE_SUFFIXES = (".css", ".scss", ".sass", ".less", ".styl", ".stylus", ".pcss", ".postcss")


class ViteManifestNotFound(RuntimeError):
    """The build ran, or it did not — this says which."""


class ViteEntryNotFound(RuntimeError):
    """An entry point was asked for that the manifest does not name."""


class Vite:
    """Resolves Vite entry points to HTML tags."""

    def __init__(
        self,
        *,
        base_path: Path | str | None = None,
        build_directory: str = "build",
        hot_file: str | None = None,
    ) -> None:
        self.base_path = Path(base_path) if base_path is not None else None
        self.build_directory = build_directory.strip("/")
        self.hot_file = hot_file or HOT_FILE

    # -- paths ---------------------------------------------------------------

    def _root(self) -> Path:
        if self.base_path is not None:
            return self.base_path
        from almasix.framework.helpers import current_application

        application = current_application()
        return application.base_path if application is not None else Path.cwd()

    def hot_path(self) -> Path:
        return self._root() / self.hot_file

    def dev_server_url(self) -> str | None:
        """The dev server's origin, or ``None`` when it is not running."""
        path = self.hot_path()
        if not path.is_file():
            return None
        origin = path.read_text(encoding="utf-8").strip()
        return (origin or "http://localhost:5173").rstrip("/")

    def manifest_path(self) -> Path:
        build = self._root() / "public" / self.build_directory
        for candidate in MANIFEST_PATHS:
            path = build / candidate
            if path.is_file():
                return path
        raise ViteManifestNotFound(
            f"No Vite manifest in {build}. Run `npm run build` (or `npm run dev` "
            "for the dev server)."
        )

    def has_manifest(self) -> bool:
        """Whether a build is present to read entry points from."""
        try:
            self.manifest_path()
        except ViteManifestNotFound:
            return False
        return True

    def manifest(self) -> dict[str, Any]:
        """The build manifest, read fresh so a rebuild is picked up."""
        data = json.loads(self.manifest_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    # -- resolution ----------------------------------------------------------

    def asset_url(self, path: str) -> str:
        from almasix.routing.url import asset

        return asset(path, absolute=False)

    def entry_url(self, entry: str) -> str:
        """The URL a single entry point is served from."""
        dev = self.dev_server_url()
        if dev is not None:
            return f"{dev}/{entry.lstrip('/')}"
        chunk = self._chunk(entry)
        return self.asset_url(f"{self.build_directory}/{chunk['file']}")

    def _chunk(self, entry: str) -> dict[str, Any]:
        manifest = self.manifest()
        chunk = manifest.get(entry)
        if not isinstance(chunk, dict) or "file" not in chunk:
            known = ", ".join(sorted(manifest)) or "nothing"
            raise ViteEntryNotFound(f"Vite manifest has no entry {entry!r}. It names: {known}.")
        return chunk

    # -- tags ----------------------------------------------------------------

    def __call__(self, entries: str | Iterable[str], *rest: str) -> str:
        """``vite("resources/js/app.js")`` or ``vite(["a.css", "b.js"])``."""
        return self.tags(entries, *rest)

    def tags(self, entries: str | Iterable[str], *rest: str) -> str:
        return "\n".join(self.tag_list(entries, *rest))

    def tag_list(self, entries: str | Iterable[str], *rest: str) -> list[str]:
        tags: list[str] = []
        dev = self.dev_server_url()
        if dev is None and not self.has_manifest():
            # A freshly scaffolded application has not run `npm run build` yet.
            # In development that is a note; in production it is a broken deploy,
            # so reading the manifest below raises there.
            if _debugging():
                return [
                    (
                        f"<!-- Vite: no build in public/{self.build_directory}. "
                        "Run `npm run dev` or `npm run build`. -->"
                    )
                ]
            self.manifest_path()
        if dev is not None:
            tags.append(f'<script type="module" src="{e(dev)}/@vite/client"></script>')
        for entry in _normalize_entries(entries, rest):
            found = [self._dev_tag(entry, dev)] if dev is not None else self._build_tags(entry)
            # A stylesheet imported by a listed JS entry would otherwise be
            # linked twice when the CSS entry is listed as well.
            tags.extend(tag for tag in found if tag not in tags)
        return tags

    def _dev_tag(self, entry: str, dev: str) -> str:
        url = f"{dev}/{entry.lstrip('/')}"
        if _is_style(entry):
            return f'<link rel="stylesheet" href="{e(url)}"/>'
        return f'<script type="module" src="{e(url)}"></script>'

    def _build_tags(self, entry: str) -> list[str]:
        chunk = self._chunk(entry)
        tags: list[str] = []
        # A JS entry importing CSS carries it in `css`, and the stylesheet has
        # to be linked or the page flashes unstyled before the module runs.
        for css in chunk.get("css") or []:
            tags.append(self._style_tag(f"{self.build_directory}/{css}"))
        target = f"{self.build_directory}/{chunk['file']}"
        if _is_style(str(chunk["file"])):
            tags.append(self._style_tag(target))
        else:
            tags.append(f'<script type="module" src="{e(self.asset_url(target))}"></script>')
        return tags

    def _style_tag(self, path: str) -> str:
        return f'<link rel="stylesheet" href="{e(self.asset_url(path))}"/>'

    # -- React refresh (starter kits) ---------------------------------------

    def react_refresh(self) -> str:
        """The preamble React's Fast Refresh needs, and only in development."""
        dev = self.dev_server_url()
        if dev is None:
            return ""
        return (
            '<script type="module">'
            f'import RefreshRuntime from "{e(dev)}/@react-refresh";'
            "RefreshRuntime.injectIntoGlobalHook(window);"
            "window.$RefreshReg$ = () => {};"
            "window.$RefreshSig$ = () => (type) => type;"
            "window.__vite_plugin_react_preamble_installed__ = true;"
            "</script>"
        )


def _normalize_entries(entries: str | Iterable[str], rest: Sequence[str] = ()) -> list[str]:
    if isinstance(entries, str):
        found = [entries]
    else:
        found = [str(entry) for entry in entries]
    return found + [str(entry) for entry in rest]


def _is_style(path: str) -> bool:
    return path.split("?", 1)[0].endswith(_STYLE_SUFFIXES)


def _debugging() -> bool:
    from almasix.config import config

    try:
        return bool(config("app.debug", False))
    except RuntimeError:
        # No application booted, so nothing is being deployed either.
        return True


def vite(entries: str | Iterable[str], *rest: str) -> str:
    """Render Vite tags for ``entries`` (the ``@vite`` directive's engine)."""
    return Vite().tags(entries, *rest)


def vite_react_refresh() -> str:
    """Render the React Fast Refresh preamble (``@viteReactRefresh``)."""
    return Vite().react_refresh()
