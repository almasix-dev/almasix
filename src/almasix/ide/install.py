"""Write local editor config for Almasix apps (``smith ide:install``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from almasix.lsp.index import find_app_root

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

    Does not download Marketplace packages — documents sideload paths for the
    in-repo VSIX / JetBrains zip built under ``editors/``.
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

    grammar = _locate_grammar(root)
    if grammar is not None:
        result.notes.append(f"Prism TextMate grammar: {grammar}")
    else:
        result.notes.append(
            "Prism grammar lives in the Almasix repo at editors/prism/syntaxes/ "
            "(bundled in the VS Code / JetBrains packages)."
        )
    result.notes.append(
        "Sideload VS Code: Extensions → Install from VSIX… → "
        "editors/vscode/*.vsix (after npm run package)."
    )
    result.notes.append(
        "Sideload JetBrains: Settings → Plugins → ⚙ → Install Plugin from Disk… → "
        "editors/jetbrains/build/distributions/*.zip."
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
                "1. Build the plugin: `cd editors/jetbrains && ./gradlew buildPlugin`",
                "2. **Settings → Plugins → ⚙ → Install Plugin from Disk…**",
                "3. Choose `editors/jetbrains/build/distributions/almasix-*.zip`",
                "4. Enable **LSP4IJ** if prompted (bundled dependency) so Prism",
                "   completions come from `almasix-lsp` in the project venv.",
                "5. Run configurations for `smith serve` / `smith queue:work` ship",
                "   with the plugin; or add them manually pointing at `.venv/bin/smith`.",
                "",
                "Marketplace publish is not required — sideload is the supported path.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result.written.append(note)


def _locate_grammar(root: Path) -> Path | None:
    """Best-effort path to the TextMate grammar (monorepo or package data)."""
    candidates = [
        root / "editors" / "prism" / "syntaxes" / "prism.tmLanguage.json",
        root.parent.parent / "editors" / "prism" / "syntaxes" / "prism.tmLanguage.json",
    ]
    # Walk up a few levels for apps living under examples/.
    current = root
    for _ in range(5):
        candidates.append(current / "editors" / "prism" / "syntaxes" / "prism.tmLanguage.json")
        if current.parent == current:
            break
        current = current.parent
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None
