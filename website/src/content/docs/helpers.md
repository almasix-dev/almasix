---
title: Helpers
description: Arr, Number, path, URL and miscellaneous helpers — documented function by function.
---

Almasix ships the helper catalogue Laravel does: array and object utilities on
`Arr`, number formatting on `Number`, path and URL builders, and a long tail of
miscellaneous functions. Nothing is injected into Python's builtins, so every
helper is imported from the package that owns it:

```python
# app/http/controllers/invoice_controller.py
from almasix.support import Arr, Number, data_get

Arr.get({"user": {"name": "Ada"}}, "user.name")   # 'Ada'
Number.currency(12.5)                              # '$12.50'
data_get({"orders": [{"total": 30}]}, "orders.*.total")  # [30]
```

`Arr`, `Number` and every helper below also answer to their Laravel camelCase
name — `Arr.sortDesc` is `Arr.sort_desc`, `Number.fileSize` is
`Number.file_size` — so a Laravel example can be transcribed without renaming
as you read. The Python name is the documented one.

Two related pages carry their own surfaces: [Strings](/strings/) documents
`Str` and the fluent `Stringable`, and [Collections](/collections/) documents
`collect()`.

## Where each helper lives

| Group | Import |
| --- | --- |
| Arrays and objects | `from almasix.support import Arr` |
| Data paths | `from almasix.support import data_get, data_set, data_fill, data_forget, head, last` |
| Numbers | `from almasix.support import Number` |
| Paths | `from almasix.support import base_path, app_path, …` |
| URLs | `from almasix.routing import url, asset` |
| Application and container | `from almasix.framework import app, resolve` |
| Request and response | `from almasix.http import request, response, redirect, back` |
| Session and cookies | `from almasix.session import session, old, cookie, csrf_token` |
| Views and forms | `from almasix.prism import view, csrf_field, method_field` |
| Everything else | `from almasix.support import …` |

## Arrays and objects

`Arr` works on plain dicts and lists — nothing here needs a collection. Keys
are dot-notation paths wherever a key is accepted.

### accessible

Whether the value can be treated as an array by the rest of `Arr` — that is,
whether it is a mapping or a sequence. Strings and bytes are sequences in
Python but are deliberately excluded, so they report `False`.

```python
from almasix.support import Arr

result = Arr.accessible({"a": 1})

# True

result = Arr.accessible((1, 2))

# True

result = Arr.accessible("abc")

# False
```

### add

Sets `key` (dot notation) only if it is currently missing, then returns the
same mapping. The check is against `None`, so a key whose value is `None`
counts as missing and will be overwritten. It mutates the mapping in place.

```python
config = {"name": "Ada"}
Arr.add(config, "role", "engineer")
Arr.add(config, "name", "Grace")
result = config

# {'name': 'Ada', 'role': 'engineer'}

result = Arr.add({}, "user.name", "Ada")

# {'user': {'name': 'Ada'}}
```

### array

Reads `key` with dot notation and insists the value is a `list`, raising
`TypeError` with the offending key and value if it is not. With no key the
whole value is checked. Use it for configuration reads where a wrong type
should fail at the read rather than later.

```python
result = Arr.array({"tags": ["a", "b"]}, "tags")

# ['a', 'b']

try:
    Arr.array({"tags": "a,b"}, "tags")
except TypeError as error:
    result = str(error)

# "Value for 'tags' is not a list: 'a,b'"
```

### boolean

Reads `key` with dot notation and insists the value is a `bool`, raising
`TypeError` otherwise. The check is strict about Python's `bool`/`int` overlap,
so `1` and `0` are rejected rather than coerced.

```python
result = Arr.boolean({"debug": True}, "debug")

# True

try:
    Arr.boolean({"debug": 1}, "debug")
except TypeError as error:
    result = str(error)

# "Value for 'debug' is not a boolean: 1"
```

### collapse

Flattens one level of an iterable of iterables into a single list. Mappings
contribute their values, and items that are neither a mapping nor a sequence
are kept as they are rather than discarded.

```python
result = Arr.collapse([[1, 2], [3], {"a": 4}])

# [1, 2, 3, 4]

result = Arr.collapse([1, [2]])

# [1, 2]
```

### cross_join

Returns the Cartesian product of the given iterables as a list of lists, one
list per combination, in the order the arguments were passed. Called with no
arguments it returns a single empty combination.

```python
result = Arr.cross_join([1, 2], ["a", "b"])

# [[1, 'a'], [1, 'b'], [2, 'a'], [2, 'b']]

result = Arr.cross_join()

# [[]]
```

### divide

Splits a mapping into its keys and its values. Almasix returns a two-element
tuple, so it unpacks directly into two names.

```python
keys, values = Arr.divide({"name": "Ada", "role": "engineer"})
result = (keys, values)

# (['name', 'role'], ['Ada', 'engineer'])
```

### dot

Flattens a nested mapping or sequence into a single-level dict whose keys are
dot-notation paths; list positions become numeric segments. Empty mappings and
empty lists are kept as leaf values instead of vanishing. `prepend` is prefixed
to every key verbatim, so include the trailing dot yourself if you want one.

```python
result = Arr.dot({"user": {"name": "Ada", "roles": ["admin"]}})

# {'user.name': 'Ada', 'user.roles.0': 'admin'}

result = Arr.dot({"name": "Ada"}, "user.")

# {'user.name': 'Ada'}

result = Arr.dot({"tags": [], "meta": {}})

# {'tags': [], 'meta': {}}
```

### every

Whether `callback` returns true for every item. An empty iterable is `True`.

```python
result = Arr.every([2, 4, 6], lambda n: n % 2 == 0)

# True

result = Arr.every([2, 3], lambda n: n % 2 == 0)

# False
```

### except_

Returns the mapping without the given keys, which may be a single string or an
iterable of strings. Laravel calls this `except`; the trailing underscore
avoids the Python keyword. Keys are compared exactly at the top level — dot
notation is not resolved, so `"user.id"` removes nothing.

```python
result = Arr.except_({"name": "Ada", "role": "engineer", "id": 1}, ["role", "id"])

# {'name': 'Ada'}

result = Arr.except_({"user": {"name": "Ada", "id": 1}}, "user.id")

# {'user': {'name': 'Ada', 'id': 1}}
```

### except_keys

A second name for `except_`, bound to the same function, for call sites that
read better with an explicit noun. Behaviour is identical.

```python
result = Arr.except_keys({"name": "Ada", "role": "engineer"}, "role")

# {'name': 'Ada'}

result = Arr.except_keys is Arr.except_

# True
```

### except_values

Returns the items that are not in `values`, comparing by equality. This is the
value-side counterpart of `except_`, which works on keys.

```python
result = Arr.except_values([1, 2, 3, 4], [2, 4])

# [1, 3]
```

### exists

Whether `key` is present, without treating a `None` value as absent. Keys are
looked up exactly — dot notation is not resolved; for a sequence the key is an
index, coerced with `int`, and must be within range.

```python
result = Arr.exists({"a": None}, "a")

# True

result = Arr.exists([1, 2, 3], "1")

# True

result = Arr.exists({"user": {"id": 1}}, "user.id")

# False
```

### first

The first item, or the first item for which `callback` returns true. `default`
is returned when nothing matches, and is called if it is callable.

```python
result = Arr.first([1, 2, 3])

# 1

result = Arr.first([1, 2, 3], lambda n: n > 1)

# 2

result = Arr.first([1, 2, 3], lambda n: n > 5, 0)

# 0
```

### flatten

Flattens nested sequences and mappings into a single list, mappings
contributing their values. `depth` limits how many levels are flattened and
defaults to unlimited.

```python
result = Arr.flatten([1, [2, [3, [4]]]])

# [1, 2, 3, 4]

result = Arr.flatten([1, [2, [3, [4]]]], 1)

# [1, 2, [3, [4]]]

result = Arr.flatten({"a": [1, 2], "b": 3})

# [1, 2, 3]
```

### float

Reads `key` with dot notation and insists the value is a `float`, raising
`TypeError` otherwise. The check is by type and not by convertibility, so an
`int` such as `2` is rejected — pass `2.0` or convert before storing.

```python
result = Arr.float({"rate": 1.5}, "rate")

# 1.5

try:
    Arr.float({"rate": 2}, "rate")
except TypeError as error:
    result = str(error)

# "Value for 'rate' is not a float: 2"
```

### forget

Removes the given keys, in dot notation, from the mapping. It mutates the
mapping in place and returns `None`, so do not assign its result. Paths that do
not exist are ignored.

```python
config = {"user": {"name": "Ada", "id": 1}, "debug": True}
Arr.forget(config, ["user.id", "debug"])
result = config

# {'user': {'name': 'Ada'}}

result = Arr.forget(config, "user.missing")

# None
```

### from_

Materialises whatever it is given as a plain `list` or `dict`: `None` becomes
`[]`, a mapping becomes a `dict`, a string or bytes becomes a one-item list,
any other iterable becomes a `list`, and an object exposing `to_dict`,
`to_array` or `all` is converted through the first of those it has. Laravel
spells this `Arr::from`; `from` is a Python keyword, so the method is `from_`,
though the same function is also reachable as `getattr(Arr, "from")`.

```python
result = Arr.from_(None)

# []

result = Arr.from_((1, 2))

# [1, 2]

result = Arr.from_("abc")

# ['abc']

result = getattr(Arr, "from")({"a": 1})

# {'a': 1}
```

### get

Reads a value by dot-notation `key`, returning `default` when any segment is
missing. Numeric segments index into sequences, and a `key` of `None` returns
the array unchanged.

```python
result = Arr.get({"user": {"id": 7}}, "user.id")

# 7

result = Arr.get({"user": {"id": 7}}, "user.email", 0)

# 0

result = Arr.get([{"id": 7}], "0.id")

# 7

result = Arr.get({"a": 1}, None)

# {'a': 1}
```

### has

Whether a key exists, using dot notation to reach into nested mappings and
sequences. Given several keys it is true only when every one of them is
present, and an empty list of keys is false.

```python
from almasix.support import Arr

result = Arr.has({"user": {"name": "Ada"}}, "user.name")

# True
```

```python
result = Arr.has({"user": {"name": "Ada"}}, ["user.name", "user.email"])

# False
```

### has_all

Whether every one of the keys exists. This is the same test `has` already
performs for a list of keys; Laravel added `Arr::hasAll` as the explicit form
and Almasix mirrors it. An empty list of keys is false.

```python
result = Arr.has_all({"name": "Ada", "email": "ada@example.com"}, ["name", "email"])

# True
```

### has_any

Whether at least one of the keys exists, again in dot notation. An empty list
of keys is false, since nothing can match.

```python
result = Arr.has_any({"name": "Ada"}, ["email", "name"])

# True
```

### integer

Reads a value with `get` and insists it is an integer, raising `TypeError`
otherwise — for reading configuration where a wrong type should fail at the
read rather than further downstream. With no `key` the value itself is checked.
Booleans are rejected even though `bool` subclasses `int`, so
`Arr.integer({"debug": True}, "debug")` raises `TypeError: Value for 'debug' is
not an integer: True`. Almasix also provides `Arr.string`, `Arr.boolean`,
`Arr.float` and `Arr.array` in the same shape.

```python
result = Arr.integer({"server": {"port": 8000}}, "server.port")

# 8000
```

```python
result = Arr.integer(8000)

# 8000
```

### is_assoc

Whether the mapping has keys other than `0..n-1`, i.e. whether it is a
dictionary rather than something list-shaped. Sequences — including lists and
tuples — are always false, as is a dict whose keys happen to be consecutive
integers from zero.

```python
result = Arr.is_assoc({"name": "Ada"})

# True
```

```python
result = Arr.is_assoc({0: "a", 1: "b"})

# False
```

### is_list

The inverse test: true for any `list`, and for a mapping whose keys are exactly
`0..n-1`. Note that a tuple is not a list here — `Arr.is_list((1, 2))` is
`False`.

```python
result = Arr.is_list([1, 2, 3])

# True
```

```python
result = Arr.is_list({0: "a", 1: "b"})

# True
```

### join

Joins the items into a string with `glue`, stringifying each one. If
`final_glue` is given and there is more than one item, the last item is
attached with it instead.

```python
result = Arr.join(["a", "b", "c"], ", ")

# 'a, b, c'
```

```python
result = Arr.join(["a", "b", "c"], ", ", " and ")

# 'a, b and c'
```

### key_by

Builds a dictionary keyed by the given item attribute, read in dot notation, or
by the return value of a callback. Later items win when two share a key.

```python
result = Arr.key_by([{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}], "id")

# {1: {'id': 1, 'name': 'Ada'}, 2: {'id': 2, 'name': 'Linus'}}
```

```python
result = Arr.key_by(["ada", "linus"], lambda name: name[0])

# {'a': 'ada', 'l': 'linus'}
```

### last

The last item, or the last one for which `callback` returns true. When nothing
matches, `default` is returned — and if `default` is callable it is called, so
an expensive fallback can be deferred. Any iterable is accepted; it is
materialised into a list first.

```python
result = Arr.last([1, 2, 3, 4])

# 4
```

```python
result = Arr.last([1, 2, 3, 4], lambda n: n < 3)

# 2
```

```python
result = Arr.last([1, 2], lambda n: n > 5, default=lambda: 0)

# 0
```

### map

Applies the callback to each value and returns a list of the results. The
callback always receives two arguments — the value and its key, or its index
for a sequence — so a one-argument function will not work here. A mapping
argument still yields a list, not a mapping; use `map_with_keys` when you want
to keep keys.

```python
result = Arr.map({"a": 1, "b": 2}, lambda value, key: f"{key}={value}")

# ['a=1', 'b=2']
```

```python
result = Arr.map([10, 20], lambda value, index: value * index)

# [0, 20]
```

### map_spread

Like `map`, but each item that is a sequence is unpacked into the callback's
arguments, which suits lists of pairs. Items that are not sequences are passed
as a single argument.

```python
result = Arr.map_spread([[1, 2], [3, 4]], lambda a, b: a + b)

# [3, 7]
```

### map_with_keys

Builds a dictionary from the callback's return value, which may be either a
`(key, value)` tuple or a mapping that is merged into the result. The callback
receives the value and its key or index, as in `map`.

```python
result = Arr.map_with_keys(
    [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}],
    lambda item, index: (item["id"], item["name"]),
)

# {1: 'Ada', 2: 'Linus'}
```

```python
result = Arr.map_with_keys({"a": 1, "b": 2}, lambda value, key: {key.upper(): value * 10})

# {'A': 10, 'B': 20}
```

### only

Keeps only the given keys of a mapping. Keys that are absent are skipped rather
than filled with `None`, and the result follows the order of `keys`, not of the
mapping. A single key may be passed as a string. The complement is
`Arr.except_`.

```python
result = Arr.only({"name": "Ada", "age": 36, "email": "a@b.c"}, ["name", "email"])

# {'name': 'Ada', 'email': 'a@b.c'}
```

```python
result = Arr.only({"name": "Ada"}, "name")

# {'name': 'Ada'}
```

### only_values

Keeps the items whose *value* appears in `values`, in the original order.
Duplicates are kept, so an item that occurs twice is returned twice. The
complement is `Arr.except_values`.

```python
result = Arr.only_values([1, 2, 3, 4, 2], [2, 4])

# [2, 4, 2]
```

### partition

Splits the items into those for which the callback is true and those for which
it is false, returned as a two-tuple to unpack.

```python
passed, failed = Arr.partition([1, 2, 3, 4, 5], lambda n: n % 2 == 0)

result = (passed, failed)

# ([2, 4], [1, 3, 5])
```

### pluck

Collects one value out of each item, named in dot notation or produced by a
callback. Passing `key` as well returns a dictionary keyed by that second value
instead of a list.

```python
result = Arr.pluck([{"name": "Ada"}, {"name": "Linus"}], "name")

# ['Ada', 'Linus']
```

```python
result = Arr.pluck([{"id": 1, "name": "Ada"}, {"id": 2, "name": "Linus"}], "name", "id")

# {1: 'Ada', 2: 'Linus'}
```

### prepend

Returns a new list with the value at the front. Passing `key` changes the
return type to a dictionary with that key first; when the argument was a list
its items follow under their integer indexes, which is how Laravel's numeric
array keys come out in Python.

```python
result = Arr.prepend([2, 3], 1)

# [1, 2, 3]
```

```python
result = Arr.prepend(["b", "c"], "a", key="first")

# {'first': 'a', 0: 'b', 1: 'c'}
```

### prepend_keys_with

Returns a new dictionary with every key prefixed by the given string. Keys are
formatted into a string, so non-string keys become strings.

```python
result = Arr.prepend_keys_with({"name": "Ada", "age": 36}, "user_")

# {'user_name': 'Ada', 'user_age': 36}
```

### pull

Returns the value at `key` **and removes it from the mapping**, which is
modified in place. Dot notation reaches nested keys, and `default` is returned
when the key is absent.

```python
config = {"driver": "redis", "host": "127.0.0.1"}
driver = Arr.pull(config, "driver")

result = (driver, config)

# ('redis', {'host': '127.0.0.1'})
```

```python
result = Arr.pull({"host": "127.0.0.1"}, "port", 6379)

# 6379
```

### push

Appends the values to the list stored at `key`, **modifying the mapping in
place** and returning that same mapping rather than a copy. If the key is
missing it is created as a list, including intermediate levels of a
dot-notation key.

```python
payload = {"tags": ["python"]}
Arr.push(payload, "tags", "web", "orm")

result = payload

# {'tags': ['python', 'web', 'orm']}
```

```python
fresh = {}
Arr.push(fresh, "meta.tags", "new")

result = fresh

# {'meta': {'tags': ['new']}}
```

### query

Converts a mapping into a URL query string. A value that is a list is repeated
once per item, because the encoding is done by `urllib.parse.urlencode` with
`doseq=True`; that also means non-string scalars are rendered with Python's
`str`, so `None` becomes `a=None` rather than being dropped, and a nested
mapping is flattened to its keys instead of `filter[x]=1`.

```python
from almasix.support import Arr

result = Arr.query({"name": "Ada", "tags": ["a", "b"]})

# 'name=Ada&tags=a&tags=b'
```

### random

Returns one randomly chosen item, or a list of `number` randomly chosen items
when `number` is given. The result is random, so the examples below seed
`random` to make the output reproducible; asking for more items than the array
holds returns the whole array in random order rather than raising.

```python
import random

random.seed(1)
result = Arr.random([1, 2, 3, 4, 5])

# 2

two = Arr.random([1, 2, 3, 4, 5], 2)

# [5, 1]
```

### reject

Returns the items for which `callback` is falsey — the inverse of `Arr.where`.
The callback receives the item only, never its key or index.

```python
result = Arr.reject([1, 2, 3, 4], lambda n: n % 2 == 0)

# [1, 3]
```

### select

Reduces each row of `array` to the given keys, discarding the rest. `keys` may
be a single key or an iterable of them, and each row must be a mapping.

```python
rows = [{"name": "Ada", "age": 36}, {"name": "Linus", "age": 54}]
result = Arr.select(rows, ["name"])

# [{'name': 'Ada'}, {'name': 'Linus'}]
```

### set

Writes `value` at a dot-notation `key`, creating the intermediate mappings as
it goes. It **mutates the mapping it is given** and returns that same object
rather than a copy, so the return value is only a convenience for chaining. A
list along the way is written through by index, growing with `None` to reach an
index past its end; an intermediate segment holding any other non-mapping value
is replaced by a new mapping, discarding what was there.

```python
prices = {"products": {"desk": {"price": 100}}}
Arr.set(prices, "products.desk.price", 200)
result = prices

# {'products': {'desk': {'price': 200}}}

fresh = Arr.set({}, "a.b.c", 1)

# {'a': {'b': {'c': 1}}}
```

### shuffle

Returns a new list holding the items in random order. Unlike `Arr.set`, it does
not touch the argument — the original sequence is left as it was. The order is
random, so the example seeds `random` to make the output reproducible.

```python
import random

random.seed(1)
result = Arr.shuffle([1, 2, 3, 4, 5])

# [3, 4, 5, 1, 2]
```

### sole

Returns the single item matching `callback`, or the single item in `array` when
no callback is given. It raises `ItemNotFoundError` when nothing matches and
`MultipleItemsFoundError` when more than one item does, both from
`almasix.support.collection`.

```python
result = Arr.sole([1, 2, 3], lambda n: n > 2)

# 3

only = Arr.sole([{"name": "Ada"}])

# {'name': 'Ada'}
```

### some

Whether `callback` holds for at least one item. It short-circuits on the first
match and returns `False` for an empty array.

```python
result = Arr.some([1, 2, 3], lambda n: n > 2)

# True

none = Arr.some([1, 2, 3], lambda n: n > 9)

# False
```

### sort

Sorts by value and returns a `dict` for a mapping — keys are kept, paired with
their values, and only the order changes — or a new `list` for a sequence. Pass
`callback` to sort by a derived value instead of the value itself. See
`Arr.sort_desc` for the descending order.

```python
result = Arr.sort({"desk": 200, "chair": 100, "table": 150})

# {'chair': 100, 'table': 150, 'desk': 200}

by_name = Arr.sort([{"n": "b"}, {"n": "a"}], lambda row: row["n"])

# [{'n': 'a'}, {'n': 'b'}]
```

### sort_desc

The descending counterpart of `Arr.sort`, with the same mapping-in/`dict`-out
and sequence-in/`list`-out behaviour and the same optional `callback`. It is
implemented by reversing the ascending sort, so items with equal values come
out in the reverse of their original order rather than keeping it.

```python
result = Arr.sort_desc({"desk": 200, "chair": 100, "table": 150})

# {'desk': 200, 'table': 150, 'chair': 100}

numbers = Arr.sort_desc([1, 3, 2])

# [3, 2, 1]
```

### sort_recursive

Sorts a nested structure at every level, descending into mappings and
sequences. A mapping is sorted by its **keys** (unlike `Arr.sort`, which sorts
a mapping by value) and a sequence by its values; pass `descending=True` for
the reverse, which is the keyword Almasix uses in place of Laravel's separate
`sortRecursiveDesc`. A sequence whose items cannot be compared with one another
is returned in its original order instead of raising.

```python
result = Arr.sort_recursive({"users": ["Zoe", "Ada"], "b": 1, "a": 2})

# {'a': 2, 'b': 1, 'users': ['Ada', 'Zoe']}

reverse = Arr.sort_recursive({"a": [1, 3, 2], "b": 4}, descending=True)

# {'b': 4, 'a': [3, 2, 1]}
```

### string

Reads the value at a dot-notation `key` and insists it is a `str`, raising
`TypeError` if it is anything else — for reading configuration where a wrong
type should fail at the read rather than further downstream. Omit `key` to
assert on `array` itself.

```python
result = Arr.string({"app": {"name": "Almasix"}}, "app.name")

# 'Almasix'
```

### take

Returns the first `limit` items, or the last `limit` items when `limit` is
negative. Asking for more items than the array holds returns all of them.

```python
result = Arr.take([1, 2, 3, 4, 5], 3)

# [1, 2, 3]

last_two = Arr.take([1, 2, 3, 4, 5], -2)

# [4, 5]
```

### to_css_classes

Builds a `class` attribute value. Given a mapping, each key is included when
its value is truthy; given a sequence, each item is included when the item
itself is truthy, which is how falsey entries are dropped.

```python
result = Arr.to_css_classes({"p-4": True, "font-bold": False, "bg-red": 1})

# 'p-4 bg-red'

from_list = Arr.to_css_classes(["p-4", "", "font-bold", None])

# 'p-4 font-bold'
```

### to_css_styles

Builds a `style` attribute value, joined with `;` and with no trailing
semicolon. It reads two shapes: property to value, and Laravel's, where the key
is a whole style string and the value is the flag that switches it on. An entry
whose value is exactly `False` or `None` is skipped either way, which is how a
style is made conditional. A plain list of style strings works too.

```python
result = Arr.to_css_styles({"background-color": "blue", "color": "red"})

# 'background-color:blue;color:red'

switched = Arr.to_css_styles({"display: none": True, "color: red": False})

# 'display: none'

listed = Arr.to_css_styles(["display: none;", "color: red"])

# 'display: none;color: red'
```

### undot

Expands a flat mapping of dot-notation keys back into a nested `dict`, the
inverse of `Arr.dot`. Because it builds the result with `Arr.set`, a numeric
segment becomes a string key in a `dict` rather than an index in a list, so
`Arr.dot` followed by `Arr.undot` does not round-trip a structure that
contained lists.

```python
result = Arr.undot({"user.name": "Ada", "user.occupation": "Analyst"})

# {'user': {'name': 'Ada', 'occupation': 'Analyst'}}

numeric = Arr.undot({"users.0.name": "Ada"})

# {'users': {'0': {'name': 'Ada'}}}
```

### where

Returns the items for which `callback` is truthy. The callback receives the
item only, never its key or index, so filtering a mapping filters its values
and returns a list.

```python
result = Arr.where([1, 2, 3, 4], lambda n: n % 2 == 0)

# [2, 4]
```

### where_not_null

Returns the items that are not `None`. The test is `is not None`, so falsey
values such as `0` and `""` are kept.

```python
result = Arr.where_not_null([1, None, 3, None])

# [1, 3]
```

### wrap

Wraps a value in a list unless it already is one. `None` becomes an empty list,
a `list` is returned unchanged (the same object, not a copy), and any other
non-string sequence such as a tuple is converted to a list. A mapping is
wrapped rather than returned as-is, which differs from Laravel, where an
associative array is its own list.

```python
result = Arr.wrap("Almasix")

# ['Almasix']

empty = Arr.wrap(None)

# []

mapping = Arr.wrap({"a": 1})

# [{'a': 1}]
```

## Data paths

The `data_*` helpers and their two neighbours read and write nested structures
by dotted path, including through lists with `*`.

### data_fill

Writes `value` at the dotted `key` only when nothing is there already, and
mutates `target` in place rather than returning a copy (it does return the same
object for chaining). It is `data_set` with `overwrite=False`, so the existing
`price` below is left alone while the missing `discount` is added.

```python
from almasix.support import data_fill

data = {"products": {"desk": {"price": 100}}}
data_fill(data, "products.desk.price", 200)
data_fill(data, "products.desk.discount", 10)

# {'products': {'desk': {'price': 100, 'discount': 10}}}
```

### data_forget

Removes the value at a dotted `key`, mutating `target` in place. `keys` may be
a single string or a list of them, and missing keys are ignored rather than
raising.

```python
from almasix.support import data_forget

data = {"products": {"desk": {"price": 100, "sku": "D1"}}}
data_forget(data, "products.desk.price")
data_forget(data, ["products.desk.sku"])

# {'products': {'desk': {}}}
```

### data_get

Reads a value out of nested data using a dotted path, returning `default` when
any segment is missing. Segments resolve against mappings by key, against lists
and tuples by integer index, and against other objects by `get_attribute()` or
plain attribute lookup. Passing `key=None` returns `target` unchanged. A `*`
segment fans out over every entry at that level and collects the matches,
dropping the branches that came up empty; a second `*` collapses one level, so
the result stays flat.

```python
from almasix.support import data_get

data = {"users": [{"name": "Ada"}, {"name": "Linus"}]}
result = data_get(data, "users.0.name")
missing = data_get(data, "users.5.name", "unknown")
wildcard = data_get(data, "users.*.name")

# 'Ada'
# 'unknown'
# ['Ada', 'Linus']
```

A path that never reaches a list or mapping returns the default rather than an
empty list, so a wildcard over missing data is still distinguishable from a
wildcard over data with nothing in it.

```python
nowhere = data_get({"users": []}, "orders.*.total", "no orders")

# 'no orders'
```

### data_set

Writes `value` at the dotted `key`, creating intermediate dictionaries as
needed, and mutates `target` in place rather than returning a copy. The fourth
argument `overwrite` defaults to `True`; pass `False` to leave an existing
value alone, which is what `data_fill` does. A numeric segment against a list
writes into that list rather than replacing it, growing it with `None` when the
index is past the end; a non-numeric segment against a list raises `TypeError`
rather than quietly discarding the list.

```python
from almasix.support import data_set

data = {"products": {"desk": {"price": 100}}}
data_set(data, "products.desk.price", 200)
data_set(data, "products.chair.price", 50)
data_set(data, "products.desk.price", 999, False)

# {'products': {'desk': {'price': 200}, 'chair': {'price': 50}}}

users = {"users": [{"name": "Ada"}]}
data_set(users, "users.0.name", "Grace")
data_set(users, "users.2.name", "Alan")

# {'users': [{'name': 'Grace'}, None, {'name': 'Alan'}]}
```

### head

Returns the first item of any iterable, or `None` when it is empty — Laravel
returns `false` there. The argument is materialised into a list first, so a
generator is consumed.

```python
from almasix.support import head

result = (head([1, 2, 3]), head([]))

# (1, None)
```

```python
from almasix.support import head

result = head({"name": "Ada", "role": "engineer"})

# 'name'
```

### last

Returns the final item of any iterable, or `None` when it is empty. Like
`head`, it materialises the argument into a list, so it works on iterators as
well as sequences.

```python
from almasix.support import last

result = (last([1, 2, 3]), last([]))

# (3, None)
```

## Numbers

`Number` formats and parses numbers for people to read. Locale and currency
default to `en` and `USD` and can be changed per call or process-wide.

### abbreviate

Formats a number in short form, dividing by 1000 until the value fits and
appending the unit suffix (`K`, `M`, `B`, `T`). `precision` is the number of
decimal places to keep. At the default `precision=0` the remainder is truncated
rather than rounded, so `1999` abbreviates to `1K`, not `2K` as Laravel would
give.

```python
from almasix.support import Number

result = Number.abbreviate(1234)
precise = Number.abbreviate(1234, precision=2)

# '1K'
# '1.23K'
```

### clamp

Returns `number` restricted to the inclusive range between `min_value` and
`max_value`. Values below the minimum come back as the minimum, values above
the maximum as the maximum.

```python
result = Number.clamp(15, 1, 10)
low = Number.clamp(0, 1, 10)

# 10
# 1
```

### currency

Formats a number as currency using a symbol looked up from the currency code.
`in_` is the ISO code — Laravel spells this argument `in`, and the trailing
underscore avoids the Python keyword. It defaults to
`Number.default_currency()`. Only `USD`, `EUR` and `GBP` have symbols; any
other code is prefixed as the bare code followed by a space. `precision` sets
the decimal places, and `locale` is accepted for signature parity but ignored.

```python
result = Number.currency(1234.56)
yen = Number.currency(1234.56, in_="JPY")

# '$1,234.56'
# 'JPY 1,234.56'
```

### default_currency

Returns the currency code that `Number.currency` uses when no `in_` is passed.
It starts as `USD` and changes only through `use_currency` or `with_currency`.

```python
result = Number.default_currency()

# 'USD'
```

### default_locale

Returns the process-wide default locale, which starts as `en`. Note that the
locale is currently only consulted by `parse_int` and `parse_float`; the
formatting methods accept a `locale` argument and ignore it.

```python
result = Number.default_locale()

# 'en'
```

### file_size

Formats a byte count as a human-readable size, stepping through `B`, `KB`,
`MB`, `GB`, `TB` and `PB` in units of 1024. `precision` is the number of
decimal places; at the default of `0` the value is rounded, so `1536` gives `2
KB`.

```python
result = Number.file_size(1024)
precise = Number.file_size(1024 * 1024 * 3, precision=2)

# '1 KB'
# '3.00 MB'
```

### for_humans

Formats a number for display. By default it delegates to `abbreviate`, giving
the short `1.2M` form; passing `abbreviate=False` delegates to `format`
instead, giving the grouped `1,234` form. `precision` is forwarded to whichever
it calls.

```python
result = Number.for_humans(1234567, precision=1)
grouped = Number.for_humans(1234, abbreviate=False)

# '1.2M'
# '1,234'
```

### format

Formats a number with thousands separators. `precision` fixes the number of
decimal places; `max_precision` formats to that many places and then strips
trailing zeros. With neither, integers and whole floats print without a decimal
part and other floats keep their full value. `locale` is accepted for signature
parity but ignored, so output is always in the English `1,234.56` style.

```python
result = Number.format(1234567.891)
fixed = Number.format(1234567.891, precision=2)

# '1,234,567.891'
# '1,234,567.89'
```

### ordinal

Returns the number with its English ordinal suffix attached. The teens through
`20` all take `th`; the sign is preserved on the digits but does not affect the
suffix chosen.

```python
result = Number.ordinal(21)
teen = Number.ordinal(112)

# '21st'
# '112th'
```

### pairs

Splits the range `1..total` into `(start, end)` tuples of at most `chunk` items
each, useful for building batch or pagination ranges. The final tuple is short
when `total` is not a multiple of `chunk`.

```python
result = Number.pairs(25, 10)

# [(1, 10), (11, 20), (21, 25)]
```

### parse_float

Reads a float out of a formatted string, discarding grouping separators. Unlike
the formatting methods, `locale` has a real effect here: for `fr`, `de`, `es`,
`it`, `pt`, `nl`, `tr` and `ru` the comma is treated as the decimal separator
and dots and spaces as grouping; for anything else commas and spaces are
stripped and the dot is the decimal separator.

```python
result = Number.parse_float("1,234.56")
german = Number.parse_float("1.234,56", locale="de")

# 1234.56
# 1234.56
```

### parse_int

Parses the string through `parse_float` and truncates towards zero, so any
fractional part is discarded rather than rounded. `locale` is forwarded to
`parse_float` and selects the separator convention in the same way.

```python
result = Number.parse_int("1,234.99")
german = Number.parse_int("1.234,99", locale="de")

# 1234
# 1234
```

### percentage

Formats a number as a percentage string with a trailing `%`. `precision` is the
number of decimal places, defaulting to `0`. Both `max_precision` and `locale`
are accepted for signature parity and ignored, so `max_precision` will not
widen the output the way Laravel's does.

```python
result = Number.percentage(21.567, precision=2)

# '21.57%'
```

### spell

Spells a number out in English words, hyphenating the tens. The implementation
covers integers from `-999` to `999`; anything outside that range comes back as
its digits, so `1500` gives `'1500'` rather than words. Floats are truncated to
an integer first, and `locale` is accepted for signature parity but ignored.

```python
result = Number.spell(42)
large = Number.spell(1500)

# 'forty-two'
# '1500'
```

### spell_ordinal

Spells a number as an ordinal word by running `spell` and converting the last
word — `one` becomes `first`, `twenty` becomes `twentieth`. Only the final
hyphenated segment is converted, so hundreds come out wrong (`105` gives `'one
hundred fiveth'`), and `locale` is accepted for signature parity but ignored.

```python
result = Number.spell_ordinal(21)
irregular = Number.spell_ordinal(12)

# 'twenty-first'
# 'twelfth'
```

### trim

Drops a meaningless trailing zero decimal by returning an `int` when the value
is a whole number, and the `float` unchanged otherwise.

```python
result = Number.trim(12.0)
fractional = Number.trim(12.5)

# 12
# 12.5
```

### use_currency

Sets the process-wide default currency used by `Number.currency`. This mutates
module-level state for the rest of the process, so prefer `with_currency` for a
scoped change; if you do call it, capture and restore the previous value as
below.

```python
previous = Number.default_currency()
Number.use_currency("EUR")
formatted = Number.currency(9.99)
Number.use_currency(previous)

# '€9.99'
```

### use_locale

Sets the process-wide default locale. Like `use_currency` this mutates
module-level state for the rest of the process, so restore the previous value
or use `with_locale` instead. Only `parse_int` and `parse_float` read a locale,
and they read the one passed to them rather than this default, so today this
setting affects nothing but `default_locale`.

```python
previous = Number.default_locale()
Number.use_locale("de")
current = Number.default_locale()
Number.use_locale(previous)

# 'de'
```

### with_currency

Runs `callback` with `currency` installed as the default, returns whatever the
callback returns, and restores the previous default afterwards — including when
the callback raises. The callback takes no arguments.

```python
result = Number.with_currency("GBP", lambda: Number.currency(9.99))
after = Number.default_currency()

# '£9.99'
# 'USD'
```

### with_locale

Runs `callback` with `locale` installed as the default locale, returns its
result, and restores the previous default afterwards even if the callback
raises. As with `use_locale`, no formatting method reads the default locale, so
this is only observable through `default_locale`.

```python
result = Number.with_locale("fr", lambda: Number.default_locale())
after = Number.default_locale()

# 'fr'
# 'en'
```

## Paths

Every path helper resolves against the booted application's root, falling back
to the working directory when nothing is bootstrapped. Each returns a `str`.

### app_path

Returns the path to the application's `app` directory, joining any extra
segments onto it. Like every path helper it resolves against the booted
application's base path, falling back to the current working directory when
nothing has been bootstrapped — so the output below is what it printed when run
from the repository root.

```python
from almasix.support import app_path

result = app_path("Models")

# '/home/smaosa/Projects/almasix/app/Models'
```

### base_path

Returns the application's root directory, with any extra segments joined onto
it. The root is the booted application's base path, or the current working
directory when nothing is bootstrapped, so the values below are what it printed
from the repository root. Segments may be one dotted-free string containing
slashes or several separate arguments — `base_path("storage/logs")` and
`base_path("storage", "logs")` are equivalent.

```python
from almasix.support import base_path

root = base_path()
logs = base_path("storage/logs")

# '/home/smaosa/Projects/almasix'
# '/home/smaosa/Projects/almasix/storage/logs'
```

### config_path

Returns the path to the `config` directory, where Almasix looks for the
`config/*.py` modules that populate `config()`.

```python
from almasix.support import config_path

result = config_path("app.py")

# '/home/smaosa/Projects/almasix/config/app.py'
```

### database_path

Returns the path to the `database` directory, which holds migrations, seeders
and a SQLite file if you use one.

```python
from almasix.support import database_path

result = database_path("migrations")

# '/home/smaosa/Projects/almasix/database/migrations'
```

### lang_path

Returns the path to the `lang` directory, where translation files live.

```python
from almasix.support import lang_path

result = lang_path("en/validation.py")

# '/home/smaosa/Projects/almasix/lang/en/validation.py'
```

### public_path

Returns the path to the `public` directory — the document root, including the
`public/build` output that Vite and Tailwind write into.

```python
from almasix.support import public_path

result = public_path("build/app.css")

# '/home/smaosa/Projects/almasix/public/build/app.css'
```

### resource_path

Returns the path to the `resources` directory, where templates and uncompiled
front-end sources live. Note the directory is `resources` while the helper is
singular, matching Laravel.

```python
from almasix.support import resource_path

result = resource_path("views")

# '/home/smaosa/Projects/almasix/resources/views'
```

### storage_path

Returns the path to the `storage` directory, used for logs, caches and other
generated files.

```python
from almasix.support import storage_path

result = storage_path("logs/almasix.log")

# '/home/smaosa/Projects/almasix/storage/logs/almasix.log'
```

## URLs

`url()` and `asset()` resolve against `APP_URL` and `APP_BASE_PATH`, so a path
written once works behind a subdirectory or a proxy.

The named-route family — Laravel's `route()`, `to_route()`, `action()`,
`to_action()`, `uri()`, `secure_url()` and `secure_asset()` — arrives with
named-route generation, and is documented with it in [Routing](/routing/)
rather than duplicated here. Until then, build those URLs with `url()`.

### asset

Returns the URL for a file under `public/`, prefixed with `APP_BASE_PATH` so
apps hosted on a subpath emit correct links. It is the same code path as `url`,
so `absolute=False` drops the origin and keeps the base path. Reading config
outside a booted application raises `RuntimeError`, which is why the example
installs a config repository first; inside a booted app the import alone is
enough.

```python
from almasix.config import ConfigRepository, set_repository
from almasix.routing import asset

repository = ConfigRepository()
repository.set("app.url", "https://shop.test")
repository.set("app.base_path", "/eu")
set_repository(repository)

result = asset("build/app.css")
relative = asset("build/app.css", absolute=False)

# 'https://shop.test/eu/build/app.css'
# '/eu/build/app.css'
```

### url

Builds a URL for `path` from the `app.url` and `app.base_path` config values,
so an app mounted under a subpath never emits a root-absolute link. Pass
`absolute=False` for a path-only URL that keeps the base path but drops the
origin, and a path that is already absolute (`https://…` or `//…`) is returned
untouched. Calling it outside a booted application raises `RuntimeError`
because the config repository is unset, so the example installs one; a booted
app does this during bootstrap.

```python
from almasix.config import ConfigRepository, set_repository
from almasix.routing import url

repository = ConfigRepository()
repository.set("app.url", "https://shop.test")
repository.set("app.base_path", "/eu")
set_repository(repository)

result = url("users/1")
relative = url("users/1", absolute=False)

# 'https://shop.test/eu/users/1'
# '/eu/users/1'
```

## Miscellaneous

The long tail. Several of these reach for request or application state, and say
so where they do.

### abort

Raises an `HttpException` with the given status code, which the HTTP kernel
turns into an error response. The code defaults to `404` and the message to
`Aborted`; unlike Laravel, every status raises the same `HttpException` class
rather than a per-status subclass, with the code on `status_code`.

```python
from almasix.http.exceptions import HttpException
from almasix.support import abort

try:
    abort(403, "This post is not yours.")
except HttpException as error:
    result = (type(error).__name__, error.status_code, error.message)

# ('HttpException', 403, 'This post is not yours.')
```

### abort_if

Calls `abort` when the condition is truthy, and does nothing otherwise. The
arguments after the condition are the ones `abort` takes — status code,
message, and optional headers.

```python
from almasix.http.exceptions import HttpException
from almasix.support import abort_if

post = None
try:
    abort_if(post is None, 404, "No such post.")
except HttpException as error:
    result = (error.status_code, error.message)

# (404, 'No such post.')
```

```python
from almasix.support import abort_if

result = abort_if(False, 404, "No such post.")

# None
```

### abort_unless

The inverse of `abort_if`: aborts when the condition is falsy. It reads well
for guards that assert something must hold.

```python
from almasix.http.exceptions import HttpException
from almasix.support import abort_unless

owns_post = False
try:
    abort_unless(owns_post, 403, "This post is not yours.")
except HttpException as error:
    result = (error.status_code, error.message)

# (403, 'This post is not yours.')
```

### app

Returns the booted `Application`, or resolves `abstract` out of its container
when you pass a class or binding name. It raises `RuntimeError("Application is
not set. Bootstrap the Application first.")` before bootstrap, so it is for
code that runs inside the application, not for import-time work.

```python
# needs a booted application
from almasix.cache.manager import CacheManager
from almasix.framework import app

application = app()
manager = app(CacheManager)

# the Application, then the CacheManager resolved from its container
```

### auth

Returns the request's `AuthManager`, the entry point to the guards. Outside a
request it hands back an empty manager configured from `config('auth')` rather
than raising, so `auth().check()` is `False` instead of an error in console and
queue code.

```python
# needs a request context
from almasix.auth import auth


class SessionController:
    async def store(self):
        if await auth().attempt({"email": "ada@example.com", "password": "secret"}):
            return auth().user()
        return None

# auth() returns the AuthManager; user()/check()/id() are plain calls
```

Unlike Laravel, the methods that change authentication state — `attempt`,
`login`, `login_using_id`, `logout` — are coroutines and have to be awaited.
`user()`, `check()`, `guest()`, and `id()` are synchronous.

### back

Builds a 302 `Redirect` back to the page the request came from, falling back to
`fallback` (default `/`) when there is nowhere to go back to. Almasix reads the
`Referer` header rather than a session-stored previous URL, so a request that
arrives without one — and any call made outside a request, like the one below —
lands on the fallback.

```python
from almasix.http import back

redirect = back("/posts")
result = (redirect.status_code, redirect.headers["location"])

# (302, '/posts')
```

```python
from almasix.http import back

result = back("/posts", status=303).status_code

# 303
```

### bcrypt

Hashes a value with bcrypt whatever the configured default hash driver is, and
returns the 60-character crypt string. The optional second argument is the
driver's options, of which bcrypt reads `rounds`.

```python
from almasix.hashing import Hash, bcrypt

hashed = bcrypt("secret")
result = (hashed[:7], len(hashed), Hash.check("secret", hashed))

# ('$2b$12$', 60, True)
```

```python
from almasix.hashing import bcrypt

result = bcrypt("secret", {"rounds": 4})[:7]

# '$2b$04$'
```

### blank

Reports whether a value is "empty-ish": `None`, a string that is empty or only
whitespace, or an empty mapping, sequence, or anything else with a length of
zero. Booleans and numbers are never blank, and neither is the string `"0"`.

```python
from almasix.support import blank

result = (blank(""), blank("   "), blank(None), blank([]), blank({}))

# (True, True, True, True, True)
```

```python
from almasix.support import blank

result = (blank(0), blank(False), blank("0"))

# (False, False, False)
```

### cache

With no arguments returns the default store's repository; with a key it reads a
value, returning `default` on a miss. Passing a dict writes every pair, and in
that form the second argument is the time to live in seconds rather than a
default.

```python
# needs a booted application
from almasix.cache import cache

total = cache("orders.total", 0)
cache({"orders.total": 42}, 600)
repository = cache()

# the stored value or 0, then True for the write, then the default store
```

Without a booted application it raises `RuntimeError("Cache is not configured.
Bootstrap the Application first.")`.

### class_basename

Returns the class name without its module path. It accepts a class, an
instance, or a string path, and splits a string on both `.` and `\` so
PHP-style class strings carried over from Laravel still resolve.

```python
from almasix.support import class_basename

result = (class_basename(dict), class_basename("app.models.User"))

# ('dict', 'User')
```

```python
from almasix.support import class_basename

result = class_basename({"a": 1})

# 'dict'
```

### class_uses_recursive

Returns the set of classes an object or class inherits from, walking the whole
MRO and leaving out the class itself and `object`. Python has no traits, so
where Laravel returns the traits used by a class this returns base classes —
the sets are unordered, hence the `sorted` below.

```python
from almasix.support import class_uses_recursive


class Timestamps:
    pass


class Sluggable:
    pass


class Post(Timestamps, Sluggable):
    pass


result = sorted(base.__name__ for base in class_uses_recursive(Post))

# ['Sluggable', 'Timestamps']
```

### collect

Wraps a list, dict, tuple, set, generator, or another collection in a Support
`Collection` so you can chain over it. With no argument it builds an empty
collection; see the [Collections](/collections/) page for the methods.

```python
from almasix.support import collect

result = collect([1, 2, 3, 4]).filter(lambda n: n % 2 == 0).values().all()

# [2, 4]
```

```python
from almasix.support import collect

result = collect({"a": 1, "b": 2}).sum()

# 3
```

### config

Reads a configuration value by dot notation, returning `default` when the key
is missing. It is read-only: Laravel's array form for writing at runtime has no
equivalent, so set values through the repository (`app().config.set(...)`).

```python
# needs a booted application
from almasix.config import config

timezone = config("app.timezone", "UTC")
guards = config("auth.guards", {})

# the configured value, or the default when the key is missing
```

Before bootstrap it raises `RuntimeError("Configuration repository is not set.
Bootstrap the Application first.")`.

### cookie

Builds a cookie — it does not send one. `minutes` sets the lifetime, and is
stored as `max_age` in seconds; leave it out for a session cookie. With no name
it returns the cookie jar, whose `queue` method attaches a cookie to the
outgoing response.

```python
from almasix.session import cookie

built = cookie("flavour", "mint", 60)
result = (built.name, built.value, built.max_age, built.path, built.httponly)

# ('flavour', 'mint', 3600, '/', True)
```

```python
from almasix.session import cookie

result = cookie().forever("theme", "dark").max_age

# 315360000
```

### csrf_field

Returns the hidden `_token` input a form needs, as an `HtmlString` that the
Prism escaper leaves alone. In a template use the `@csrf` directive, which
compiles to the same markup.

```python
# needs a request context
from almasix.prism import csrf_field

field = csrf_field().__html__()

# '<input type="hidden" name="_token" value="...the session token...">'
```

### csrf_token

Returns the current session's CSRF token, generating and storing one on first
read. Where Laravel raises when there is no session store, this returns an
empty string.

```python
# needs a request context
from almasix.session import csrf_token

token = csrf_token()

# a random URL-safe token; '' when no session has been started
```

### dd

Dumps its arguments and halts — "dump and die". It prints a Rich panel per
value to stderr and then raises `DumpAndDie`, so unlike Laravel's `exit()` the
process is not killed: the HTTP kernel catches it and renders a dump page, and
a test can catch it too. Anything after the `dd()` call does not run.

```python
from almasix.debug import DumpAndDie
from almasix.support import dd

try:
    dd({"name": "Ada"})
except DumpAndDie as halt:
    result = halt.values

# ({'name': 'Ada'},)
```

### decrypt

Decrypts a payload produced by `encrypt`, returning the original value with its
type intact rather than a string. It verifies the payload's MAC first and
raises `DecryptException("The payload could not be decrypted.")` when the
payload has been tampered with or none of the configured keys fit — the current
`config('app.key')` is tried first, then `config('app.previous_keys')`, so a
key rotation does not invalidate old payloads.

```python
from almasix.encryption import decrypt, encrypt

result = decrypt(encrypt({"card": "4242"}))

# {'card': '4242'}
```

### dispatch

Pushes a job onto its queue connection, or runs it in-process when the job is
not queueable. Laravel's `dispatch()` is synchronous and returns a
`PendingDispatch`; Almasix's is a coroutine you have to await, and for a job
that runs in-process it returns whatever `handle()` returned.

```python
import asyncio

from almasix.queue import dispatch
from almasix.queue.job import Job


class SendWelcomeEmail(Job):
    def __init__(self, email):
        self.email = email

    def handle(self):
        return f"welcome sent to {self.email}"


result = asyncio.run(dispatch(SendWelcomeEmail("ada@example.com")))

# 'welcome sent to ada@example.com'
```

A job that subclasses `ShouldQueue` (or sets `queue`) is pushed to the
connection instead, which needs the queue configuration a booted application
supplies.

### dispatch_sync

Runs a job immediately in the current process, through its job middleware,
bypassing queue connections entirely — the way to run a `ShouldQueue` job
without a worker. Like `dispatch` it is a coroutine, and it returns the value
`handle()` returned.

```python
import asyncio

from almasix.queue import dispatch_sync
from almasix.queue.job import Job, ShouldQueue


class RebuildSitemap(Job, ShouldQueue):
    def handle(self):
        return "sitemap rebuilt"


result = asyncio.run(dispatch_sync(RebuildSitemap()))

# 'sitemap rebuilt'
```

### dump

Pretty-prints its arguments to stderr and carries on. It returns the values it
was given as a tuple, so it can be wrapped around an expression without
changing the surrounding code.

```python
from almasix.support import dump

result = dump({"name": "Ada"})

# ({'name': 'Ada'},)
```

```python
from almasix.support import dump

result = dump(1, "two")

# (1, 'two')
```

### e

HTML-escapes a value for output, converting `None` to an empty string and
escaping quotes as well as angle brackets. Passing `double_encode=False` leaves
entities such as `&lt;` alone, though `&amp;` is still re-encoded.

```python
from almasix.support import e

result = e("<b>Ada & Co</b>")

# '&lt;b&gt;Ada &amp; Co&lt;/b&gt;'
```

```python
from almasix.support import e

result = e("&lt;script&gt;", double_encode=False)

# '&lt;script&gt;'
```

### encrypt

Encrypts a value and returns the payload as a `nonce.ciphertext.mac` string;
`decrypt` gives the value back. The value is serialised as JSON rather than
pickled, so it has to be JSON-safe, and the nonce is random, which means
encrypting the same value twice produces two different payloads. The key comes
from `config('app.key')`, falling back to an insecure development key when no
application is booted — which is why the example below runs on its own.

```python
from almasix.encryption import decrypt, encrypt

payload = encrypt("4242 4242 4242 4242")
result = (type(payload).__name__, decrypt(payload))

# ('str', '4242 4242 4242 4242')
```

### env

Reads an environment variable, returning `default` when it is unset. Values
that look boolean (`true`, `yes`, `on`, `1` and their negatives) become `bool`,
and — unlike Laravel, which only ever returns strings here — a value is coerced
to `int` or `float` when the default you pass is one. `env` reads `os.environ`
only; loading the `.env` file is the application's job at boot.

```python
import os

from almasix.config import env

os.environ["APP_DEBUG"] = "true"
result = env("APP_DEBUG", False)

# True
```

```python
import os

from almasix.config import env

os.environ["DB_PORT"] = "5432"
result = (env("DB_PORT", 3306), env("DB_PORT"))

# (5432, '5432')
```

### event

Dispatches an event to its listeners and returns the list of their return
values. It is synchronous. The optional `payload` is for string events, whose
listeners are called with the event name and the payload list.

```python
from dataclasses import dataclass

from almasix.events import event, listen


@dataclass
class OrderShipped:
    order_id: int


listen(OrderShipped, lambda shipped: f"notified about {shipped.order_id}")
result = event(OrderShipped(order_id=17))

# ['notified about 17']
```

A listener that returns `False` stops the ones after it. Note that
`almasix.events` also exports a `dispatch` alias for this helper, which is a
different function from `almasix.queue.dispatch`.

### filled

The inverse of `blank` — true when a value has something in it. `0`, `False`,
and `"0"` are filled; whitespace-only strings are not.

```python
from almasix.support import filled

result = (filled("Ada"), filled(0), filled(""), filled(None))

# (True, True, False, False)
```

### info

Writes a message at INFO level to the default log channel and returns `None`.
The optional second argument is context, which is appended to the line as
`[key='value']` pairs.

```python
from almasix.log import info

result = info("Deploy finished", {"release": "1.4.0"})

# None
```

The line written to stderr is `[INFO] Deploy finished [release='1.4.0']`.

### literal

Builds a throwaway object whose attributes are the keyword arguments you pass,
for when a dict would need attribute access. It takes keyword arguments only.

```python
from almasix.support import literal

point = literal(x=3, y=4)
result = (point.x, point.y)

# (3, 4)
```

### logger

With a message, writes it at DEBUG level to the default channel and returns
`None`; with no arguments it returns the `LogWriter` itself, whose `debug`,
`info`, `warning`, `error`, `critical`, and `exception` methods write at the
other levels. `with_(**context)` returns a writer that adds that context to
every line.

```python
from almasix.log import logger

logger("Cache warm", {"keys": 12})
result = type(logger()).__name__

# 'LogWriter'
```

```python
from almasix.log import logger

result = logger().with_(request_id="abc").warning("Disk almost full")

# None
```

### method_field

Returns the hidden `_method` input that spoofs an HTTP verb a browser form
cannot send, upper-casing whatever you pass. The result is an `HtmlString`, so
Prism renders it unescaped — write it with `{!! method_field("put") !!}`.

```python
from almasix.prism import method_field

method_field("put")

# HtmlString('<input type="hidden" name="_method" value="PUT">')

str(method_field("delete"))

# '<input type="hidden" name="_method" value="DELETE">'
```

### now

Returns the current moment as a timezone-aware `datetime.datetime`, in UTC
unless you pass a `tzinfo`. The result is a stdlib `datetime`, not a
Carbon-style wrapper, and the default is UTC rather than the configured
application timezone.

```python
from almasix.support import now

now().tzinfo

# datetime.timezone.utc

from datetime import timedelta, timezone

now(timezone(timedelta(hours=2))).utcoffset()

# datetime.timedelta(seconds=7200)
```

### old

Reads the input that a previous request flashed with `redirect().with_input()`,
so a re-rendered form can show what the user typed. With no key it returns the
whole flashed mapping as a `dict`; with a key it returns that field or
`default`. Unlike the other session helpers it never raises without a session —
it returns `{}` or the default, because templates re-render old input on paths
that may have no session at all.

```python
# needs a request context
from almasix.http import redirect
from almasix.session import old

class RegisterController(Controller):
    async def store(self, request: Request):
        return redirect("/register").with_input()

    async def create(self):
        # On the next request, after with_input() flashed {"email": "ada@example.com"}:
        old()            # {'email': 'ada@example.com'}
        old("email")     # 'ada@example.com'
        old("name", "")  # ''
```

### once

Runs `callback` and caches its return value on the callable itself, so later
calls with the same function object return the cached value without running the
body again. Because the cache lives on the object, a lambda written afresh at
each call site is a different object and is not memoised — pass a named
function.

```python
from almasix.support import once

calls = []

def boot():
    calls.append(1)
    return len(calls)

(once(boot), once(boot), len(calls))

# (1, 1, 1)
```

### optional

Wraps a value so attribute access is null-safe: reading an attribute of
`optional(None)` gives another falsy `Optional` rather than raising. Passing a
second argument calls it with the value and returns the result, or `None` when
the value is `None`. Note the deviation: chained reads on an empty `Optional`
return an `Optional`, not `None`, so test it with `bool(...)` rather than `is
None`.

```python
from almasix.support import optional

class User:
    name = "Ada"

optional(User()).name

# 'Ada'

bool(optional(None))

# False

optional(None, lambda user: user.name)

# None
```

### policy

Returns the policy instance registered for a model class or model instance —
either works, since a model instance is resolved by its class. It raises
`LookupError` naming the model when nothing is registered for it.

```python
from almasix.auth.access import Gate, Policy, policy

class Post:
    pass

class PostPolicy(Policy):
    def update(self, user, post=None):
        return True

Gate.policy(Post, PostPolicy)  # returns the gate, so registrations chain

class Draft:
    pass

try:
    policy(Draft)
except LookupError as exc:
    caught = f"{type(exc).__name__}: {exc}"

(type(policy(Post)).__name__, caught)

# ('PostPolicy', 'LookupError: No policy is registered for Draft.')
```

### preg_replace_array

Replaces each successive match of `pattern` in `subject` with the next item
from `replacements`. `pattern` is a plain Python `re` pattern — no PHP-style
`/.../` delimiters. Once the replacements run out, further matches are replaced
with an empty string.

```python
from almasix.support import preg_replace_array

preg_replace_array(r":[a-z]+", ["8:30", "9:00"], "The event runs from :start to :end")

# 'The event runs from 8:30 to 9:00'

preg_replace_array(r"\?", ["1"], "id = ? and team = ?")

# 'id = 1 and team = '
```

### redirect

Returns a `Redirect` response pointing at `to`, resolved through `APP_URL` and
`APP_BASE_PATH`, with status 302 unless you pass `status`. The returned object
chains `with_` (flash one value or a mapping), `with_input` (flash input for
`old()`, the current request's input by default) and `with_errors` (flash an
error bag keyed by field) — all three write to the session for the next request
and raise `RuntimeError` asking for `StartSession` when there is none. `to` is
required — there is no argument-less redirector, so reach for
`response().redirect(...)` or `back()` instead.

```python
# needs a request context
from almasix.http import redirect

class RegisterController(Controller):
    async def store(self, request: Request):
        target = redirect("/register")
        target.status_code                # 302
        target.headers["location"]        # '/register'

        return (
            redirect("/register")
            .with_("status", "Check your inbox.")
            .with_input({"email": "ada@example.com"})
            .with_errors({"email": "Taken."})
        )
        # next request: session.get("status") == 'Check your inbox.'
        #               session.get("errors") == {'email': ['Taken.']}
        #               old("email") == 'ada@example.com'
```

### report

Sends an exception to the application's exception handler without raising it,
for the failures you want recorded but not surfaced. Before an application is
booted there is no handler, so it prints a single line to stderr instead.

```python
from almasix.support import report

report(ValueError("disk almost full"))

# [report] ValueError: disk almost full
```

### report_if

Calls `report` only when the condition is truthy, and does nothing otherwise.

```python
from almasix.support import report_if

report_if(False, RuntimeError("never reported"))
report_if(True, RuntimeError("cache stampede"))

# [report] RuntimeError: cache stampede
```

### report_unless

The inverse of `report_if`: reports the exception when the condition is falsy.

```python
from almasix.support import report_unless

report_unless(True, ConnectionError("never reported"))
report_unless(False, ConnectionError("search cluster unreachable"))

# [report] ConnectionError: search cluster unreachable
```

### request

Returns the request currently being handled, or one of its inputs when given a
key. Outside a request it returns `None` rather than an empty request, so
console and queue code can ask without pretending there is a caller — which
also means `request().input(...)` blows up there, while `request(key, default)`
is safe.

```python
# needs a request context
from almasix.http import request

class SearchController(Controller):
    async def index(self):
        # For GET /search?q=almasix:
        request().path       # '/search'
        request().method     # 'GET'
        request("q")         # 'almasix'
        request("page", 1)   # 1
```

### rescue

Runs `callback` and returns its value; if it raises, returns `rescue_with`
instead — called with the exception when it is a callable. The exception is
also passed to `report` unless you pass `report=False`.

```python
from almasix.support import rescue

rescue(lambda: 1 / 0, "unavailable", report=False)

# 'unavailable'

rescue(lambda: 1 / 0, lambda exc: type(exc).__name__, report=False)

# 'ZeroDivisionError'
```

### resolve

Resolves a binding out of the booted application's container by type or string
name. It raises `RuntimeError` when no application has been bootstrapped, and
`ResolutionError` when the application exists but nothing is bound for the
abstract.

```python
# needs a booted application
from almasix.config import ConfigRepository
from almasix.framework import resolve

class ReportController(Controller):
    async def index(self):
        config = resolve(ConfigRepository)   # the application's ConfigRepository
        return {"app": config.get("app.name")}
```

### response

With content, builds a response: mappings and lists become JSON, bytes are sent
as-is, anything else is stringified as plain text. With no content it returns
the `ResponseFactory` instead, which carries `json`, `html`, `make`,
`no_content`, `view`, `file`, `download`, `stream`, `redirect` and `back`. Note
that `response(None)` returns the factory rather than a 204 —
`response().no_content()` is the 204, and `response(None, status=204)` also
gives you one.

```python
from almasix.http import response

response("Hello").status_code

# 200

response({"name": "Ada"}, status=201).status_code

# 201

type(response()).__name__

# 'ResponseFactory'

response().json({"ok": True}).body

# b'{"ok":true}'

response().no_content().status_code

# 204

response(None) is response()

# True
```

### retry

Calls `callback` up to `times` times, returning its first successful result and
re-raising the last exception when every attempt fails. `sleep` is a
keyword-only delay between attempts **in seconds** — it goes to `time.sleep`,
not milliseconds — and accepts a callable taking the attempt number for a
backoff. Pass `when` a predicate over the exception to retry only some
failures; anything it rejects is re-raised at once.

```python
from almasix.support import retry

attempts = []

def flaky():
    attempts.append(1)
    if len(attempts) < 3:
        raise RuntimeError("boom")
    return "connected"

(retry(5, flaky, sleep=0.01), len(attempts))

# ('connected', 3)
```

### retry_async

The coroutine counterpart to `retry` — it must be awaited, and it awaits the
callback's result when that result is awaitable. `sleep` is a number of seconds
slept with `asyncio.sleep`, so a retrying call does not block the event loop.

```python
import asyncio

from almasix.support import retry_async

attempts = []

async def fetch():
    attempts.append(1)
    if len(attempts) < 2:
        raise TimeoutError("slow upstream")
    return "payload"

asyncio.run(retry_async(3, fetch, sleep=0.01))

# 'payload'
```

### session

Returns the session store, one of its values, or writes every pair of a mapping
and returns `None`. It raises `RuntimeError` naming the `StartSession`
middleware when there is no session. Keys are flat: unlike Laravel, the store
is a plain dict, so `session("cart.total")` looks for a key literally called
`cart.total` rather than descending into `cart`.

```python
# needs a request context
from almasix.session import session

class CartController(Controller):
    async def show(self):
        # With a session holding {"cart": {"total": 12}}:
        session()                        # the Session store
        session("cart")                  # {'total': 12}
        session("coupon", "none")        # 'none'
        session({"coupon": "SAVE10"})    # None — writes the pair
        session("coupon")                # 'SAVE10'
```

### str_

Wraps a value in a `Stringable` for fluent string calls, the same as
`Str.of(value)`. Laravel spells it `str()`; the trailing underscore keeps it
clear of the builtin. Call `str(...)` on the result when you need a plain
`str`.

```python
from almasix.support import str_

str_("  laravel to almasix ").trim().headline()

# Stringable('Laravel To Almasix')

str(str_("almasix").upper())

# 'ALMASIX'
```

### tap

Passes `target` to `callback` and returns `target`, for acting on a value in
the middle of an expression. With no callback it returns the target unchanged
rather than a higher-order proxy, so there is no `tap(value).method()` form to
chain.

```python
from almasix.support import tap

tap([1, 2], lambda items: items.append(3))

# [1, 2, 3]

tap("Ada")

# 'Ada'
```

### throw_if

Raises when the condition is truthy, and returns `None` otherwise. Pass an
exception class plus its arguments, or an already-built exception instance; a
plain string becomes a `RuntimeError`, which is also the default when you pass
nothing.

```python
from almasix.support import throw_if

try:
    throw_if(True, ValueError, "quota exceeded")
except ValueError as exc:
    caught = f"{type(exc).__name__}: {exc}"

caught

# 'ValueError: quota exceeded'

throw_if(False, ValueError, "quota exceeded")

# None
```

### throw_unless

The inverse of `throw_if`: raises when the condition is falsy, taking the same
exception forms.

```python
from almasix.support import throw_unless

try:
    throw_unless(0, RuntimeError("a team is required"))
except RuntimeError as exc:
    caught = f"{type(exc).__name__}: {exc}"

caught

# 'RuntimeError: a team is required'
```

### today

Returns today's `datetime.date` in UTC, or in `tz` when you pass one — it is
`now(tz).date()`. As with `now`, this is a stdlib `date` rather than a Carbon
instance set to midnight.

```python
from almasix.support import now, today

today() == now().date()

# True

type(today()).__name__

# 'date'
```

### trait_uses_recursive

Returns the set of classes a class or instance inherits from, walking the whole
MRO and excluding the class itself and `object`. Python has no traits, so this
is an alias of `class_uses_recursive` over base classes and mixins, and it
returns a `set` of classes rather than PHP's name-keyed array.

```python
from almasix.support import trait_uses_recursive

class Timestamps:
    pass

class SoftDeletes:
    pass

class Post(SoftDeletes, Timestamps):
    pass

sorted(base.__name__ for base in trait_uses_recursive(Post))

# ['SoftDeletes', 'Timestamps']

sorted(base.__name__ for base in trait_uses_recursive(Post()))

# ['SoftDeletes', 'Timestamps']
```

### transform

Calls `callback` with the value when the value is filled (as `filled()` judges
it) and returns the result; otherwise returns `default`, invoking it when it is
a callable.

```python
from almasix.support import transform

transform("42", int)

# 42

transform("", int, "missing")

# 'missing'

transform(None, int, lambda: "missing")

# 'missing'
```

### validator

Validates a payload outside the request lifecycle and returns a `Validator`
with `passes()`, `fails()`, `errors()` and `validated()`. **This is a named
deviation from Laravel:** `rules` is a Pydantic model or a `FormRequest`
subclass, not an array of rule strings, because that is how Almasix declares
validation everywhere else. `errors()` maps field to a list of messages, and
`validated()` (aliased `validate()`) returns the cleaned payload or raises
`ValidationException`. The `messages` and `attributes` keyword arguments
override message text and field names.

```python
from almasix.validation import FormRequest, validator

class Registration(FormRequest):
    email: str
    age: int = 18

check = validator({"email": "ada@example.com", "age": 36}, Registration)

(check.passes(), check.validated())

# (True, {'email': 'ada@example.com', 'age': 36})

validator({"age": "thirty"}, Registration).errors()

# {'email': ['The email field is required.'], 'age': ['The age must be an integer.']}
```

### value

Returns the value it is given, or calls it and returns the result when it is
callable. Extra positional arguments are passed to the callable.

```python
from almasix.support import value

(value(5), value(lambda: 5), value(lambda n: n * 2, 21))

# (5, 5, 42)
```

### view

Renders a Prism template and wraps it in an HTML response, with optional
`status` and `headers`. It renders there and then and hands back a Starlette
`HTMLResponse` rather than a lazy view object the framework renders later, so
reach for `almasix.prism.render()` when you want the markup as a string. It
needs the engine the application bootstraps, and raises `RuntimeError` before
then.

```python
# needs a booted application
from almasix.prism import view

class WelcomeController(Controller):
    async def index(self):
        # With resources/views/welcome.prism.html containing "<h1>Hello {{ name }}</h1>":
        rendered = view("welcome", {"name": "Ada"})
        rendered.status_code   # 200
        rendered.media_type    # 'text/html'
        rendered.body          # b'<h1>Hello Ada</h1>'

        return view("welcome", {"name": "Ada"}, status=201, headers={"x-demo": "1"})
```

### when

Returns the second argument when the condition is truthy and the third when it
is not, calling either if it is a callable. A callable that takes at least one
parameter receives the condition itself, which is how you reuse the truthy
value without repeating it.

```python
from almasix.support import when

when(True, "on", "off")

# 'on'

when(0, "on", "off")

# 'off'

when("Ada", lambda name: f"Hi {name}")

# 'Hi Ada'
```

### with_

Passes the value into the callback and returns the **callback's** result, which
is what distinguishes it from `tap`. Laravel calls this `with`; the trailing
underscore avoids the Python keyword.

```python
from almasix.support import with_

with_(5, lambda n: n * 3)

# 15
```

## Not yet built

Three of Laravel's miscellaneous helpers wait on features Almasix has not built,
and are absent rather than stubbed:

| Laravel | Waiting on |
| --- | --- |
| `broadcast`, `broadcast_if`, `broadcast_unless` | Broadcasting — websockets and channel authorisation |
| `context` | The contextual data store that carries state across jobs and log lines |
| `fake` | A seeded fake-data generator for factories and tests |

## Other utilities

Laravel's Helpers page closes with a set of standalone utilities. Almasix has
not built them; they are listed here so their absence is a decision rather than
a gap you have to discover:

| Laravel utility | Status in Almasix |
| --- | --- |
| **Benchmarking** (`Benchmark::dd`) | Not built. Time code with `time.perf_counter` or your profiler. |
| **Dates** (`Carbon`) | Not built as a wrapper. Almasix returns `datetime` / `date` from `now()` and `today()`, and the ORM casts to them; Python's `datetime` and `zoneinfo` cover what Carbon does. |
| **Deferred functions** (`defer`) | Not built. Queue a job instead — see [Queues](/queues/). |
| **Lottery** (`Lottery::odds`) | Not built. |
| **Pipeline** (`Pipeline::send`) | Not built as a public utility, though the HTTP kernel runs middleware as a pipeline internally. |
| **Sleep** (`Sleep::for`) | Not built. Use `time.sleep` / `asyncio.sleep`; `retry()` takes a sleep argument for the retry case. |
| **Timebox** (`Timebox::call`) | Not built. |

## Related

- [Strings](/strings/) — `Str`, `Stringable`, `str_()`
- [Collections](/collections/) — `collect()`
- [Views](/views/) — `view()`, `csrf_field()`, and the Prism directives
