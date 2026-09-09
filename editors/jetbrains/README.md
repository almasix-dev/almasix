# Almasix for JetBrains (PyCharm / IntelliJ)

LSP-first plugin shell: Prism file type, TextMate highlighting, Smith run
configurations, and **almasix-lsp** via [LSP4IJ](https://github.com/redhat-developer/lsp4ij).

Marketplace publish is **not** required — install the zip from Disk.

## Install Plugin from Disk (sideload)

1. Build:

   ```bash
   cd editors/jetbrains
   ./gradlew buildPlugin
   ```

   Artifact: `build/distributions/Almasix-0.1.0.zip` (name may include
   version from `gradle.properties`).

2. In PyCharm / IntelliJ:

   - **Settings → Plugins → ⚙ → Install Plugin from Disk…**
   - Choose the zip from `build/distributions/`
   - Restart when prompted

3. Open an Almasix app. Ensure the project venv has the language server:

   ```bash
   pip install 'almasix[lsp]'
   ```

4. LSP4IJ starts `almasix-lsp` from `.venv/bin/almasix-lsp` (or
   `python -m almasix.lsp`). Prism (`.prism.html`) and Python files are mapped.

5. Optional: `smith ide:install` writes `.idea/almasix-editor.md` with these
   steps.

## Features

| Piece | Status |
| --- | --- |
| Prism file type (`.prism.html`) | Shipped |
| TextMate grammar bundle | Bundled under `resources/textMate/prism/` |
| LSP → `almasix-lsp` (LSP4IJ) | Shipped |
| Smith run configuration type | Shipped (`Almasix Smith`) |
| New… generators / debugger templates | Follow-up (see PLAN M47 notes) |
| Marketplace listing | Post-gate (needs publisher account) |

## Develop

- JDK 17+
- `./gradlew buildPlugin`
- `./gradlew runIde` — sandbox IDE with the plugin loaded

## Manual LSP4IJ pairing (fallback)

If the bundled server mapping does not attach, add an LSP4IJ user-defined
server:

- Command: `$ProjectFileDir$/.venv/bin/almasix-lsp`
- Languages: Prism, Python
- Working directory: project root (`bootstrap/app.py`)
