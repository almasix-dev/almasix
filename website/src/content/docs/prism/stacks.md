---
title: Stacks & Custom Directives
description: "@push, @prepend, @stack, @once, and Engine.directive()."
---

# Stacks & Custom Directives

## Stacks

Push fragments from a child view; flush them in the layout (usually **after**
`@yield` so pushes from sections are visible):

```html
<!-- resources/views/layouts/app.prism.html -->
@yield("content")
@stack("scripts")

<!-- resources/views/home.prism.html -->
@push("scripts")
  <script src="{{ asset('app.js') }}"></script>
@endpush
```

| Directive | Role |
| --- | --- |
| `@push` / `@endpush` | Append to a named stack |
| `@prepend` / `@endprepend` | Prepend to a named stack |
| `@stack("name")` | Render the stack |
| `@once` / `@endonce` | Render the block only once per request |

## Framework stubs

```html
<!-- resources/views/auth/login.prism.html -->
@csrf
@asset("css/app.css")

@error("email")
  <span class="error">{{ message }}</span>
@enderror
```

- `@csrf` emits a hidden `_token` input from `context["csrf_token"]` (empty until sessions land).
- `@error("field")` shows the block when `errors` is a field→messages mapping; `message` is the first error string.
- `@asset(...)` calls the injected `asset()` helper (subpath-aware).

## Debugging

Dump helpers for views:

```html
<!-- resources/views/debug.prism.html -->
@dump(user)
@dump(user, request)
@dd(board)
```

| Directive | Behavior |
| --- | --- |
| `@dump(...)` | Embeds a styled HTML dump card in the page; rendering continues |
| `@dd(...)` | Halts with Almasix's dump page (same as `from almasix import dd`) |

Also available in Python as `from almasix import dump, dd`. See [Smith Console](/console/#dump--dd).

## Custom directives

Register handlers on the engine (or `ViewFactory.directive`). The handler
receives the expression inside the parentheses (or `""`) and returns Python
source lines to emit into the compiled render function:

```python
# app/providers/view_service_provider.py
engine.directive(
    "datetime",
    lambda expr: f"__w(__e(str(__eval({expr!r}))))",
)
```

```html
<!-- resources/views/welcome.prism.html -->
@datetime(now.isoformat())
```

## Composers, creators, and fragment cache

```python
# app/providers/view_service_provider.py
engine.composer("profile.*", lambda ctx: ctx.setdefault("title", "Profile"))
engine.creator(["dashboard", "dashboard.*"], seed_once)

# In a template:
# @cache("sidebar") ... @endcache
engine.cache_views()  # warm compile cache
engine.clear_cache()  # compiled views + fragments + creators
```
