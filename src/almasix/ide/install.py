"""Write local editor config for Almasix apps (``smith ide:install``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from almasix.lsp.index import find_app_root

_IDE_SUPPORT_REPO = "https://github.com/almasix-dev/ide-support"
_IDE_SUPPORT_RELEASES = f"{_IDE_SUPPORT_REPO}/releases"
_VS_MARKETPLACE = "https://marketplace.visualstudio.com/items?itemName=almasix.almasix"

_VSCODE_EXTENSIONS = {
    "recommendations": [
        "almasix.almasix",
    ],
    "unwantedRecommendations": [],
}

_VSCODE_SETTINGS = {
    "files.associations": {
        "*.prism.html": "prism-html",
    },
    "emmet.includeLanguages": {
        "prism-html": "html",
    },
    "[prism-html]": {
        "editor.defaultFormatter": "almasix.almasix",
        "editor.formatOnSave": True,
    },
    "almasix.pythonPath": "${workspaceFolder}/.venv/bin/python",
}


@dataclass
class IdeInstallResult:
    """Files written by :func:`install_editor_config`."""

    base_path: Path
    written: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def install_editor_config(
    base_path: Path | str | None = None,
    *,
    vscode: bool = True,
    jetbrains: bool = True,
    force: bool = False,
) -> IdeInstallResult:
    """Create ``.vscode`` recommendations/settings and a JetBrains note.

    Points at Marketplace / GitHub Releases for
    `almasix-dev/ide-support <https://github.com/almasix-dev/ide-support>`_; does not
    download packages itself.
    """
    root = Path(base_path) if base_path else find_app_root()
    if root is None or not (Path(root) / "bootstrap" / "app.py").is_file():
        return IdeInstallResult(
            base_path=Path(base_path) if base_path else Path.cwd(),
            error="No Almasix application found (missing bootstrap/app.py).",
        )
    root = Path(root).resolve()
    result = IdeInstallResult(base_path=root)

    if vscode:
        _write_vscode(root, result, force=force)
    if jetbrains:
        _write_jetbrains_note(root, result, force=force)

    result.notes.append(f"Editor packages: {_IDE_SUPPORT_REPO}")
    result.notes.append(
        f"VS Code: Marketplace {_VS_MARKETPLACE} or VSIX from {_IDE_SUPPORT_RELEASES}"
    )
    result.notes.append(
        f"JetBrains: Marketplace plugin com.almasix.ide or zip from {_IDE_SUPPORT_RELEASES}"
    )
    return result


def _write_vscode(root: Path, result: IdeInstallResult, *, force: bool) -> None:
    vscode = root / ".vscode"
    vscode.mkdir(parents=True, exist_ok=True)

    extensions = vscode / "extensions.json"
    if force or not extensions.exists():
        extensions.write_text(
            json.dumps(_VSCODE_EXTENSIONS, indent=2) + "\n",
            encoding="utf-8",
        )
        result.written.append(extensions)
    else:
        result.notes.append(f"Kept existing {extensions.relative_to(root)}")

    settings_path = vscode / "settings.json"
    if force or not settings_path.exists():
        settings_path.write_text(
            json.dumps(_VSCODE_SETTINGS, indent=2) + "\n",
            encoding="utf-8",
        )
        result.written.append(settings_path)
    else:
        merged = _merge_settings(settings_path)
        if merged:
            settings_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
            result.written.append(settings_path)
        else:
            result.notes.append(f"Kept existing {settings_path.relative_to(root)}")


def _merge_settings(path: Path) -> dict[str, object] | None:
    """Merge Almasix keys into an existing settings.json; None if unchanged."""
    try:
        existing = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_VSCODE_SETTINGS)
    if not isinstance(existing, dict):
        return dict(_VSCODE_SETTINGS)

    changed = False
    out = dict(existing)
    for key, value in _VSCODE_SETTINGS.items():
        if key not in out:
            out[key] = value
            changed = True
        elif key == "files.associations" and isinstance(out[key], dict) and isinstance(value, dict):
            for assoc_key, assoc_val in value.items():
                if assoc_key not in out[key]:
                    out[key][assoc_key] = assoc_val
                    changed = True
    return out if changed else None


def _write_jetbrains_note(root: Path, result: IdeInstallResult, *, force: bool) -> None:
    idea = root / ".idea"
    idea.mkdir(parents=True, exist_ok=True)
    note = idea / "almasix-editor.md"
    if note.exists() and not force:
        result.notes.append(f"Kept existing {note.relative_to(root)}")
        return
    note.write_text(
        "\n".join(
            [
                "# Almasix — JetBrains / PyCharm",
                "",
                "1. Install **Almasix** from the JetBrains Marketplace "
                "(plugin id `com.almasix.ide`), **or** download a zip from",
                f"   {_IDE_SUPPORT_RELEASES} and use",
                "   **Settings → Plugins → ⚙ → Install Plugin from Disk…**",
                "2. Restart when prompted. Enable **LSP4IJ** if asked so Prism",
                "   completions come from `almasix-lsp` in the project venv.",
                "3. Run configurations for `smith serve` / `smith queue:work` ship",
                "   with the plugin; or add them manually pointing at `.venv/bin/smith`.",
                "",
                f"Source and releases: {_IDE_SUPPORT_REPO}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result.written.append(note)
