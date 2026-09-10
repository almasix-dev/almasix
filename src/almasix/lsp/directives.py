"""Static hover documentation for Prism directives."""

from __future__ import annotations

# Keep this table in sync with the compiler / Starlight Prism docs. Full
# Starlight sourcing lands with broader IDE work; these strings are the M46
# baseline so hover never depends on a running docs site.
PRISM_DIRECTIVES: dict[str, str] = {
    "if": "`@if(condition)` — conditional block; close with `@endif`.",
    "elseif": "`@elseif(condition)` — else-if branch inside `@if`.",
    "else": "`@else` — final branch inside `@if` / `@unless`.",
    "endif": "`@endif` — closes an `@if` block.",
    "unless": "`@unless(condition)` — inverted conditional; close with `@endunless`.",
    "endunless": "`@endunless` — closes an `@unless` block.",
    "isset": "`@isset(name)` — true when the variable is set; `@endisset`.",
    "endisset": "`@endisset` — closes an `@isset` block.",
    "empty": "`@empty(name)` — true when the value is empty; `@endempty`.",
    "endempty": "`@endempty` — closes an `@empty` block.",
    "for": "`@for(…)` — C-style for loop; close with `@endfor`.",
    "endfor": "`@endfor` — closes an `@for` block.",
    "foreach": "`@foreach(items as item)` — iterate a collection; `@endforeach`.",
    "endforeach": "`@endforeach` — closes an `@foreach` block.",
    "forelse": "`@forelse(items as item)` — foreach with `@empty` / `@endforelse`.",
    "endforelse": "`@endforelse` — closes an `@forelse` block.",
    "while": "`@while(condition)` — while loop; `@endwhile`.",
    "endwhile": "`@endwhile` — closes an `@while` block.",
    "extends": "`@extends('layout')` — inherit a layout view.",
    "section": "`@section('name')` — define a layout section; `@endsection` / `@show`.",
    "endsection": "`@endsection` — closes a `@section` block.",
    "show": "`@show` — closes a section and yields it immediately.",
    "yield": "`@yield('name')` — render a section from a child view.",
    "parent": "`@parent` — include the parent section body.",
    "include": "`@include('partial')` — render another view inline.",
    "includeIf": "`@includeIf(cond, 'partial')` — include when the condition is true.",
    "includeWhen": "`@includeWhen(cond, 'partial')` — alias of include-if.",
    "includeUnless": "`@includeUnless(cond, 'partial')` — include when false.",
    "each": "`@each('view', items, 'item')` — render a view once per item.",
    "component": "`@component('name')` — class / anonymous component; `@endcomponent`.",
    "endcomponent": "`@endcomponent` — closes a `@component` block.",
    "slot": "`@slot('name')` — named slot body; `@endslot`.",
    "endslot": "`@endslot` — closes a `@slot` block.",
    "props": "`@props({…})` — declare component props with defaults.",
    "aware": "`@aware(['prop'])` — pull props from a parent component.",
    "push": "`@push('stack')` — append to a stack; `@endpush`.",
    "endpush": "`@endpush` — closes a `@push` block.",
    "prepend": "`@prepend('stack')` — prepend to a stack; `@endprepend`.",
    "endprepend": "`@endprepend` — closes a `@prepend` block.",
    "stack": "`@stack('name')` — render a named stack.",
    "once": "`@once` — render the body only once per request; `@endonce`.",
    "endonce": "`@endonce` — closes an `@once` block.",
    "python": "`@python` — embedded Python block; `@endpython`.",
    "endpython": "`@endpython` — closes a `@python` block.",
    "csrf": "`@csrf` — hidden CSRF token field.",
    "error": "`@error('field')` — validation error block; `@enderror`.",
    "enderror": "`@enderror` — closes an `@error` block.",
    "auth": "`@auth` — render when authenticated; `@endauth`.",
    "endauth": "`@endauth` — closes an `@auth` block.",
    "guest": "`@guest` — render for guests; `@endguest`.",
    "endguest": "`@endguest` — closes a `@guest` block.",
    "can": "`@can('ability')` — authorization gate; `@endcan`.",
    "endcan": "`@endcan` — closes a `@can` block.",
    "cannot": "`@cannot('ability')` — inverted gate; `@endcannot`.",
    "endcannot": "`@endcannot` — closes a `@cannot` block.",
    "canany": "`@canany([…])` — any-of abilities; `@endcanany`.",
    "endcanany": "`@endcanany` — closes a `@canany` block.",
    "cannotany": "`@cannotany([…])` — none-of abilities; `@endcannotany`.",
    "endcannotany": "`@endcannotany` — closes a `@cannotany` block.",
    "lang": "`@lang('key')` — translate a key.",
    "choice": "`@choice('key', count)` — pluralized translation.",
    "asset": "`@asset('path')` — asset URL helper.",
    "route": "`@route('name')` — named route URL.",
    "signedRoute": "`@signedRoute('name')` — signed named route URL.",
    "vite": "`@vite(['app.js'])` — Vite entry tags.",
    "viteReactRefresh": "`@viteReactRefresh` — Vite React refresh preamble.",
    "cache": "`@cache(…)` — fragment cache; `@endcache`.",
    "endcache": "`@endcache` — closes a `@cache` block.",
    "dump": "`@dump(value)` — dump a value into the response.",
    "dd": "`@dd(value)` — dump and stop rendering.",
}


def directive_hover(name: str) -> str | None:
    """Return markdown hover text for a directive name (without ``@``)."""
    key = name[1:] if name.startswith("@") else name
    text = PRISM_DIRECTIVES.get(key)
    if text is None:
        return None
    return f"**@{key}**\n\n{text}"
