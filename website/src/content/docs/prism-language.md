---
title: Prism language support
description: TextMate and tree-sitter grammars, snippets, and smith prism:format for .prism.html templates.
---

Prism templates use the `.prism.html` extension. Almasix ships editor assets and
a first-party formatter so every tool — editors, pre-commit, CI — shares one
implementation.

Assets live under [`editors/prism/`](https://github.com/almasix-dev/almasix/tree/main/editors/prism)
in the repository. Full VS Code / JetBrains packaging is covered separately; the
files here are the shared source.

## Grammar (TextMate)

`editors/prism/syntaxes/prism.tmLanguage.json` highlights:

- HTML host markup
- Escaped echoes `{{ … }}` and raw echoes `{!! … !!}`
- Comments `{{-- … --}}`
- `@python` / `@endpython` blocks as embedded Python
- Directives: `@if` / `@elseif` / `@else` / `@unless` / `@isset` / `@empty` /
  `@for` / `@foreach` / `@forelse` / `@while`, layout and includes,
  components and slots, stacks, auth / gates, `@csrf` / `@asset` / `@lang` /
  `@choice` / `@cache` / `@dump` / `@dd` / `@vite` / `@route`, and matching
  `@end*` closers

Scope name: `text.html.prism`.

## Language configuration

`editors/prism/language-configuration.json` sets:

- Block comments `{{--` / `--}}`
- Auto-closing pairs for echoes and brackets
- Folding markers on open / close directives
- Indentation rules for directives and HTML tags

## Snippets

`editors/prism/snippets/prism.code-snippets` covers common directives
(`@if`, `@foreach`, `@section`, `@auth`, `@python`, …) plus `<x-…>` components
and slots.

## Tree-sitter

`editors/prism/tree-sitter-prism/` is a minimal grammar that recognizes
`comment`, `echo`, `raw_echo`, `directive`, and `html_text`, with
`queries/highlights.scm` for Neovim / Helix / Zed. Build steps are documented
in `editors/prism/README.md`.

## Formatter

Library entry point:

```python
from almasix.prism.formatter import format_prism

formatted = format_prism(source, indent_size=4, line_length=120)
```

The formatter is **idempotent** and directive-aware. It indents HTML-ish
structure and Prism directives. Content between `@python` and `@endpython` is
**not** reindented.

CLI (registered by `PrismServiceProvider`):

```bash
smith prism:format                      # write under cwd
smith prism:format resources/views      # directory or file
smith prism:format --check              # CI: fail if would change
```

`--write` is the default when `--check` is not set.

## Loading in VS Code / Cursor

Until the official extension ships, associate files and point a small local
extension at the grammar — see `editors/prism/README.md` for
`files.associations` and a sample `package.json` contribution.
