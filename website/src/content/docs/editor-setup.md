---
title: Editor setup
description: Install the Almasix VS Code extension and JetBrains plugin from the Marketplaces or GitHub Releases.
---

Almasix editor packages live in
[`almasix-dev/ide-support`](https://github.com/almasix-dev/ide-support): VS Code /
Cursor / VSCodium extension, JetBrains plugin (Almasix Idea), and shared Prism
grammar assets.

Install from the **Visual Studio Marketplace** / **JetBrains Marketplace**, or
sideload a `.vsix` / `.zip` from
[GitHub Releases](https://github.com/almasix-dev/ide-support/releases).

For language features themselves, see [Prism language support](/prism-language/)
and the [Language server](/language-server/) (VS Code family).

## Quick path

```bash title="terminal"
# From an Almasix application root
pip install 'almasix[lsp]'   # LSP for VS Code; index dump used by JetBrains too
smith ide:install            # .vscode settings + JetBrains note
smith ide:stubs              # .pyi for models + route name Literal
smith ide:index --json       # symbol index (JetBrains rebuilds this automatically)
```

Then install the editor package for your IDE (below).

## VS Code / Cursor / VSCodium

Intelligence comes from **`almasix-lsp`** (language server).

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

Architecture is **native-heavy (Almasix Idea)**: Prism file type, native
HTML+Prism highlighter, Smith run configs, and **Kotlin completions /
annotators** driven by a plugin-owned index. The plugin runs
`smith ide:index --json` (or `python -m almasix.ide.index`) against the project
interpreter — it does **not** use LSP4IJ or `almasix-lsp`.

Prism files must show as language **Prism** (not HTML). Highlighting is native:
the IDE's own HTML highlighter is layered over the template's HTML spans, with
`@directives`, `{{ }}` and `{{-- --}}` painted on top. Each file also gets a
second HTML PSI root, so HTML completion and inspections keep working, and
typing `{{` closes itself as `{{  }}` with the caret in the middle.

Completions and unknown-string annotations cover routes, views, config,
translations, middleware, env keys, tables/columns, Articulate relations and
casts, gates, validation rules, disks/queues/caches, Prism components and
directives, Vite entries, Inertia pages, and Smith command names. Use
**Almasix → Rebuild Index** after large project changes if the cache is stale.

### Install

1. Install **Almasix** from the JetBrains Marketplace (plugin id
   `com.almasix.ide`), **or** **Settings → Plugins → ⚙ → Install Plugin from
   Disk…** with a zip from
   [`almasix-dev/ide-support` Releases](https://github.com/almasix-dev/ide-support/releases)
   (plugin **0.2.0+** for the native Almasix Idea rewrite).
2. Restart; open an Almasix app whose **project** interpreter has Almasix
   installed (or a `.venv` next to `bootstrap/app.py`).

`smith ide:install` also writes `.idea/almasix-editor.md` with these steps.

Full details: [`jetbrains/README.md`](https://github.com/almasix-dev/ide-support/blob/main/jetbrains/README.md).

## Type stubs

```bash title="terminal"
smith ide:stubs
```

Writes `.pyi` stubs for Articulate models and a `Literal[...]` of route names
so type checkers can complete `route("…")` without runtime imports.

## Symbol index

```bash title="terminal"
smith ide:index --json
```

Boots the application and dumps views, routes, config keys, models, gates,
components, validation rules, and related symbols. JetBrains caches this dump;
VS Code’s language server builds the same discovery path in-process.

## VS Code ↔ PyCharm parity

| Surface | VS Code | JetBrains |
| --- | --- | --- |
| Prism file type / highlighting | `prism-html` TextMate | Native Prism + HTML layer |
| Language intelligence | `almasix-lsp` (LSP) | Native Kotlin + `ide:index` |
| `smith` run configs | tasks.json via `ide:install` | Smith run configuration |
| Marketplace | VS Marketplace | JetBrains Marketplace |

Packaging and Marketplace publish live in
[`almasix-dev/ide-support`](https://github.com/almasix-dev/ide-support).
