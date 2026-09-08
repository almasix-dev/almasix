---
title: Components & Slots
description: "Anonymous and class-based components, named slots, attribute bags, @props, and @aware."
---

# Components & Slots

## Anonymous components

Place templates under `resources/views/components/`:

```html
<!-- resources/views/components/alert.prism.html -->
@props({"type": "info"})
<div class="alert alert-{{ type }}" {{ attributes }}>
  {{ slot }}
</div>
```

Scaffold with:

```bash
smith make:component alert
smith make:component forms/input --class
```

### Class tag syntax

```html
<!-- resources/views/welcome.prism.html -->
<x-alert type="success">Saved.</x-alert>
```

Dynamic attributes use colon bindings:

```html
<!-- resources/views/welcome.prism.html -->
<x-link :href="board_url">Board</x-link>
```

### Directive syntax

```html
<!-- resources/views/welcome.prism.html -->
@component("alert", {"type": "success"})
  Saved.
@endcomponent
```

## Named slots

```html
<!-- resources/views/welcome.prism.html -->
@component("card")
  @slot("title")
    Hello
  @endslot
  Body copy
@endcomponent
```

Or with tag syntax:

```html
<!-- resources/views/welcome.prism.html -->
<x-card>
  <x-slot:title>Hello</x-slot>
  Body copy
  <x-slot name="footer">Meta</x-slot>
</x-card>
```

```html
<!-- resources/views/components/card.prism.html -->
<h2>{{ title }}</h2>
<div>{{ slot }}</div>
@if('footer' in slots)
  <footer>{{ footer }}</footer>
@endif
```

Slot HTML is safe (not double-escaped) when echoed with `{{ slot }}`.

## Nested components

`<x-*>` tags nest. Innermost tags expand first:

```html
<!-- resources/views/welcome.prism.html -->
<x-card>Hi <x-badge>new</x-badge></x-card>
```

## `@aware` (parent → child)

Child components can pull data from the parent component scope:

```html
<!-- resources/views/components/form.prism.html -->
@props({"method": "post"})
<form method="{{ method }}">{{ slot }}</form>
```

```html
<!-- resources/views/components/input.prism.html -->
@aware(["method"])
@props({"name": "field"})
<input name="{{ name }}" data-method="{{ method }}">
```

Explicit child attributes win over aware data. Aliases use a dict:
`@aware({"form_method": "method"})`.

## Class-based components

```python
# app/view/components/alert.py
from almasix.prism import Component

class Alert(Component):
    def __init__(self, type: str = "info") -> None:
        self.type = type

    def render(self) -> str:
        return "components.alert"
```

`<x-alert>` resolves the class under `app.view.components` first, then falls
back to the anonymous view. Constructor kwargs become view data; leftover HTML
attributes remain on `attributes`.

## Attribute bags

`attributes` is an `AttributeBag`: `merge()`, `except_()`, `only()`, and stringifies
to HTML attributes for `{{ attributes }}` / `{!! attributes !!}`.
