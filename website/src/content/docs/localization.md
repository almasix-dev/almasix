---
title: Localization
description: Language catalogs, __ / trans / trans_choice, plurals, locales, and Number helpers.
---

## Introduction

Almasix’s localization features retrieve strings in various languages so an
application can support more than one locale. Catalogs live under the app’s
`lang/` directory. Groups use short keys in Python files; JSON catalogs use the
default English string as the key — the same two approaches Laravel documents.

```text
lang/
  en/
    messages.py
    validation.py
  sw/
    messages.py
  en.json
  sw.json
```

Prism views can call the same helpers: `@lang`, `__`, `trans`, and
`trans_choice` are injected into every template. See
[Control Structures](/prism/control/#localization-in-views).

### Publishing the language files

Scaffolded apps may ship a thin `lang/` tree. To publish the framework’s English
catalogs (`validation`, `auth`, `passwords`, `pagination`, `errors`) into the
application:

```shell
python smith lang:publish
```

Create an empty tree for a new locale:

```shell
python smith make:lang sw
```

Report keys present in the fallback locale but missing from a target:

```shell
python smith lang:missing --locale=sw
```

### Configuring the locale

The default and fallback locales come from `config/app.py`, typically via the
environment:

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_LOCALE` | `en` | Active locale when none is set on the request |
| `APP_FALLBACK_LOCALE` | `en` | Used when the active locale lacks a key |

```python title="config/app.py"
from almasix.config import env

config = {
    "locale": env("APP_LOCALE", "en"),
    "fallback_locale": env("APP_FALLBACK_LOCALE", "en"),
    # ...
}
```

Change the locale for the current request (ASGI-scoped — not process-global):

```python title="examples/localization.py"
from almasix.translation import set_locale, get_locale, is_locale

set_locale("sw")
get_locale()       # "sw"
is_locale("sw")    # True
```

Or through the `Lang` façade:

```python title="examples/localization.py"
from almasix.translation import Lang

Lang.set_locale("sw")
Lang.get_locale()
Lang.set_fallback("en")
```

`SetLocaleMiddleware` negotiates the locale when nothing was set earlier in the
pipeline: session key `locale` first, then `Accept-Language`, then the config
default. Alias it (often as `locale`) after session middleware on web routes:

```python title="bootstrap/app.py"
from almasix.translation import SetLocaleMiddleware

middleware.alias({"locale": SetLocaleMiddleware})
```

## Defining translation strings

### Using short keys

Place a Python file per group under `lang/<locale>/`. The module exposes a
`translations` dict (nested keys are fine):

```python title="lang/en/messages.py"
translations = {
    "welcome": "Welcome to our application!",
    "hello": "Hello, :name",
}
```

```python title="lang/sw/messages.py"
translations = {
    "welcome": "Karibu kwenye programu yetu!",
    "hello": "Habari, :name",
}
```

For languages that differ by territory, name directories with underscores
(`en_GB`), matching common locale tags.

### Using translation strings as keys

For apps with many UI strings, store the default wording as the JSON key:

```json title="lang/sw.json"
{
  "I love Almasix.": "Napenda Almasix."
}
```

Do not invent short keys that collide with a group filename. Looking up
`__("Action")` while `lang/nl/action.py` exists (and no `nl.json`) can resolve
as the whole group file rather than a JSON line.

## Retrieving translation strings

Use `__` or `trans` with dotted `file.key` for group catalogs, or the literal
string for JSON catalogs:

```python title="examples/localization.py"
from almasix.translation import __, trans, Lang

__("messages.welcome")
trans("messages.welcome")
Lang.get("messages.welcome")

__("I love Almasix.")
```

If the key is missing in the active locale and the fallback, the helpers return
the key itself — never blank, never an exception.

In Prism:

```html title="resources/views/welcome.prism.html"
@lang("messages.welcome")
{{ __("messages.welcome", {"name": name}) }}
```

### Replacing parameters

Placeholders are prefixed with `:`. Pass replacements as the second argument:

```python title="lang/en/messages.py"
translations = {
    "welcome": "Welcome, :name",
}
```

```python title="examples/localization.py"
__("messages.welcome", {"name": "Ada"})
# Welcome, Ada
```

Placeholder case follows Laravel:

| Placeholder | Replacement |
| --- | --- |
| `:name` | as given |
| `:NAME` | uppercased |
| `:Name` | first letter uppercased |

```python title="lang/en/messages.py"
translations = {
    "welcome": "Welcome, :NAME",   # Welcome, ADA
    "goodbye": "Goodbye, :Name",   # Goodbye, Ada
}
```

### Pluralization

Separate singular and plural (or more forms) with `|`. Retrieve with
`trans_choice` / `Lang.choice`:

```python title="lang/en/messages.py"
translations = {
    "apples": "There is one apple|There are many apples",
}
```

```python title="examples/localization.py"
from almasix.translation import trans_choice

trans_choice("messages.apples", 10)
```

Interval forms and explicit counts work the same as Laravel:

```python title="lang/en/messages.py"
translations = {
    "apples": "{0} There are none|[1,19] There are some|[20,*] There are many",
    "minutes_ago": "{1} :value minute ago|[2,*] :value minutes ago",
}
```

```python title="examples/localization.py"
trans_choice("messages.minutes_ago", 5, {"value": 5})
```

`:count` is injected automatically from the number passed to `trans_choice`.

When a string has more than two segments without intervals, Almasix selects by
**CLDR plural categories** for the active locale (via Babel) — `zero` / `one` /
`two` / `few` / `many` / `other` — not English-only one/other pretending to be
universal.

JSON catalogs support pipe plurals as values as well:

```json title="lang/sw.json"
{
  "There is one apple|There are many apples": "Kuna tofaa moja|Kuna matofaa mengi"
}
```

### Checking for keys

```python title="examples/localization.py"
from almasix.translation import Lang

Lang.has("messages.welcome")
Lang.has_for_locale("messages.welcome", "sw")  # no fallback
```

### Missing-key hooks

Optionally register a callback when a key cannot be resolved (default still
returns the key):

```python title="app/providers/app_service_provider.py"
from almasix.translation import Lang

Lang.handle_missing_keys_using(
    lambda key, locale, replace: f"[missing:{key}]"
)
```

### Namespaces and package catalogs

Packages register a namespace; look up with `package::file.key`:

```python title="examples/localization.py"
from almasix.translation import Lang, __

Lang.add_namespace("acme", "/path/to/acme/lang")
__("acme::messages.welcome")
```

Runtime lines without a file:

```python title="examples/localization.py"
Lang.add_lines({"flash": "Saved"}, locale="en", namespace="*")
```

## Overriding package language files

To override a package’s strings without editing the package, place files under
`lang/vendor/<package>/<locale>/`:

```text
lang/vendor/acme/en/messages.py
```

Only define the keys you want to change; everything else still loads from the
package catalog.

## Locale-aware numbers and dates

`almasix.translation.Number` formats values with Babel using the active (or
given) locale — the localization counterpart to the support
[Helpers](/helpers/#numbers) `Number` utilities:

```python title="examples/localization.py"
from almasix.translation import Number, localize_date, localize_time, set_locale
from datetime import datetime

set_locale("de")
Number.format(1234.5)
Number.percentage(10)           # "10%"
Number.currency(99.9, "EUR")
Number.file_size(1_500_000)
Number.for_humans(1_500_000)

localize_date(datetime.now(), format="medium")
localize_time(datetime.now(), format="short")
```

## Related

- [Validation](/validation/) — published validation catalogs
- [Strings](/strings/) — `Str` / `Stringable` (not translation catalogs)
- [Middleware](/middleware/) — registering `SetLocaleMiddleware`
- [Prism Control Structures](/prism/control/#localization-in-views)
- [Structure](/structure/) — the `lang` directory
