---
title: Editor setup
description: Sideload the Almasix VS Code extension and JetBrains plugin — local-first, Marketplace later.
---

Almasix editor support is **local-first**. You install a `.vsix` or JetBrains
`.zip` built from this repository. Visual Studio Marketplace / Open VSX /
JetBrains Marketplace listings land later (when publisher accounts exist) —
they are **not** required to develop or QA.

For language features themselves, see [Prism language support](/prism-language/)
and the [Language server](/language-server/).

## Quick path

```bash
# From an Almasix application root
pip install 'almasix[lsp]'
smith ide:install          # .vscode settings + JetBrains note
smith ide:stubs            # .pyi for models + route name Literal
```

Then sideload the editor package for your IDE (below).

## VS Code / Cursor / VSCodium

### Build the VSIX

```bash
cd editors/vscode
npm install
npm run package
# → almasix-0.1.0.vsix
```

`npm run package` invokes `npx @vscode/vsce package` — you do **not** need a
global `vsce` install.

### Install from VSIX

1. Extensions view → **⋯** → **Install from VSIX…**
2. Choose `editors/vscode/almasix-*.vsix`
3. Open a folder that contains `bootstrap/app.py`
4. Confirm the status bar shows **Almasix** (not “LSP missing”)

Settings written by `smith ide:install`:

- `files.associations`: `*.prism.html` → `prism-html`
- `almasix.pythonPath`: `${workspaceFolder}/.venv/bin/python`
- Emmet / format-on-save for Prism

Commands: **Almasix: Rebuild LSP Index**, **Show Application Info**,
**Restart Language Server**.

Full details: [`editors/vscode/README.md`](https://github.com/almasix-dev/almasix/blob/main/editors/vscode/README.md).

## JetBrains (PyCharm / IntelliJ)

Architecture is **LSP-first**: the plugin is a Platform shell (file type,
TextMate, run configs) that runs `almasix-lsp` through LSP4IJ.

Prism files must show as language **Prism** (not HTML). The plugin overrides
`*.prism.html` so the built-in HTML type cannot steal them, and ships a VS Code–
shaped TextMate `package.json` so directive / `{{ }}` scopes color correctly.

### Build the zip

```bash
cd editors/jetbrains
./gradlew buildPlugin
# → build/distributions/*.zip
```

Requires JDK 17+.

### Install Plugin from Disk

1. **Settings → Plugins → ⚙ → Install Plugin from Disk…**
2. Choose the zip under `editors/jetbrains/build/distributions/`
3. Restart; open an Almasix app with `almasix[lsp]` in the venv

`smith ide:install` also writes `.idea/almasix-editor.md` with these steps.

Full details: [`editors/jetbrains/README.md`](https://github.com/almasix-dev/almasix/blob/main/editors/jetbrains/README.md).

## Type stubs

```bash
smith ide:stubs
# → .almasix/stubs/models/*.pyi
# → .almasix/stubs/routes.pyi   (RouteName = Literal[...])
```

Point pyright `stubPath` / mypy `mypy_path` at `.almasix/stubs`. Column names
come from each model's `fillable` / `casts` (schema inspection optional).

## Other editors

Generic LSP recipes (Neovim, Helix, Zed, …) stay on the
[Language server](/language-server/) page — same `almasix-lsp` binary.

## Marketplace (when published)

| Channel | Status |
| --- | --- |
| Visual Studio Marketplace | Not required yet — sideload VSIX |
| Open VSX | Same |
| JetBrains Marketplace | Same — Install from Disk |

When listings go live, `smith ide:install` will gain recommendation IDs;
until then the in-repo artifacts are the supported install path.

## Parity matrix

| Capability | VS Code family | PyCharm / IntelliJ |
| --- | --- | --- |
| Prism highlighting (TextMate) | Extension grammar (`prism-html`) | File type override + TextMate bundle (not HTML) |
| Snippets | Bundled | Via TextMate / live templates follow-up |
| LSP completions / diagnostics / hover / definition | `vscode-languageclient` → `almasix-lsp` | LSP4IJ → `almasix-lsp` |
| Find references (view names) | Same LSP (pruned app scan) | Same LSP (pruned app scan) |
| Rebuild index / app info | Command palette → LSP commands | LSP4IJ execute command / notification |
| Format Prism | `smith prism:format` / extension formatter hook | External tool / Smith run config |
| Smith serve / queue / migrate | tasks.json (optional) | **Almasix Smith** run configuration type |
| Type stubs | `smith ide:stubs` (shared) | Same |
| Local install helper | `smith ide:install` → `.vscode/*` | `smith ide:install` → `.idea/almasix-editor.md` |
| Marketplace | Sideload first | Sideload first |

No silent gap: both editors get Prism association + the same language server.
Native-only New… wizards and debugger templates on JetBrains are named
follow-ups in PLAN (not blockers for the editor-integration gate).

## Demo

```bash
cd examples/progress
smith progress:ide
```
