---
title: Views
description: Render HTML with Prism from controllers and routes.
---

A **view** turns data from a controller into HTML. Almasix’s view engine is
**Prism**: templates under `resources/views` with a `.prism.html` extension,
compiled to Python and cached in the process. This page is the overview; the
full Prism tutorial lives under [Prism](/prism/).

## Creating and returning views

```python
# app/http/controllers/welcome_controller.py
from almasix.prism import view


async def index(self):
    return view("welcome", {"title": "Almasix"})
```

Templates live under `resources/views`. Dots map to directories: `view("posts.show")` → `resources/views/posts/show.prism.html`.

```html
<!-- resources/views/welcome.prism.html -->
@extends("layouts.app")

@section("content")
  <h1>{{ title }}</h1>
@endsection
```

## Passing data

The second argument to `view()` is a dict of template data. Helpers such as `url`, `asset`, `e`, and `__` are injected automatically for Prism templates.

## Escaping

- `{{ value }}` — HTML-escaped (safe default)
- `{!! value !!}` — raw HTML (only when you trust the content)

## When to use `html()`

[`html()`](/responses/) is for small hand-built fragments or low-level responses. Prefer `view()` for pages, layouts, and components.

## Deep dive

This Basics page is the entry point. Full Prism documentation lives in its own section:

- [Prism](/prism/) — overview
- [Rendering Views](/prism/rendering/)
- [Layouts & Inheritance](/prism/layouts/)
- [Components & Slots](/prism/components/)
- [Control Structures](/prism/control/)
- [Including Subviews](/prism/includes/)
- [Stacks & Directives](/prism/stacks/)

## Related

- [Responses](/responses/)
- [Asset Bundling](/asset-bundling/)
- [URL Generation](/urls/)
