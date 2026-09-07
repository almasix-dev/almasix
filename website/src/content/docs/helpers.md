---
title: Helpers
description: Arr, Number, data helpers, and miscellaneous Support utilities.
---

## Introduction

Avalon ships a Support helpers catalog under `avalon.support`. Helpers are
**not** injected into Python’s builtins and are **not** re-exported from the
`avalon` package root — import what you need:

```python
from avalon.support import Arr, Number, blank, data_get, data_set, optional, retry, tap
```

Surfaces owned by other packages stay on those packages:

| Concern | Import from |
| --- | --- |
| Config | `avalon.config` → `config`, `env` |
| Auth | `avalon.auth` → `auth`, `Gate`, `authorize` |
| Views | `avalon.caliburn` → `view` |
| Storage | `avalon.filesystem` → `storage` / `Storage` |
| Cache | `avalon.cache` → `cache` / `Cache` |
| Debug dump | `avalon` → `dump`, `dd` |
| Strings | `avalon.support` → `Str`, `Stringable`, `str_` — see [Strings](/strings/) |
| Collections | `avalon.support` → `collect`, `Collection` — see [Collections](/collections/) |

This page covers **Arr**, **data_***, **Number**, and miscellaneous utilities.

## Arrays — `Arr`

```python
from avalon.support import Arr

Arr.get({"user": {"name": "Ada"}}, "user.name")  # "Ada"
Arr.set(payload, "user.role", "admin")
Arr.dot({"a": {"b": 1}})                         # {"a.b": 1}
Arr.undot({"a.b": 1})                            # {"a": {"b": 1}}
Arr.only(payload, ["id", "email"])
Arr.except_(payload, ["password"])
Arr.pluck(users, "email", "id")
Arr.has(payload, "user.email")
Arr.first(items, lambda item: item["active"])
```

### Available methods

`accessible`, `add`, `collapse`, `cross_join`, `divide`, `dot`, `undot`,
`except_`, `only`, `exists`, `first`, `last`, `flatten`, `forget`, `get`,
`has`, `has_any`, `is_assoc`, `is_list`, `join`, `key_by`, `map`,
`map_spread`, `map_with_keys`, `pluck`, `prepend`, `prepend_keys_with`,
`pull`, `query`, `random`, `reject`, `set`, `shuffle`, `sort`, `sort_desc`,
`sort_recursive`, `take`, `to_css_classes`, `to_css_styles`, `where`,
`where_not_null`, `wrap`.

## Data helpers

Work with nested arrays and objects using dotted paths:

```python
from avalon.support import data_get, data_set, data_fill, data_forget, head, last

target = {"user": {"name": "Ada"}}

data_get(target, "user.name")           # "Ada"
data_get(target, "user.missing", None)  # None

data_set(target, "user.role", "admin")
data_fill(target, "user.role", "guest")  # no-op — already set
data_forget(target, "user.role")

head([1, 2, 3])   # 1
last([1, 2, 3])   # 3
```

## Numbers — `Number`

```python
from avalon.support import Number

Number.format(1000)                      # "1,000"
Number.currency(12.5)                    # "$12.50"
Number.percentage(12.345, precision=1)   # "12.3%"
Number.file_size(2_048)                  # "2 KB"
Number.ordinal(3)                        # "3rd"
Number.spell(21)                         # "twenty-one"
Number.for_humans(1_500_000)             # human-readable magnitude
```

Locale-aware formatting follows the application locale when configured through
the translation layer.

## Miscellaneous utilities

```python
from avalon.support import (
    blank, filled, value, tap, with_, when, transform,
    optional, retry, once, rescue, throw_if, throw_unless,
    abort, abort_if, abort_unless, e, class_basename, now, today,
    base_path, app_path, config_path, database_path, resource_path,
    storage_path, public_path, lang_path,
)

blank(None)          # True
blank("")            # True
filled("Ada")        # True

value(lambda: 42)    # 42
tap(user, lambda u: u.touch())
with_(payload, lambda p: p["id"])

optional(user).email           # None-safe attribute access
retry(3, lambda: fetch())      # retry with optional sleep
once(lambda: load_config())    # memoize on the callable itself
rescue(lambda: risky(), default=None)

throw_if(not ok, ValueError("nope"))
abort(404)                     # raise HTTP exception
abort_if(missing, 404)

e("<b>Ada</b>")                # HTML-escape
class_basename(User)           # "User"
now()                          # UTC datetime
today()                        # UTC date

base_path("storage/logs")
app_path("models")
public_path("css/app.css")
```

| Helper | Role |
| --- | --- |
| `blank` / `filled` | Empty-ish checks |
| `value` | Resolve callables |
| `tap` / `with_` | Pass-through / transform |
| `when` / `transform` | Conditional values |
| `optional` | Null-safe proxy |
| `retry` / `retry_async` | Retry with optional sleep |
| `once` | Memoize a callable on itself |
| `rescue` | Catch → default |
| `throw_if` / `throw_unless` | Conditional raise |
| `abort` / `abort_if` / `abort_unless` | HTTP abort |
| `e` | HTML escape |
| `class_basename` | Trailing class segment |
| `now` / `today` | UTC datetime / date |
| `base_path` / `app_path` / … | Path helpers (app-rooted) |
| `preg_replace_array` | Sequential regex replacements |
| `report_exception` / `report_if` / `report_unless` | Report without always raising |

## Related

- [Strings](/strings/) — `Str` / `Stringable` / `str_`
- [Collections](/collections/) — `collect()`
