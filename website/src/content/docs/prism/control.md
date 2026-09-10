---
title: Control Structures
description: "Conditionals, loops, and @python blocks in Prism."
---

# Control Structures

| Directive | Role |
| --- | --- |
| `@if` / `@elseif` / `@else` / `@endif` | Conditionals |
| `@unless` / `@endunless` | Inverted conditional |
| `@isset(expr)` / `@endisset` | Body when `expr` evaluates to not `None` |
| `@empty(expr)` / `@endempty` | Body when `expr` is empty / falsy |
| `@foreach(items as item)` / `@endforeach` | Loop with `loop` helpers |
| `@forelse` / `@empty` / `@endforelse` | Loop or empty state |
| `@for` / `@endfor` | C-style (`i = 0; i < n; i++`) or Python (`i in range(n)`) |
| `@while` / `@endwhile` | While loop |
| `@auth` / `@endauth` | Body when `auth_user` or `__authenticated` is set |
| `@guest` / `@endguest` | Inverse of `@auth` |
| `@can` / `@cannot` / `@canany` / `@cannotany` | Gate / policy checks — see [Authorization](/authorization/) |
| `@python` / `@endpython` | Escape hatch |

## Loop variable

Inside `@foreach` / `@forelse`, `loop` exposes:
`index`, `iteration`, `remaining`, `count`, `first`, `last`, `even`, `odd`, `depth`, `parent`.

```html
<!-- resources/views/welcome.prism.html -->
@foreach(users as user)
  <li @if(loop.first)class="first"@endif>{{ user.name }}</li>
@endforeach

@for(i = 0; i < 3; i++)
  <li>Item {{ i + 1 }}</li>
@endfor

@for(i in range(3))
  <li>Item {{ i + 1 }}</li>
@endfor
```

Bare `@empty` inside `@forelse` remains the empty branch. Standalone
`@empty(expr)` … `@endempty` is a separate empty-check directive.

## Auth and authorization

```html
<!-- resources/views/partials/nav.prism.html -->
@auth
  <p>Welcome back</p>
@endauth

@guest
  <a href="/login">Sign in</a>
@endguest

@can('update', post)
  <a href="/edit">Edit</a>
@endcan
```

`@can` / `@cannot` / `@canany` call the [authorization](/authorization/) gate.

## Localization in views

```html
<!-- resources/views/welcome.prism.html -->
@lang("messages.welcome", {"name": name})
{{ __("messages.welcome", {"name": name}) }}
```

`__`, `trans`, and `trans_choice` are injected into every template context.
