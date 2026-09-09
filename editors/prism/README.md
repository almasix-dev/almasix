# Prism language support

Editor assets for Almasix **Prism** templates (``.prism.html``): TextMate grammar,
language configuration, snippets, a minimal tree-sitter grammar, and the
``smith prism:format`` CLI (library: ``almasix.prism.formatter.format_prism``).

Full packaging into VS Code / JetBrains extensions is **M47**. This directory is
the shared source those extensions will ship.

## VS Code / Cursor (manual load)

Until the Almasix extension is installed, associate the grammar locally:

1. Copy or symlink this folder somewhere durable, or open the Almasix repo.
2. In user or workspace ``settings.json``:

```json
{
  "files.associations": {
    "*.prism.html": "html"
  }
}
```

For a proper language id with this grammar, use a tiny local extension
``package.json`` contribution (or wait for M47):

```json
{
  "contributes": {
    "languages": [
      {
        "id": "prism",
        "aliases": ["Prism", "prism"],
        "extensions": [".prism.html"],
        "configuration": "./language-configuration.json"
      }
    ],
    "grammars": [
      {
        "language": "prism",
        "scopeName": "text.html.prism",
        "path": "./syntaxes/prism.tmLanguage.json",
        "embeddedLanguages": {
          "source.python": "python",
          "text.html.basic": "html"
        }
      }
    ],
    "snippets": [
      {
        "language": "prism",
        "path": "./snippets/prism.code-snippets"
      }
    ]
  }
}
```

Point ``configuration`` / ``path`` entries at the files in this directory
(absolute or relative to the extension root).

Comment toggle uses ``{{--`` / ``--}}``. Folding and indentation rules live in
``language-configuration.json``.

## Formatter CLI

```bash
# Write formatted .prism.html under the given path (default: cwd)
smith prism:format
smith prism:format resources/views
smith prism:format resources/views/welcome.prism.html

# CI: fail if any file would change
smith prism:format --check
```

Library entry point (same implementation):

```python
from almasix.prism.formatter import format_prism

print(format_prism(source, indent_size=4, line_length=120))
```

The formatter is **idempotent** and **directive-aware**. Content inside
``@python`` … ``@endpython`` is left untouched (not reindented).

## Tree-sitter

See ``tree-sitter-prism/grammar.js``. Optional build:

```bash
npm install -g tree-sitter-cli
cd tree-sitter-prism
tree-sitter generate
tree-sitter build
```

Highlight queries: ``tree-sitter-prism/queries/highlights.scm``.

## Layout

| Path | Role |
| --- | --- |
| ``syntaxes/prism.tmLanguage.json`` | TextMate grammar |
| ``language-configuration.json`` | Comments, brackets, folding, indent |
| ``snippets/prism.code-snippets`` | Directive + ``x-component`` snippets |
| ``tree-sitter-prism/`` | Minimal tree-sitter grammar + queries |
