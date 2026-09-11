---
title: Editor setup
description: Install the Almasix VS Code extension and JetBrains plugin from the Marketplaces or GitHub Releases.
---

Almasix editor packages live in
[`almasix-dev/ide-support`](https://github.com/almasix-dev/ide-support): VS Code /
Cursor / VSCodium extension, JetBrains plugin, and shared Prism grammar assets.

Install from the **Visual Studio Marketplace** / **JetBrains Marketplace**, or
sideload a `.vsix` / `.zip` from
[GitHub Releases](https://github.com/almasix-dev/ide-support/releases).

For language features themselves, see [Prism language support](/prism-language/)
and the [Language server](/language-server/).

## Quick path

```bash title="terminal"
# From an Almasix application root
pip install 'almasix[lsp]'
smith ide:install          # .vscode settings + JetBrains note
smith ide:stubs            # .pyi for models + route name Literal
```

Then install the editor package for your IDE (below).

## VS Code / Cursor / VSCodium

1. Install **Almasix** from the
   [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=almasix.almasix)
   (publisher `almasix`), **or** **Install from VSIX…** with a release artifact
   from [`almasix-dev/ide-support`](https://github.com/almasix-dev/ide-support/releases).
2. Open a folder that contains `bootstrap/app.py`
3. Confirm the status bar shows **Almasix** (not “LSP missing”)

Settings written by `smith ide:install`:

- `files.associations`: `*.prism.html` → `prism-html`
- `almasix.pythonPath`: `${workspaceFolder}/.venv/bin/python`
- Emmet / format-on-save for Prism

Commands: **Almasix: Rebuild LSP Index**, **Show Application Info**,
**Restart Language Server**.

Full details: [`almasix-dev/ide-support` README](https://github.com/almasix-dev/ide-support)
and [`vscode/README.md`](https://github.com/almasix-dev/ide-support/blob/main/vscode/README.md).

## JetBrains (PyCharm / IntelliJ)

Architecture is **LSP-first**: the plugin is a Platform shell (file type,
native HTML+Prism highlighter, run configs) that runs `almasix-lsp` through
LSP4IJ.

Prism files must show as language **Prism** (not HTML). Highlighting is native:
the IDE's own HTML highlighter is layered over the template's HTML spans, with
`@directives`, `{{ }}` and `{{-- --}}` painted on top. Each file also gets a
second HTML PSI root, so HTML completion and inspections keep working, and
typing `{{` closes itself as `{{  }}` with the caret in the middle.

Completions and Ctrl-click for `{{ globals }}`, `route()`, `url()`, `asset()`,
and `vite()` paths come from `almasix-lsp` (wired by language + `*.prism.html`
filename). Ctrl+Space anywhere in a template offers the `@directive` list plus
the globals and `view()` data available to that template. The same server also
completes `env("…")` / dotenv `${…}` keys and table / column names from
migrations; `.env` files are mapped to the LSP in both editors.

### Install

1. Install **Almasix** from the JetBrains Marketplace (plugin id
   `com.almasix.ide`), **or** **Settings → Plugins → ⚙ → Install Plugin from
   Disk…** with a zip from
   [`almasix-dev/ide-support` Releases](https://github.com/almasix-dev/ide-support/releases)
2. Restart; open an Almasix app with `almasix[lsp]` in the venv

`smith ide:install` also writes `.idea/almasix-editor.md` with these steps.

Full details: [`jetbrains/README.md`](https://github.com/almasix-dev/ide-support/blob/main/jetbrains/README.md).

## Type stubs

```bash title="terminal"
smith ide:stubs
```

Writes `.pyi` stubs for Articulate models and a `Literal[...]` of route names
so the editor can complete `route("…")` without runtime imports.

## VS Code ↔ PyCharm parity

| Surface | VS Code | JetBrains |
| --- | --- | --- |
| Prism file type / highlighting | `prism-html` TextMate | Native Prism + HTML layer |
| `almasix-lsp` | vscode-languageclient | LSP4IJ |
| `smith` run configs | tasks.json via `ide:install` | Smith run configuration |
| Marketplace | VS Marketplace | JetBrains Marketplace |

Language intelligence is shared (`almasix-lsp`). Packaging and Marketplace
publish live in [`almasix-dev/ide-support`](https://github.com/almasix-dev/ide-support).
