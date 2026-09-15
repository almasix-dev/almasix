---
title: Editor setup
description: Install the Almasix VS Code extension and JetBrains plugin from the Marketplaces or GitHub Releases.
---

Almasix editor packages live in dedicated repositories:

| Editor | Repository |
| --- | --- |
| VS Code / Cursor / VSCodium | [`almasix-dev/almasix-vscode`](https://github.com/almasix-dev/almasix-vscode) |
| PyCharm / WebStorm (**Almasix Idea**) | [`almasix-dev/almasix-idea`](https://github.com/almasix-dev/almasix-idea) |

The former monorepo [`almasix-dev/ide-support`](https://github.com/almasix-dev/ide-support)
is a redirect only.

Install from the **Visual Studio Marketplace**, **Open VSX** (Cursor / VSCodium),
or the **JetBrains Marketplace**, or sideload a `.vsix` / `.zip` from each
repo’s GitHub Releases.

For language features themselves, see [Prism language support](/prism-language/)
and the [Language server](/language-server/) (optional legacy path on VS Code).

## Quick path

```bash title="terminal"
# From an Almasix application root
pip install almasix
smith ide:install            # .vscode settings + JetBrains note
smith ide:stubs              # .pyi for models + route name Literal
smith ide:index --json       # symbol index (both IDEs rebuild from this)
```

Then install the editor package for your IDE (below).

## VS Code / Cursor / VSCodium

Intelligence is **native** via `smith ide:index --json` (Idea parity). Optional
legacy `almasix-lsp` when `almasix.useLsp` is enabled.

1. Install **Almasix**:
   - **VS Code** — [Visual Studio Marketplace](https://marketplace.visualstudio.com/items?itemName=almasix.almasix)
     (publisher `almasix`)
   - **Cursor / VSCodium / Windsurf** — [Open VSX](https://open-vsx.org/extension/almasix/almasix)
     (Extensions search), or **Install from VSIX…**
   - Any client — `.vsix` from [`almasix-vscode` Releases](https://github.com/almasix-dev/almasix-vscode/releases)
2. Open a folder that contains `bootstrap/app.py`
3. Confirm the status bar shows **Almasix · N routes · M views**
4. Optional — Prism explorer icons: **File Icon Theme → Almasix File Icons**
   (Seti/Material often show an HTML icon for `*.prism.html` otherwise)

Settings written by `smith ide:install`:

- `files.associations`: `*.prism.html` → `prism-html`
- `almasix.pythonPath`: `${workspaceFolder}/.venv/bin/python`
- Emmet / format-on-save for Prism

Commands: **Almasix: Rebuild Index**, **New…**, **New Model…**, **Show Application Info**.

Full guide: [`almasix-vscode` README](https://github.com/almasix-dev/almasix-vscode#readme)
(architecture, features, settings, troubleshooting). Parity with JetBrains:
[PARITY.md](https://github.com/almasix-dev/almasix-vscode/blob/main/PARITY.md).

## JetBrains (PyCharm / WebStorm)

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
   [`almasix-idea` Releases](https://github.com/almasix-dev/almasix-idea/releases)
   (plugin **0.3.2+**; PyCharm / WebStorm only).
2. Restart; open an Almasix app whose **project** interpreter has Almasix
   installed (or a `.venv` next to `bootstrap/app.py`).

`smith ide:install` also writes `.idea/almasix-editor.md` with these steps.

Full guide: [`almasix-idea` README](https://github.com/almasix-dev/almasix-idea#readme)
(architecture, features, menus, troubleshooting).

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
components, validation rules, and related symbols. Both IDEs cache / rebuild
from this dump (VS Code optionally still uses `almasix-lsp` when enabled).

## VS Code ↔ PyCharm parity

| Surface | VS Code | JetBrains |
| --- | --- | --- |
| Prism file type / highlighting | `prism-html` TextMate | Native Prism + HTML layer |
| Language intelligence | Native index (`ide:index`) | Native Kotlin + `ide:index` |
| `smith` run configs | Task provider | Smith run configuration |
| Marketplace | VS Marketplace + Open VSX | JetBrains Marketplace |

Packaging and Marketplace publish live in
[`almasix-vscode`](https://github.com/almasix-dev/almasix-vscode) and
[`almasix-idea`](https://github.com/almasix-dev/almasix-idea).
