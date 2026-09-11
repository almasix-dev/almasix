---
title: Layouts & Inheritance
description: "Extend layouts with @extends, @section, @yield, and @parent."
---

# Layouts & Inheritance

Prism layouts use `@extends`, `@section`, and `@yield`.

## Yielding sections

```html title="resources/views/layouts/app.prism.html"
<html>
  <head>
    <title>@yield("title", "Almasix")</title>
  </head>
  <body>
    @yield("content")
    @stack("scripts")
  </body>
</html>
```

## Extending a layout

```html title="resources/views/home.prism.html"
@extends("layouts.app")

@section("title", "Home")

@section("content")
  <p>Welcome.</p>
  @push("scripts")
    <script src="{{ asset('home.js') }}"></script>
  @endpush
@endsection
```

## `@parent`

When a child overrides a section that an intermediate layout already defined,
`@parent` inserts the parent section’s content:

```html title="resources/views/home.prism.html"
@section("content")
  @parent
  <p>Extra for this page.</p>
@endsection
```
