---
title: Including Subviews
description: "Compose templates with @include and related directives."
---

# Including Subviews

```html title="resources/views/layouts/app.prism.html"
@include("partials.nav")
```

Pass a second argument to merge data into the child context (parent data is
copied first):

```html title="resources/views/layouts/app.prism.html"
@include("partials.alert", {"type": "success", "message": message})
```

## Conditional includes

| Directive | Behavior |
| --- | --- |
| `@includeIf("view")` | Include only when the view exists on disk |
| `@includeWhen(cond, "view")` | Include when `cond` is truthy |
| `@includeUnless(cond, "view")` | Include when `cond` is falsy |

Optional data dicts work the same way as `@include` (second arg for
`@includeIf`, third for when/unless).

```html title="resources/views/layouts/app.prism.html"
@includeIf("partials.banner")
@includeWhen(user, "partials.account", {"user": user})
@includeUnless(preview, "partials.footer")
```

## Rendering collections with `@each`

```html title="resources/views/welcome.prism.html"
@each("partials.job", jobs, "job")
@each("partials.job", jobs, "job", "partials.no-jobs")
```

Prism renders the first view once per item (binding the item under the
given variable name). When the collection is empty and a fourth view is
provided, that empty view is rendered instead.
