---
title: Language server
description: almasix-lsp — completions, diagnostics, hover, and go-to-definition for Almasix apps.
---

**`almasix-lsp`** is the first-party language server for Almasix. One
implementation serves every editor that speaks LSP: VS Code / Cursor, Neovim,
Helix, Zed, Sublime, and PyCharm (via its LSP client).

It boots your application the same way Smith does, then answers questions a
type checker cannot: which views exist, which routes are named, which config
keys were loaded.

## Install

```bash
pip install 'almasix[lsp]'
# or with the full dev set
pip install 'almasix[dev]'
```

Both extras pull in `pygls` and `lsprotocol` (Python 3.11–3.13).

## Run the server

Any of these starts the stdio language server:

```bash
almasix-lsp
python -m almasix.lsp
smith lsp:serve          # from an application root
```

Editors launch the binary with the project virtualenv on `PATH`. Point the
client at the app root (the directory that contains `bootstrap/app.py`).

## What it indexes

On initialize (and again on save / `almasix.rebuildIndex`), the server:

1. Finds `bootstrap/app.py` (walks up from the workspace root; multi-root
   workspaces pick the first folder that contains one)
2. Boots the application — prefers `bootstrap.app.application` so middleware
   aliases match the HTTP kernel
3. Collects:
   - **Views** — every `*.prism.html` under `resources/views` (dotted names)
   - **Named routes** — from the live router, with best-effort file/line from
     `routes/*.py` (falls back to `web.py` / `api.py`)
   - **Config keys** — flattened dotted keys from `config/*.py`
   - **Models** — module stems under `app/models`
   - **Translation keys** — from `lang/<locale>/*.py`, `lang/<locale>.json`,
     and best-effort PHP arrays when `lang/` exists
   - **Middleware aliases** — framework defaults plus
     `http.middleware_aliases` from bootstrap

If boot fails, the client gets a clear error message instead of a silent empty
index.

## Capabilities

| Feature | Surfaces |
| --- | --- |
| **Completion** | `view("…")`, `@include` / `@extends`, `route("…")`, `config("…")`, `__()` / `trans()` / `@lang`, `.middleware("…")` |
| **Diagnostics** | Unknown `view("…")`; unknown translation keys when `lang/` is present |
| **Hover** | Prism directives (static docs table); route / view / config / translation / middleware strings |
| **Go to definition** | `view("foo.bar")` → template; `route("name")` → routes file; `config("app.x")` → `config/app.py` |
| **Find references** | View names — `view("…")` / `@include` / `@extends` across the app |
| **Document links** | View, route, and config string arguments |
| **Code actions** | Create missing view (empty `.prism.html`) for unknown-view diagnostics |

Trigger characters: `"`, `'`, `.`, `@`.

Rebuild the index from the client with the `almasix.rebuildIndex` command, or
by saving a document. Creating a view via the code action refreshes the index.

## Editor wiring

### VS Code / Cursor / VSCodium

Install the official extension from a local VSIX (see [Editor setup](/editor-setup/)):

```bash
cd editors/vscode && npm install && npm run package
# Extensions → Install from VSIX… → almasix-*.vsix
```

Or, until the extension is installed, a minimal `settings.json`:

```json
{
  "almasix.pythonPath": "${workspaceFolder}/.venv/bin/python"
}
```

Associate `*.prism.html` with language id `prism-html` so hover on directives works
(see [Prism language support](/prism-language/)).

### Neovim (nvim-lspconfig)

```lua
vim.lsp.config("almasix_lsp", {
  cmd = { "almasix-lsp" },
  filetypes = { "python", "html" },
  root_markers = { "bootstrap/app.py" },
})
vim.lsp.enable("almasix_lsp")
```

### Helix

```toml
[language-server.almasix-lsp]
command = "almasix-lsp"

[[language]]
name = "python"
language-servers = ["almasix-lsp", "pylsp"]
```

### Zed

```json
{
  "languages": {
    "Python": {
      "language_servers": ["almasix-lsp", "..."]
    }
  },
  "lsp": {
    "almasix-lsp": {
      "binary": { "path": "almasix-lsp" }
    }
  }
}
```

## Library API

```python
from almasix.lsp import build_index, create_server, find_app_root

index = build_index("/path/to/app")   # or find_app_root()
print(len(index.views), len(index.routes), len(index.config_keys))

server = create_server()              # pygls LanguageServer
# server.start_io()
```

`build_index` is usable without starting the LSP process — the progress demo
uses it directly.

## Demo

From `examples/progress`:

```bash
smith progress:lsp
```

Prints view / route / config / model / middleware / translation counts and
`lsp ok`.

## Scope notes

Shipped for day-to-day editing: views, routes, config, translations,
middleware aliases, find-references for views, and a create-view code action.
Still on the roadmap: disk / queue / cache / gate / relation / column /
component completions, Prism structural diagnostics, rename, Starlight-sourced
hover, and filesystem watchers. Editor packaging is on [Editor setup](/editor-setup/).
