# Almasix for VS Code / Cursor / VSCodium

Prism highlighting + snippets + **almasix-lsp** client. Marketplace publish is
not required — install the `.vsix` from this repo.

## Install from VSIX (sideload)

1. Build the package (from the Almasix repo):

   ```bash
   cd editors/vscode
   npm install
   npm run package
   ```

   That runs `npx @vscode/vsce package` (vsce does **not** need a global
   install) and writes `almasix-0.x.x.vsix` in this directory.

2. In VS Code / Cursor / VSCodium:

   - Open **Extensions**
   - `⋯` / **Views and More Actions** → **Install from VSIX…**
   - Choose `editors/vscode/almasix-*.vsix`

3. Open an Almasix app (directory with `bootstrap/app.py`). Ensure the project
   venv has the language server:

   ```bash
   pip install 'almasix[lsp]'
   # or: pip install -e '.[lsp]' from the framework checkout
   ```

4. Optional: run `smith ide:install` in the app to write `.vscode/settings.json`
   (Prism associations + python path) and `extensions.json`.

## Settings

| Setting | Meaning |
| --- | --- |
| `almasix.pythonPath` | Interpreter with `almasix[lsp]` (default: `${workspaceFolder}/.venv/bin/python`) |
| `almasix.lsp.command` | Full override for the LSP executable |
| `almasix.lsp.args` | Extra argv for the server |

If the server cannot start, the status bar shows **Almasix: LSP missing** (or
**failed**) with a clear message.

## Commands

- **Almasix: Rebuild LSP Index** → `almasix.rebuildIndex`
- **Almasix: Show Application Info** → `almasix.showAppInfo`
- **Almasix: Restart Language Server**

## Language id

`.prism.html` files use language id **`prism-html`** (TextMate grammar from
`editors/prism/`).

## Develop

```bash
npm install
npm run compile   # or npm run watch
# Press F5 in VS Code with this folder open to launch an Extension Development Host
```

Sync Prism assets from `editors/prism/` before packaging:

```bash
npm run sync-prism
```
