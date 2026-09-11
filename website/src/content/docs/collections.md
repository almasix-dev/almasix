---
title: Collections
description: Fluent Support collections via collect() — ordered maps with a rich method chain, documented method by method.
---

Almasix collections wrap a list or a dict so you can chain operations instead
of writing loops. `collect()` is the way in, every transformer returns a new
collection, and `all()` gets you back to plain Python. Methods also accept
camelCase aliases (`sortBy` for `sort_by`); snake_case is the documented form.

```python title="app/http/controllers/welcome_controller.py"
from almasix.support import collect

collect(["", "Ada", None, "Grace"]).filter().values().all()
# ["Ada", "Grace"]
```

Almasix ships two collection types:

| Type | Import | Role |
| --- | --- | --- |
| **Support** | `from almasix.support import collect, Collection` | General list and map work — this page |
| **Articulate** | `from almasix.orm import Collection` | Model results; **extends** Support with `load`, `model_keys`, and key-aware overrides — see [Articulate: Collections](/articulate/collections/) |

## Keys

Collections are ordered maps, not lists. A list becomes contiguous integer
keys; a dict keeps the keys it came with. This matters because filtering
**preserves keys** rather than closing the gaps:

```python title="app/support_demo.py"
collect([0, 1, 2]).filter().all()           # {1: 1, 2: 2}
collect([0, 1, 2]).filter().values().all()  # [1, 2]
```

`values()` reindexes. It is worth reaching for whenever a filtered collection
is on its way to JSON, since a dict with integer keys and a list serialise
differently.

## Creating collections

`collect()` accepts a list, a dict, a tuple, a set, a generator, another
collection, or nothing at all:

```python title="examples/helpers.py"
from almasix.support import Collection, collect

collect([1, 2, 3])
collect({"a": 1, "b": 2})
collect()                        # empty

Collection.make([1, 2, 3])       # the same thing, spelled as a constructor
Collection.wrap("Ada")           # ["Ada"] — wraps a scalar, passes a collection through
Collection.times(3, lambda n: n * 2)   # [2, 4, 6]
Collection.range(1, 4)                 # [1, 2, 3, 4]
Collection.from_json('[1, 2]')         # decode JSON into a collection
```

## Extending collections

`macro` registers a method on the collection class at runtime, for an operation
your application performs often enough to deserve a name:

```python title="app/providers/app_service_provider.py"
from almasix.support import Collection

Collection.macro("to_upper", lambda collection: collection.map(str.upper))

collect(["ada", "grace"]).to_upper().all()
# ["ADA", "GRACE"]
```

The callback receives the collection as its first argument, followed by
whatever the caller passed. Macros are registered globally, so put them in a
service provider rather than in a request path.

## Higher order messages

For the common case where the callback does one thing to each item, a higher
order message says it in less:

```python title="examples/collections.py"
users.each.mark_as_vip()        # calls the method on every model
users.sum.votes                 # reads the attribute from every model
users.sort_by.created_at
```

Twenty-four methods support this: `average`, `avg`, `contains`, `each`,
`every`, `filter`, `first`, `flat_map`, `group_by`, `key_by`, `map`, `max`,
`min`, `partition`, `reject`, `skip_until`, `skip_while`, `some`, `sort_by`,
`sort_by_desc`, `sum`, `take_until`, `take_while`, and `unique`.

PHP can tell a property read apart from a method call at the call site and
Python cannot, so Almasix decides by looking at the items: a callable member is
invoked, anything else is read. Reading works on model attributes and on
mapping keys, so `collect([{"votes": 3}]).sum.votes` is `3`.

Filtering methods use the member as a **predicate**:
`users.first.vip` is the first VIP user, not the first user's `vip` value.

## Lazy collections

An eager collection holds every item in memory. A lazy one holds a source and
applies your operations one item at a time, which is what you want for a
database cursor or a file with a million lines in it.

```python title="examples/helpers.py"
from almasix.support import LazyCollection

def lines():
    with open("access.log") as handle:
        yield from handle

LazyCollection(lines).filter(lambda line: "error" in line).take(5).all()
```

Only five lines are read from the file. Nothing runs until you call a terminal
method — `all`, `first`, `each`, `count`, `sum`, `avg`, `max`, `min`, `reduce`,
`contains`, `is_empty`, `collect` — and the chain in between (`map`, `filter`,
`reject`, `where`, `pluck`, `take`, `skip`, `take_while`, `take_until`,
`skip_while`, `skip_until`, `unique`, `chunk`, `tap_each`) never materialises.

Because a lazy collection is a source rather than data, iterating twice runs
the source twice — and a spent generator yields nothing the second time.
`remember()` caches what has been enumerated so far:

```python title="examples/collections.py"
rows = LazyCollection(lines).remember()
rows.take(5).all()    # reads five lines
rows.all()            # replays those five, then reads the rest
```

### Streaming from the database

Reading a row is awaited, so the database returns the async twin,
`AsyncLazyCollection`. The operations are identical and the terminals are
awaited:

```python title="app/http/controllers/report_controller.py"
totals = await Order.query().cursor().where("status", "shipped").sum("total")

async for order in Order.query().lazy():
    await archive(order)
```

`Model.cursor()` holds one result set open; `Model.lazy()` and
`Model.lazy_by_id()` issue a query per chunk. All three return an
`AsyncLazyCollection`, so `async for` reads rows as they arrive and the
pipeline applies without buffering the result set.

### Lazy-only methods

Four methods exist only on lazy collections, because they are about
enumeration rather than data:

```python title="examples/collections.py"
rows.tap_each(log)                    # watch each item as it passes
rows.throttle(0.5)                    # space items out for a rate-limited consumer
rows.take_until_timeout(30)           # stop enumerating after 30 seconds
rows.with_heartbeat(10, touch_lock)    # call something every 10 seconds while working
```

`take_until_timeout` also accepts a `datetime`. `throttle` and
`with_heartbeat` pause with `time.sleep` on a sync collection and
`asyncio.sleep` on an async one.

### What lazy collections do not have

Sorting and grouping need every item at once, so they are not lazy operations
and are deliberately absent rather than faked. Call `collect()` to materialise
an eager collection and use its full surface:

```python title="examples/collections.py"
await Order.query().cursor().where("status", "shipped").collect()
# an eager Collection — sort_by, group_by, and the rest of this page
```

## Available methods

Every method below has its own section. They are listed alphabetically.

### after

Returns the item that comes after the given value, or `None` if the value is not
in the collection or is the last item. Values are located by equality against
the collection's values.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).after(2)

# 3

last = collect([1, 2, 3, 4]).after(4)

# None
```

Almasix takes a plain value only and always compares with `==` — there is no
callback or strict-comparison form.

### all

Returns the underlying items. You get a `list` when the keys are a contiguous
`0..n-1` range, and a `dict` otherwise — so a collection built from a mapping,
or one whose keys were preserved by `filter`, comes back as a `dict`.

```python title="examples/collections.py"
result = collect([1, 2, 3]).all()

# [1, 2, 3]

mapping = collect({"a": 1, "b": 2}).all()

# {'a': 1, 'b': 2}
```

### average

Alias for `avg`.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).average()

# 2.5
```

### avg

Returns the mean of the items. Pass a key (dot notation is supported) or a
callable to average a value pulled out of each item. `None` values are skipped
entirely, and an empty collection returns `None` rather than raising.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).avg()

# 2.5

pages = collect([{"pages": 176}, {"pages": 1096}]).avg("pages")

# 636.0
```

Also available as a higher order message (`collection.avg.pages`).

### before

Returns the item that comes before the given value, or `None` if the value is
not in the collection or is the first item.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).before(3)

# 2

first = collect([1, 2, 3, 4]).before(1)

# None
```

### chunk

Splits the collection into a collection of smaller collections of the given
size; the final chunk holds whatever is left over. Keys are not preserved, and a
size of zero or less raises `ValueError`.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).chunk(2).all()

# [Collection([1, 2]), Collection([3, 4]), Collection([5])]

plain = collect([1, 2, 3, 4, 5]).chunk(2).map(lambda chunk: chunk.all()).all()

# [[1, 2], [3, 4], [5]]
```

### chunk_while

Builds chunks by deciding, for each item, whether it belongs with the run built
so far. The callback receives three arguments: the current item, the previous
item, and the chunk being accumulated as a plain list. Return a truthy value to
keep the item in the current chunk, falsy to start a new one.

```python title="examples/collections.py"
result = (
    collect([1, 2, 3, 5, 6, 8])
    .chunk_while(lambda item, previous, chunk: item == previous + 1)
    .map(lambda chunk: chunk.all())
    .all()
)

# [[1, 2, 3], [5, 6], [8]]
```

The callback receives the current item, the previous item, and the chunk —
not the key.

### collapse

Flattens a collection of iterables into a single collection, one level deep.
Mapping items contribute their values, and items that are not iterable are
passed through unchanged instead of raising.

```python title="examples/collections.py"
result = collect([[1, 2], [3, 4], [5]]).collapse().all()

# [1, 2, 3, 4, 5]

mixed = collect([[1, 2], 3]).collapse().all()

# [1, 2, 3]
```

### collapse_with_keys

Merges the mapping (or collection) items into a single collection, keeping their
keys; later keys win over earlier ones. Items that are neither mappings nor
collections are dropped rather than appended.

```python title="examples/collections.py"
result = collect([{"a": 1}, {"b": 2}]).collapse_with_keys().all()

# {'a': 1, 'b': 2}

dropped = collect([{"a": 1}, [1, 2]]).collapse_with_keys().all()

# {'a': 1}
```

### collect

Returns a new collection holding the same items — a shallow copy, useful when
you are about to call one of the mutating methods and want the original left
alone. This is the method on an existing collection; the module-level `collect()`
function is the constructor.

```python title="examples/collections.py"
original = collect([1, 2])
copy = original.collect().push(9)

# copy.all() is [1, 2, 9], original.all() is still [1, 2]
```

### combine

Uses the collection's values as keys and the given iterable as the matching
values. The two are zipped non-strictly, so the result stops at the shorter of
the two rather than raising.

```python title="examples/collections.py"
result = collect(["name", "age"]).combine(["Sara", 30]).all()

# {'name': 'Sara', 'age': 30}

short = collect(["a", "b", "c"]).combine([1, 2]).all()

# {'a': 1, 'b': 2}
```

### concat

Appends the given items to the end of the collection.

```python title="examples/collections.py"
result = collect([1, 2]).concat([3, 4]).all()

# [1, 2, 3, 4]
```

In Almasix `concat` is `merge`, so it only appends when both sides are list-like.
Given string keys it merges and colliding keys overwrite, rather than always
appending and reindexing:

```python title="examples/collections.py"
result = collect({"a": 1}).concat({"a": 2}).all()

# {'a': 2}
```

### contains

Reports whether the collection holds a matching item. Pass a value, a predicate,
a key and a value, or a key, an operator and a value.

```python title="examples/collections.py"
books = [{"name": "Refactoring", "pages": 448}, {"name": "Clean Code", "pages": 464}]

result = collect([1, 2, 3]).contains(2)

# True

by_predicate = collect([1, 2, 3]).contains(lambda item: item > 2)

# True

by_key = collect(books).contains("name", "Clean Code")

# True

by_operator = collect(books).contains("pages", ">", 450)

# True
```

With a single argument Almasix checks the keys as well as the values, so
`collect({"a": 1}).contains("a")` is `True`. Also available as a higher order
message.

### contains_one_item

Reports whether the collection holds exactly one item.

```python title="examples/collections.py"
result = collect([1]).contains_one_item()

# True

more = collect([1, 2]).contains_one_item()

# False
```

### contains_strict

Reports whether the collection holds the given object by identity (`is`), not
equality. Two equal but distinct lists or dicts do not match; interned strings
and small integers often do, which makes this mostly useful for object
membership.

```python title="examples/collections.py"
result = collect([[1], [2]]).contains_strict([1])

# False
```

Almasix compares object identity (`is`), not type-strict value equality.

### count

Returns the number of items.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).count()

# 4
```

### count_by

Counts occurrences and returns a collection of value-to-count pairs. With no
argument it counts the items themselves; pass a key or a callable to count by
something derived from each item.

```python title="resources/views/examples/collections.prism.html"
result = collect([1, 1, 2, 2, 2, 3]).count_by().all()

# {1: 2, 2: 3, 3: 1}

domains = collect(["a@gmail.com", "b@yahoo.com", "c@gmail.com"]).count_by(
    lambda email: email.split("@")[1]
).all()

# {'gmail.com': 2, 'yahoo.com': 1}
```

### cross_join

Returns the Cartesian product of the collection with the given iterables, as a
collection of lists. Any number of iterables may be passed.

```python title="examples/collections.py"
result = collect([1, 2]).cross_join(["a", "b"]).all()

# [[1, 'a'], [1, 'b'], [2, 'a'], [2, 'b']]
```

### dd

Prints the collection's contents to stderr and halts by raising
`almasix.debug.DumpAndDie`, which the HTTP and console kernels catch and render
as a dump page. It returns nothing — execution after the call does not run.

```python title="examples/collections.py"
collect([1, 2, 3]).dd()
```

The dump goes to stderr as a titled panel containing `[1, 2, 3]`, followed by a
`halted` rule. Use `dump` if you want to keep going.

### diff

Returns the values that are not present in the given items. Comparison is done
through a `set`, so every value on both sides must be hashable.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).diff([2, 4, 6]).all()

# [1, 3, 5]
```

`diff` does not preserve the original keys — the surviving values are
reindexed from zero:

```python title="examples/collections.py"
result = collect({"a": 1, "b": 2}).diff([1]).all()

# [2]
```

### diff_assoc

Compares keys *and* values, returning the pairs from this collection that are
either missing from the given items or present with a different value.

```python title="examples/collections.py"
result = collect({"colour": "orange", "type": "fruit", "qty": 5}).diff_assoc(
    {"colour": "yellow", "type": "fruit", "qty": 3}
).all()

# {'colour': 'orange', 'qty': 5}
```

### diff_assoc_using

Like `diff_assoc`, but a callback decides whether two values count as equal. The
callback receives this collection's value first and the other side's value
second, and returns `True` when they match; pairs whose keys are missing from
the other side are always kept.

```python title="examples/collections.py"
result = collect({"colour": "orange", "type": "fruit"}).diff_assoc_using(
    {"colour": "ORANGE", "type": "veg"},
    lambda mine, theirs: str(mine).lower() == str(theirs).lower(),
).all()

# {'type': 'fruit'}
```

The callback compares the *values*, not the keys.

### diff_keys

Returns the pairs whose keys are not present in the given items. Only the other
side's keys are looked at — its values are ignored.

```python title="examples/collections.py"
result = collect({"one": 10, "two": 20, "three": 30}).diff_keys({"two": 2, "four": 4}).all()

# {'one': 10, 'three': 30}
```

### doesnt_contain

The negation of `contains`, and it accepts the same arguments: a value, a
predicate, a key and a value, or a key, an operator and a value.

```python title="examples/collections.py"
result = collect([1, 2, 3]).doesnt_contain(5)

# True
```

### doesnt_contain_strict

The negation of `contains_strict` — reports that no item *is* the given object.

```python title="examples/collections.py"
result = collect([[1], [2]]).doesnt_contain_strict([1])

# True
```

### dot

Flattens a nested collection into a single-level collection whose keys are dot
notation paths. List indices become path segments too, and empty containers are
kept as-is under their own path.

```python title="examples/collections.py"
result = collect({"products": {"desk": {"price": 100}}}).dot().all()

# {'products.desk.price': 100}

with_lists = collect({"tags": ["a", "b"], "empty": {}}).dot().all()

# {'tags.0': 'a', 'tags.1': 'b', 'empty': {}}
```

### dump

Prints the collection's contents to stderr and returns the collection, so it can
be dropped into the middle of a chain without breaking it.

```python title="examples/collections.py"
result = collect([1, 2, 3]).dump().map(lambda item: item * 2).all()

# [2, 4, 6]
```

Alongside the returned value, a titled panel containing `[1, 2, 3]` is written
to stderr. Use `dd` to stop instead of continuing.

### duplicates

Returns the items that appear more than once, keyed by the position of the
repeat rather than of the first occurrence. Pass a key or a callable to look for
duplicates of a derived value, in which case the derived value is what you get
back.

```python title="examples/collections.py"
result = collect(["a", "b", "a", "c", "b"]).duplicates().all()

# {2: 'a', 4: 'b'}

by_key = collect([{"role": "admin"}, {"role": "user"}, {"role": "admin"}]).duplicates("role").all()

# {2: 'admin'}
```

### duplicates_strict

Like `duplicates`, but items are compared by identity (`is`) instead of
equality, so only the same object repeated counts as a duplicate.

```python title="examples/collections.py"
row = [1]
result = collect([row, row, [1]]).duplicates_strict().all()

# {1: [1]}
```

### each

Runs the callback over every item and returns the collection unchanged. The
callback is offered `(item, key)` and falls back to `(item)` if it does not
accept two arguments. Returning `False` from the callback stops the iteration
early.

```python title="examples/collections.py"
log = []
collect([1, 2, 3, 4]).each(lambda item: log.append(item) if item < 3 else False)

# log is [1, 2]
```

Also available as a higher order message.

### each_spread

Like `each`, but each item that is a list or tuple is unpacked into the
callback's arguments.

```python title="examples/collections.py"
pairs = []
collect([[1, "a"], [2, "b"]]).each_spread(lambda number, letter: pairs.append(f"{number}{letter}"))

# pairs is ['1a', '2b']
```

### ensure

Asserts that every item is an instance of the given type and returns the
collection. The first item that is not raises `TypeError`.

```python title="examples/collections.py"
result = collect([1, 2, 3]).ensure(int).all()

# [1, 2, 3]

# collect([1, "two"]).ensure(int)
# TypeError: Collection item is not an instance of <class 'int'>
```

### every

Reports whether the callback returns truthy for every item. An empty collection
returns `True`.

```python title="examples/collections.py"
result = collect([1, 2, 3]).every(lambda item: item > 0)

# True

stricter = collect([1, 2, 3]).every(lambda item: item > 2)

# False
```

Also available as a higher order message.

### except_

Returns every pair except those with the given keys. Keys may be passed as
separate arguments or as one list, tuple or set.

```python title="examples/collections.py"
result = collect({"id": 1, "name": "Sara", "age": 30}).except_("age").all()

# {'id': 1, 'name': 'Sara'}

several = collect({"id": 1, "name": "Sara", "age": 30}).except_(["name", "age"]).all()

# {'id': 1}
```

The trailing underscore avoids the Python keyword `except`.

### except_keys

Alias for `except_`, for when the trailing underscore reads badly.

```python title="examples/collections.py"
result = collect({"id": 1, "name": "Sara"}).except_keys("name").all()

# {'id': 1}
```

### filter

Keeps the items for which the callback returns truthy, preserving the original
keys — which means filtering a list generally gives you a `dict` back, and you
need `values()` to renumber it. Called with no callback, it keeps the items that
are truthy in themselves.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).filter(lambda item: item > 2).all()

# {2: 3, 3: 4}

renumbered = collect([1, 2, 3, 4]).filter(lambda item: item > 2).values().all()

# [3, 4]

truthy = collect([1, 0, 2, None, 3, ""]).filter().all()

# {0: 1, 2: 2, 4: 3}
```

The callback is offered `(item, key)` and falls back to `(item)`. Also available
as a higher order message.

### first

Returns the first item, or the first item matching a predicate. A non-callable
sole argument is read as the default instead of a predicate, so `first(0)`
returns `0` for an empty collection rather than searching for `0`.

```python title="examples/collections.py"
result = collect([1, 2, 3]).first(lambda item: item > 1)

# 2

fallback = collect([]).first("none")

# 'none'

no_match = collect([1, 2]).first(lambda item: item > 5, "missing")

# 'missing'
```

Also available as a higher order message.

### first_or_fail

Returns the first item (optionally the first matching a predicate) and raises
`almasix.support.collection.ItemNotFoundError` when there is none.

```python title="examples/collections.py"
result = collect([1, 2, 3]).first_or_fail(lambda item: item > 2)

# 3

# collect([1, 2, 3]).first_or_fail(lambda item: item > 5)
# ItemNotFoundError: Item not found.
```

The check is `item is None`, so a collection whose first item is genuinely
`None` raises even though an item was found.

### first_where

Returns the first item matching a key/value pair, or a key, operator and value.
Returns `None` when nothing matches.

```python title="examples/collections.py"
books = [{"name": "Refactoring", "pages": 448}, {"name": "Clean Code", "pages": 464}]

result = collect(books).first_where("pages", 464)

# {'name': 'Clean Code', 'pages': 464}

with_operator = collect(books).first_where("pages", ">", 450)

# {'name': 'Clean Code', 'pages': 464}
```

### flat_map

Maps every item through the callback and then collapses the result one level, so
a callback that returns a list contributes its elements rather than the list.

```python title="examples/collections.py"
result = collect([{"tags": ["a", "b"]}, {"tags": ["c"]}]).flat_map(lambda item: item["tags"]).all()

# ['a', 'b', 'c']
```

Also available as a higher order message.

### flatten

Flattens a nested structure into a single-level collection. Pass a depth to
limit how far it descends; the default is unlimited. Mapping values are
flattened in, and strings and bytes are never treated as iterables.

```python title="examples/collections.py"
result = collect([1, [2, [3, [4]]]]).flatten().all()

# [1, 2, 3, 4]

shallow = collect([1, [2, [3, [4]]]]).flatten(1).all()

# [1, 2, [3, [4]]]

from_mapping = collect({"name": "Sara", "languages": ["python", "php"]}).flatten().all()

# ['Sara', 'python', 'php']
```

### flip

Swaps keys and values. On a list-like collection the values become keys and the
integer positions become the values.

```python title="examples/collections.py"
result = collect({"name": "Sara", "framework": "almasix"}).flip().all()

# {'Sara': 'name', 'almasix': 'framework'}

from_list = collect(["a", "b"]).flip().all()

# {'a': 0, 'b': 1}
```

### for_page

Returns the slice of items belonging to the given one-based page. A page number
below one is clamped to the first page, and the last page returns however many
items remain.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5, 6, 7]).for_page(2, 3).all()

# [4, 5, 6]

last = collect([1, 2, 3, 4, 5, 6, 7]).for_page(3, 3).all()

# [7]
```

### forget

Removes the given keys **in place** and returns the same collection — unlike
most methods, the original is modified. Keys that are not present are ignored,
and remaining keys are left as they are rather than renumbered.

```python title="examples/collections.py"
items = collect({"name": "Sara", "age": 30, "city": "Cairo"})
items.forget("age")

# items.all() is {'name': 'Sara', 'city': 'Cairo'}
```

### from_json

Class method that decodes a JSON string into a new collection. Extra keyword
arguments are forwarded to `json.loads`.

```python title="examples/collections.py"
result = Collection.from_json("[1, 2, 3]").all()

# [1, 2, 3]

mapping = Collection.from_json('{"name": "Sara"}').all()

# {'name': 'Sara'}
```

### get

Returns the value at the given key, or the default (`None` if not given) when
the key is absent. Lookup is by key only: on a list-like collection the integer
positions are the keys, so `get(1)` works but `get(-1)` does not.

```python title="examples/collections.py"
result = collect({"name": "Sara"}).get("name")

# 'Sara'

missing = collect({"name": "Sara"}).get("age", 0)

# 0
```

### group_by

Groups the items by a key or a callable, returning a collection of collections
keyed by the grouping value. Insertion order of the groups follows first
appearance.

```python title="examples/collections.py"
result = collect([{"role": "admin"}, {"role": "user"}]).group_by("role").all()

# {'admin': Collection([{'role': 'admin'}]), 'user': Collection([{'role': 'user'}])}

by_callable = collect([1, 2, 3, 4]).group_by(lambda n: "even" if n % 2 == 0 else "odd").all()

# {'odd': Collection([1, 3]), 'even': Collection([2, 4])}
```

Also available as a higher order message.

### has

Reports whether **all** of the given keys are present.

```python title="examples/collections.py"
result = collect({"a": 1, "b": 2}).has("a")

# True

both = collect({"a": 1, "b": 2}).has("a", "c")

# False
```

### has_any

Reports whether **any** of the given keys are present. The keys may be passed as
separate arguments or as a single list or tuple.

```python title="examples/collections.py"
result = collect({"a": 1, "b": 2}).has_any("c", "b")

# True

as_list = collect({"a": 1}).has_any(["x", "y"])

# False
```

### implode

Joins the items into a string. With one argument that argument is the glue and
the items are stringified directly; with two, the first is the key to pull from
each item and the second is the glue.

```python title="examples/collections.py"
result = collect([1, 2, 3]).implode("-")

# '1-2-3'

books = [{"name": "Refactoring"}, {"name": "Clean Code"}]
names = collect(books).implode("name", ", ")

# 'Refactoring, Clean Code'
```

### intersect

Returns the values that are also present in the given items, in this
collection's order. Comparison goes through a `set`, so all values must be
hashable, and duplicates on this side are all kept.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).intersect([2, 4, 6]).all()

# [2, 4]
```

As with `diff`, the original keys are not preserved — survivors are reindexed
from zero:

```python title="examples/collections.py"
result = collect({"a": 1, "b": 2}).intersect([2]).all()

# [2]
```

### intersect_assoc

Keeps the entries whose key *and* value both appear in the given items, compared
with `==`. Entries that share a key but disagree on the value are dropped.

```python title="examples/collections.py"
result = collect({"name": "iPhone", "colour": "gold", "size": 6}).intersect_assoc(
    {"name": "iPhone", "colour": "silver", "size": 6}
).all()

# {'name': 'iPhone', 'size': 6}

positions = collect([1, 2, 3]).intersect_assoc([9, 2, 3]).all()

# {1: 2, 2: 3}
```

The original keys are kept. When a list loses its first item the surviving keys
are no longer `0, 1, 2, …`, so `all()` hands back a dict rather than a list —
call `values()` first if you want a list.

### intersect_assoc_using

Like `intersect_assoc`, but the two values for a shared key are compared by your
callback instead of `==`. The callback receives this collection's value first
and the other side's value second, and returns whether they match.

```python title="examples/collections.py"
result = collect({"name": "iPhone", "colour": "GOLD"}).intersect_assoc_using(
    {"name": "iphone", "colour": "silver"},
    lambda mine, theirs: str(mine).lower() == str(theirs).lower(),
).all()

# {'name': 'iPhone'}
```

### intersect_by_keys

Keeps the entries whose *key* appears in the given items, ignoring values
entirely. The values kept are always this collection's.

```python title="examples/collections.py"
result = collect({"serial": "UX301", "type": "screen", "year": 2009}).intersect_by_keys(
    {"reference": "UX404", "type": "tab", "year": 2009}
).all()

# {'type': 'screen', 'year': 2009}
```

### intersect_using

Keeps the values that match at least one value in the given items, where
"match" is decided by your callback rather than `==`. The callback is called
with one of this collection's values and one candidate from the other side.

```python title="examples/collections.py"
result = collect(["Desk", "Sofa", "Chair"]).intersect_using(
    ["DESK", "chair", "bookcase"],
    lambda mine, theirs: mine.lower() == theirs.lower(),
).all()

# ['Desk', 'Chair']
```

Unlike the `intersect_assoc*` methods this one is value-only, and the result is
renumbered from zero rather than keeping the original keys.

### is_empty

Whether the collection has no items. Emptiness is about the number of items, not
their truthiness — a collection holding a single `0` is not empty.

```python title="examples/collections.py"
result = (collect([]).is_empty(), collect([0]).is_empty(), collect({}).is_empty())

# (True, False, True)
```

### is_not_empty

The inverse of `is_empty`.

```python title="examples/collections.py"
result = (collect([1]).is_not_empty(), collect([]).is_not_empty())

# (True, False)
```

### join

Joins the values into a string with `glue`, optionally using a different
`final_glue` before the last one. Values are passed through `str()`, and only
values are used, so a keyed collection joins its values.

```python title="examples/collections.py"
result = collect(["a", "b", "c"]).join(", ")

# 'a, b, c'

listed = collect(["a", "b", "c"]).join(", ", " and ")

# 'a, b and c'

empty = collect([]).join(", ")

# ''
```

A single item is returned on its own, with neither glue applied.

### key_by

Rekeys the collection by the given item key or callback, so each value ends up
stored under a key derived from it. When two items produce the same key the last
one wins.

```python title="examples/collections.py"
result = collect([
    {"product_id": "prod-100", "name": "Desk"},
    {"product_id": "prod-200", "name": "Chair"},
]).key_by("product_id").all()

# {'prod-100': {'product_id': 'prod-100', 'name': 'Desk'}, 'prod-200': {'product_id': 'prod-200', 'name': 'Chair'}}

upper = collect([
    {"product_id": "prod-100", "name": "Desk"},
    {"product_id": "prod-200", "name": "Chair"},
]).key_by(lambda item: item["product_id"].upper()).all()

# {'PROD-100': {'product_id': 'prod-100', 'name': 'Desk'}, 'PROD-200': {'product_id': 'prod-200', 'name': 'Chair'}}
```

The string form uses dot notation, so `key_by("owner.id")` reaches into nested
data.

### keys

Returns a new collection of the keys. A collection built from a list has the
contiguous integer keys `0, 1, 2, …`, so this is how you see them.

```python title="examples/collections.py"
result = collect({"prod-100": {"name": "Desk"}, "prod-200": {"name": "Chair"}}).keys().all()

# ['prod-100', 'prod-200']

indexes = collect(["Desk", "Chair"]).keys().all()

# [0, 1]
```

### last

Returns the last item, or the last item passing the callback. A single
non-callable argument is read as the default, so `last("empty")` means "the last
item, or `'empty'` if there is none".

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).last()

# 4

matched = collect([1, 2, 3, 4]).last(lambda value: value < 3)

# 2

fallback = collect([]).last("empty")

# 'empty'

missed = collect([1, 2]).last(lambda value: value > 5, "none")

# 'none'
```

Without a default the result is `None`.

### lazy

Returns a `LazyCollection` over this collection's values, for chaining the lazy
operations (`chunk`, `throttle`, `take_until_timeout`, `with_heartbeat`) that
only exist there. The items are already in memory, so this buys the API rather
than the memory saving; keys are dropped and only values carry over.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).lazy().filter(lambda v: v % 2 == 0).map(lambda v: v * 10).all()

# [20, 40]
```

Call `collect()` on the lazy collection to get an eager `Collection` back.

### macro

Registers a callback as a method name, callable on any collection. It is a
classmethod taking the name and the callback, and the callback receives the
collection as its first argument followed by whatever the caller passes.

```python title="examples/helpers.py"
from almasix.support import Collection

Collection.macro("to_upper", lambda collection: collection.map(lambda item: item.upper()))

result = collect(["first", "second"]).to_upper().all()

# ['FIRST', 'SECOND']
```

The registry is global and shared by every collection class: a macro registered
through a subclass is visible on `Collection` too, and the registration lasts for
the life of the process, not for one instance. Macros are resolved through
`__getattr__`, which Python only consults when normal attribute lookup fails, so
a macro named after an existing method (`count`, `map`) is registered but never
called.

### make

Builds a collection from the given items — a classmethod equivalent to calling
the class directly, and the form to use when you have a `Collection` subclass in
hand. With no argument you get an empty collection.

```python title="examples/helpers.py"
from almasix.support import Collection

result = Collection.make([1, 2, 3]).all()

# [1, 2, 3]

mapping = Collection.make({"a": 1}).all()

# {'a': 1}
```

For the plain class, `collect()` is the shorter spelling.

### map

Runs the callback over every item and returns a new collection of the results.
**Keys are preserved**, so mapping a dict-backed collection keeps its keys. A
callback taking two parameters is given `(item, key)`; a one-parameter callback
is given just the item.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).map(lambda value: value * 2).all()

# [2, 4, 6, 8]

keyed = collect({"a": 1, "b": 2}).map(lambda value, key: f"{key}={value}").all()

# {'a': 'a=1', 'b': 'b=2'}
```

The two arities are told apart by calling with two arguments and retrying with
one on `TypeError`. A callback that raises `TypeError` internally is therefore
called a second time with a single argument before the error surfaces.

### map_into

Maps every item into a new instance of the given class, calling `cls(item)`.

```python title="resources/views/examples/collections.prism.html"
from dataclasses import dataclass

@dataclass
class Currency:
    code: str

result = collect(["USD", "EUR"]).map_into(Currency).all()

# [Currency(code='USD'), Currency(code='EUR')]
```

The item is passed as a single positional argument, so the class must accept one.

### map_spread

Maps over the items, spreading each one into the callback's arguments. Use it
after a method that produces pairs, such as `zip`.

```python title="examples/collections.py"
result = collect([[1, 2], [3, 4], [5, 6]]).map_spread(lambda a, b: a + b).all()

# [3, 7, 11]
```

Only lists and tuples are spread. Items that are collections — what `chunk` and
`sliding` produce — are passed whole as a single argument (so after `chunk`,
pass a one-argument callback that receives the chunk):

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).chunk(2).map_spread(lambda chunk: chunk.sum()).all()

# [3, 7]
```

### map_to_groups

Maps each item to a single-pair `(key, value)` tuple or one-entry dict, and
groups the values by that key. Unlike `map_with_keys`, repeated keys accumulate
instead of overwriting.

```python title="examples/collections.py"
result = collect([
    {"name": "Ana", "department": "Sales"},
    {"name": "Bo", "department": "Sales"},
    {"name": "Cy", "department": "Marketing"},
]).map_to_groups(lambda item: (item["department"], item["name"])).all()

# {'Sales': Collection(['Ana', 'Bo']), 'Marketing': Collection(['Cy'])}
```

Each group is itself a collection. As with `map`, a two-parameter callback
receives `(item, key)`.

### map_with_keys

Maps each item to a `(key, value)` tuple or a dict, and builds a new collection
from those pairs. Returning a dict lets one item contribute several entries;
duplicate keys overwrite, so the last item wins.

```python title="resources/views/examples/collections.prism.html"
result = collect([
    {"name": "Ana", "email": "ana@example.com"},
    {"name": "Bo", "email": "bo@example.com"},
]).map_with_keys(lambda item: (item["name"], item["email"])).all()

# {'Ana': 'ana@example.com', 'Bo': 'bo@example.com'}

from_dict = collect([
    {"name": "Ana", "email": "ana@example.com"},
]).map_with_keys(lambda item: {item["name"]: item["email"]}).all()

# {'Ana': 'ana@example.com'}
```

### max

The largest value, optionally of an item key or a callback's result. `None`
values are ignored, and an empty collection gives `None` rather than raising.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).max()

# 5

by_key = collect([{"foo": 10}, {"foo": 20}]).max("foo")

# 20

by_callback = collect(["ab", "c"]).max(len)

# 2
```

The callback form returns the largest derived value, not the item that produced
it — use `sort_by_desc(...).first()` for that.

### median

The median of the values, optionally of an item key or a callback's result.
`None` values are ignored and an empty collection gives `None`. An even number of
values yields the mean of the middle two, so the result may be a float even when
every input is an integer.

```python title="examples/collections.py"
result = collect([1, 1, 2, 4]).median()

# 1.5

odd = collect([1, 3, 3, 6, 7, 8, 9]).median()

# 6

by_key = collect([{"foo": 10}, {"foo": 10}, {"foo": 20}, {"foo": 40}]).median("foo")

# 15.0
```

### merge

Merges the given items into a new collection. When both sides are list-like the
items are appended; otherwise the given items are merged by key, and colliding
keys take the *incoming* value.

```python title="examples/collections.py"
result = collect(["Desk", "Chair"]).merge(["Bookcase", "Door"]).all()

# ['Desk', 'Chair', 'Bookcase', 'Door']

keyed = collect({"product_id": 1, "price": 100}).merge({"price": 200, "discount": False}).all()

# {'product_id': 1, 'price': 200, 'discount': False}
```

Mixing the two shapes merges by key, which puts the list's integer keys and the
dict's string keys side by side:

```python title="examples/collections.py"
mixed = collect(["Desk"]).merge({"price": 100}).all()

# {0: 'Desk', 'price': 100}
```

`concat` is the same method under another name.

### merge_recursive

Merges by key like `merge`, but descends into nested dicts instead of replacing
them outright. Anything that is not a dict on both sides is replaced by the
incoming value.

```python title="examples/collections.py"
result = collect({"db": {"host": "localhost", "port": 5432}, "debug": False}).merge_recursive(
    {"db": {"port": 6543}, "debug": True}
).all()

# {'db': OrderedDict({'host': 'localhost', 'port': 6543}), 'debug': True}
```

Colliding scalars are replaced by the incoming value rather than turned into
a list of both. Merged sub-dicts come back as `OrderedDict` instances, which
compare equal to plain dicts but print differently.

### min

The smallest value, optionally of an item key or a callback's result. `None`
values are ignored, and an empty collection gives `None`.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).min()

# 1

by_key = collect([{"foo": 10}, {"foo": 20}]).min("foo")

# 10
```

### mode

The most frequently occurring value(s), optionally of an item key or a callback's
result. It always returns a plain **list**, because ties are all reported, and
`None` for an empty collection.

```python title="examples/collections.py"
result = collect([1, 1, 2, 4]).mode()

# [1]

tied = collect([1, 1, 2, 2]).mode()

# [1, 2]

by_key = collect([{"foo": 10}, {"foo": 10}, {"foo": 20}]).mode("foo")

# [10]
```

Note that this is a list, not a collection — the only aggregate in this group
that returns a bare Python list.

### multiply

Repeats every item the given number of times, concatenated end to end. A
non-positive count gives an empty collection.

```python title="examples/collections.py"
result = collect(["Desk", "Chair"]).multiply(3).all()

# ['Desk', 'Chair', 'Desk', 'Chair', 'Desk', 'Chair']

none = collect(["Desk"]).multiply(0).all()

# []
```

Keys are dropped and the result is renumbered from zero, so this works on keyed
collections too — it copies the values only.

### nth

Every `step`-th value, optionally starting at `offset` rather than the first
item.

```python title="examples/collections.py"
result = collect(["a", "b", "c", "d", "e", "f"]).nth(4).all()

# ['a', 'e']

offset = collect(["a", "b", "c", "d", "e", "f"]).nth(4, 1).all()

# ['b', 'f']
```

The offset counts items, not keys, and the result is renumbered from zero.

### only

Keeps only the entries with the given keys. Keys are accepted as separate
arguments or as one list, tuple, or set, and unknown keys are ignored rather
than producing `None`.

```python title="examples/collections.py"
result = collect({"product_id": 1, "name": "Desk", "price": 100, "discount": False}).only(
    "product_id", "name"
).all()

# {'product_id': 1, 'name': 'Desk'}

positions = collect(["Desk", "Chair", "Bookcase"]).only([0, 2]).all()

# {0: 'Desk', 2: 'Bookcase'}
```

Two details follow from the key preservation: entries come back in the order you
asked for them, not in collection order, and selecting non-adjacent positions
from a list gives a dict. `except_` is the inverse.

### pad

Pads the collection to `size` with `value`. A positive size pads on the right, a
negative size pads on the left, and a size the collection already reaches leaves
it untouched.

```python title="examples/collections.py"
result = collect(["A", "B", "C"]).pad(5, 0).all()

# ['A', 'B', 'C', 0, 0]

left = collect(["A", "B", "C"]).pad(-5, 0).all()

# [0, 0, 'A', 'B', 'C']

unchanged = collect(["A", "B", "C"]).pad(2, 0).all()

# ['A', 'B', 'C']
```

### partition

Splits the collection in two by a predicate: the items that pass, then the items
that do not. It returns a collection of two collections, which unpacks directly
into a pair of names.

```python title="examples/collections.py"
under, over = collect([1, 2, 3, 4, 5, 6]).partition(lambda value: value < 3)
result = (under.all(), over.all())

# ([1, 2], [3, 4, 5, 6])
```

Both halves are renumbered from zero.

### percentage

The percentage of items matching the callback, rounded to `precision` decimal
places (2 by default). An empty collection gives `0.0` instead of dividing by
zero.

```python title="examples/collections.py"
result = collect([1, 1, 2, 2, 2, 3]).percentage(lambda value: value == 1)

# 33.33

rounded = collect([1, 1, 2, 2, 2, 3]).percentage(lambda value: value == 1, precision=0)

# 33.0
```

The return is always a float, so `precision=0` gives `33.0` rather than `33`.

### pipe

Passes the collection to the callback and returns whatever the callback returns.
Use it to keep a chain going through an operation the collection does not have.

```python title="examples/collections.py"
result = collect([1, 2, 3]).pipe(lambda collection: collection.sum())

# 6
```

### pipe_into

Passes the collection to the given class's constructor and returns the new
instance. The class receives the `Collection` itself, not a list.

```python title="examples/collections.py"
class ResourceCollection:
    def __init__(self, collection):
        self.collection = collection

    def __repr__(self):
        return f"ResourceCollection({self.collection.all()!r})"

result = collect([1, 2, 3]).pipe_into(ResourceCollection)

# ResourceCollection([1, 2, 3])
```

### pipe_through

Passes the collection through an iterable of callbacks in order, feeding each
one the previous result. The final callback decides the return type.

```python title="examples/collections.py"
result = collect([1, 2, 3]).pipe_through([
    lambda collection: collection.map(lambda value: value * 2),
    lambda collection: collection.sum(),
])

# 12
```

### pluck

Retrieves one key from every item. The `value` argument is the key to read and
supports dot notation for nested data.

```python title="examples/collections.py"
result = collect([
    {"product_id": "prod-100", "name": "Desk"},
    {"product_id": "prod-200", "name": "Chair"},
]).pluck("name").all()

# ['Desk', 'Chair']

nested = collect([{"speakers": {"first": "Ana"}}]).pluck("speakers.first").all()

# ['Ana']
```

A second argument names the key to index the result by — and in that form Almasix
returns a **plain dict**, not a collection, so there is nothing to chain onto and
no `.all()` to call:

```python title="examples/collections.py"
keyed = collect([
    {"product_id": "prod-100", "name": "Desk"},
    {"product_id": "prod-200", "name": "Chair"},
]).pluck("name", "product_id")

# {'prod-100': 'Desk', 'prod-200': 'Chair'}
```

Both forms return a plain dict (or list), not a collection.

### pop

Removes and returns the last item, **mutating the collection in place**. With a
count above one it removes that many and returns them as a collection, in their
original order.

```python title="examples/collections.py"
items = collect([1, 2, 3, 4, 5])
result = items.pop()

# 5

remaining = items.all()

# [1, 2, 3, 4]

removed = items.pop(2).all()

# [3, 4]

left = items.all()

# [1, 2]
```

Popping from an empty collection returns `None`. Integer keys are renumbered
afterwards; other keys are left alone.

### prepend

Adds an item to the front, **mutating the collection in place** and returning it
for chaining. A second argument gives the new item a key.

```python title="examples/collections.py"
items = collect([1, 2, 3])
result = items.prepend(0).all()

# [0, 1, 2, 3]

mapping = collect({"one": 1}).prepend(0, "zero").all()

# {'zero': 0, 'one': 1}
```

Without a key the whole collection is renumbered from zero, which discards any
existing keys — `collect({"one": 1}).prepend(0).all()` gives `[0, 1]`, not a
dict. Pass a key when the collection has them.

### pull

Removes the entry with the given key and returns its value, **mutating the
collection in place**. A missing key returns the default instead of raising.

```python title="examples/collections.py"
items = collect({"product_id": "prod-100", "name": "Desk"})
result = items.pull("name")

# 'Desk'

remaining = items.all()

# {'product_id': 'prod-100'}

fallback = items.pull("missing", "default")

# 'default'
```

The key is a map key, so on a list-backed collection it is the index, and the
remaining items are *not* renumbered.

### push

Appends one or more items to the end, **mutating the collection in place** and
returning it for chaining.

```python title="examples/collections.py"
items = collect([1, 2, 3])
result = items.push(4).all()

# [1, 2, 3, 4]

more = items.push(5, 6).all()

# [1, 2, 3, 4, 5, 6]
```

The key for each new item is one past the highest integer key, or the current
item count when there are no integer keys — so pushing onto a keyed collection
mixes in an integer key: `collect({"a": 1}).push("b").all()` gives
`{'a': 1, 1: 'b'}`.

### put

Sets a key to a value, **mutating the collection in place** and returning it for
chaining.

```python title="examples/collections.py"
items = collect({"product_id": 1, "name": "Desk"})
result = items.put("price", 100).all()

# {'product_id': 1, 'name': 'Desk', 'price': 100}
```

On a list-backed collection the key is the index, so `put(1, "x")` overwrites
the second item, and putting a key beyond the end leaves a gap rather than
extending the list.

### random

Returns one item chosen at random, or a collection of `count` items when a count
is given. The results differ per call, so the example below checks membership
rather than printing a value.

```python title="examples/collections.py"
value = collect([1, 2, 3, 4, 5]).random()
result = value in [1, 2, 3, 4, 5]

# True

sample = collect([1, 2, 3, 4, 5]).random(3).count()

# 3
```

Asking for more items than there are quietly clamps to the collection size —
`collect([1, 2]).random(5).count()` is `2` rather than raising. An empty
collection returns `None`, or an empty collection when a count was given.

### range

Builds a collection of integers from `start` to `end`, a classmethod rather than
an instance method. Both ends are **inclusive**, and the range counts down when
`end` is below `start`.

```python title="examples/helpers.py"
from almasix.support import Collection

result = Collection.range(1, 5).all()

# [1, 2, 3, 4, 5]

down = Collection.range(5, 1).all()

# [5, 4, 3, 2, 1]
```

`Collection.range(3, 3)` gives `[3]`, not an empty collection — unlike Python's
own `range`.

### reduce

Reduces the collection to a single value, calling the callback with the carry
and each item. Without an initial value the first item becomes the carry and the
reduction starts from the second.

```python title="examples/collections.py"
result = collect([1, 2, 3]).reduce(lambda carry, item: carry + item)

# 6

seeded = collect([1, 2, 3]).reduce(lambda carry, item: carry + item, 10)

# 16
```

With no initial value, the first item becomes the carry and the callback runs
for the rest. Because `None` is the marker for "no initial value", you cannot
deliberately start from `None` here. An empty collection returns `None`.

### reduce_spread

Reduces where each item is a list or tuple spread across the callback's
arguments after the carry.

```python title="examples/collections.py"
result = collect([[1, 2], [3, 4]]).reduce_spread(lambda carry, a, b: carry + (a * b), 0)

# 14
```

The *item* is spread into the callback after the carry; the callback returns
a single accumulator value.

### reject

The inverse of `filter`: keeps the items for which the callback returns false.
Keys are preserved. A non-callable argument rejects the items equal to it.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).reject(lambda value: value > 2).all()

# [1, 2]

by_value = collect([1, 2, 3, 2]).reject(2).all()

# {0: 1, 2: 3}
```

The second result is a dict because keys `0` and `2` survived and are no longer
contiguous. Chain `values()` to renumber:
`collect([1, 2, 3, 2]).reject(2).values().all()` gives `[1, 3]`.

### replace

Overwrites entries by key with the given items, adding keys that did not exist.

```python title="examples/collections.py"
result = collect(["Taylor", "Abigail", "James"]).replace({1: "Victoria", 3: "Finn"}).all()

# ['Taylor', 'Victoria', 'James', 'Finn']

keyed = collect({"a": 1, "b": 2}).replace({"b": 20, "c": 30}).all()

# {'a': 1, 'b': 20, 'c': 30}
```

The first result is a list because the replacement filled key `3`, keeping the
keys contiguous. Unlike `merge`, a list replacement is matched up by index rather
than appended.

### replace_recursive

Replaces by key, descending into nested dicts rather than overwriting them
wholesale.

```python title="examples/collections.py"
result = collect({"db": {"host": "localhost", "port": 5432}}).replace_recursive(
    {"db": {"port": 6543}}
).all()

# {'db': OrderedDict({'host': 'localhost', 'port': 6543})}
```

In Almasix this is an alias for `merge_recursive`, so it only recurses into
dicts: nested lists are replaced as a whole rather than merged by index. As
with `merge_recursive`, nested results are `OrderedDict` instances.

### reverse

Reverses the order of the items, **keeping each item with its key**.

```python title="examples/collections.py"
result = collect(["a", "b", "c"]).reverse().all()

# {2: 'c', 1: 'b', 0: 'a'}

renumbered = collect(["a", "b", "c"]).reverse().values().all()

# ['c', 'b', 'a']
```

This catches people out: reversing a list-backed collection leaves the keys as
`2, 1, 0`, which is no longer contiguous, so `all()` returns a dict. Chain
`values()` when you want a list back.

### search

Returns the key of the first matching item, or `False` when nothing matches.
The argument is either a value to look for or a predicate.

```python title="examples/collections.py"
result = collect([2, 4, 6, 8]).search(4)

# 1

by_callback = collect([2, 4, 6, 8]).search(lambda value: value > 5)

# 2

missing = collect([2, 4, 6, 8]).search(9)

# False
```

Pass `strict=True` to compare by identity rather than `==`, which rules out
matches like `4 == 4.0`: `collect([2, 4, 6, 8]).search(4.0)` is `1`, while
`search(4.0, strict=True)` is `False`. Since a found key may itself be falsy —
searching for the first item returns `0` — test the result with `is False`
rather than a plain truthiness check. On a keyed collection the map key is
returned.

### select

Reduces every item to a dict of just the named keys, the multi-key counterpart
to `pluck`. Keys are accepted as separate arguments or as one list or tuple, and
each name goes through dot notation — a dotted name reads the nested value but
keeps the whole dotted string as the key.

```python title="examples/collections.py"
result = collect([
    {"name": "Ana", "role": "dev", "age": 30},
    {"name": "Bo", "role": "ops", "age": 40},
]).select("name", "role").all()

# [{'name': 'Ana', 'role': 'dev'}, {'name': 'Bo', 'role': 'ops'}]
```

A key an item does not have comes back as `None` rather than being omitted:
`collect([{"name": "Ana"}]).select("name", "missing").all()` gives
`[{'name': 'Ana', 'missing': None}]`. The collection's own keys are preserved.

### shift

Removes and returns the first item, **mutating the collection in place**. With a
count above one it removes that many and returns them as a collection.

```python title="examples/collections.py"
items = collect([1, 2, 3, 4, 5])
result = items.shift()

# 1

remaining = items.all()

# [2, 3, 4, 5]

removed = items.shift(2).all()

# [2, 3]

left = items.all()

# [4, 5]
```

Shifting an empty collection returns `None`. Integer keys are renumbered
afterwards, so the collection stays list-like; other keys are left alone.

### shuffle

Returns a new collection with the items in random order. The original is left
untouched, and keys are dropped in favour of a fresh numbering.

```python title="examples/collections.py"
shuffled = collect([1, 2, 3, 4, 5]).shuffle()
result = sorted(shuffled.all())

# [1, 2, 3, 4, 5]
```

The order differs on every call, so the example sorts the result to have
something stable to show. Seed Python's `random` module beforehand if you need a
repeatable shuffle in a test.

### skip

Returns a new collection with the first `count` items dropped. Keys are not
preserved — the remaining values are reindexed from zero.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).skip(2).all()

# [3, 4, 5]
```

### skip_until

Drops items until the given callback returns true, then keeps everything from
that point on. Passing a plain value instead of a callback skips until an item
equals it. If nothing ever matches, the result is empty.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).skip_until(lambda n: n >= 3).all()

# [3, 4]

result = collect([1, 2, 3, 4]).skip_until(3).all()

# [3, 4]
```

### skip_while

Drops items while the callback returns true, then keeps the rest — including
later items that would also fail the test. Unlike `skip_until`, this takes a
callback only, not a value.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 1]).skip_while(lambda n: n < 3).all()

# [3, 4, 1]
```

### slice

Returns a slice of the collection starting at `start`, optionally limited to
`length` items. Keys are reindexed rather than preserved. A negative `length`
is ignored rather than counting back from the end, so
`slice(2, -1)` gives the same result as `slice(2)`.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5, 6]).slice(2).all()

# [3, 4, 5, 6]

result = collect([1, 2, 3, 4, 5, 6]).slice(2, 3).all()

# [3, 4, 5]
```

### sliding

Returns a collection of overlapping windows of `size` items, advanced by `step`
each time. Each window is itself a collection, so `.all()` on the outer
collection gives you `Collection` reprs — map over it if you want plain lists.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).sliding(2).map(lambda chunk: chunk.all()).all()

# [[1, 2], [2, 3], [3, 4], [4, 5]]

result = collect([1, 2, 3, 4, 5]).sliding(3, step=2).map(lambda chunk: chunk.all()).all()

# [[1, 2, 3], [3, 4, 5]]
```

### sole

Returns the single item matching the optional callback. Raises
`ItemNotFoundError` when nothing matches and `MultipleItemsFoundError` when more
than one item does; both are `LookupError` subclasses exported from
`almasix.support`. Almasix accepts a callback only — not a key/operator/value
triple.

```python title="examples/helpers.py"
from almasix.support import collect, MultipleItemsFoundError

result = collect([1, 2, 3]).sole(lambda n: n == 2)

# 2

try:
    collect([1, 2, 3]).sole(lambda n: n > 1)
except MultipleItemsFoundError as exc:
    result = type(exc).__name__

# MultipleItemsFoundError
```

### some

Alias for `contains`, and accepts the same three forms (a callback, a bare
value, or a key with an optional operator).

```python title="examples/collections.py"
result = collect([1, 2, 3]).some(lambda n: n > 2)

# True

result = collect([{"votes": 50}]).some("votes", ">", 10)

# True
```

### sort

Sorts the values with Python's `sorted`. The optional callback is a **key
function** (as in `sorted(key=...)`), not a two-argument comparator. Keys are
discarded and the result is reindexed, so a keyed
collection comes back as a list.

```python title="examples/collections.py"
result = collect([5, 3, 1, 2, 4]).sort().all()

# [1, 2, 3, 4, 5]

result = collect(["ccc", "a", "bb"]).sort(len).all()

# ['a', 'bb', 'ccc']
```

### sort_by

Sorts by the value at the given key, which may be a dot-notation string or a
callable applied to each item. Pass `descending=True` to reverse, or use
`sort_by_desc`.

```python title="examples/collections.py"
items = [{"name": "Desk", "price": 200}, {"name": "Chair", "price": 100}, {"name": "Bookcase", "price": 150}]
result = collect(items).sort_by("price").pluck("name").all()

# ['Chair', 'Bookcase', 'Desk']

result = collect(["bb", "a", "ccc"]).sort_by(len).all()

# ['a', 'bb', 'ccc']
```

### sort_by_desc

`sort_by` with `descending=True`. Takes a key or a callable, but no `descending`
argument of its own.

```python title="examples/collections.py"
items = [{"name": "Desk", "price": 200}, {"name": "Chair", "price": 100}]
result = collect(items).sort_by_desc("price").pluck("name").all()

# ['Desk', 'Chair']
```

### sort_desc

Sorts the values in reverse order. Unlike `sort`, it accepts no callback — for a
descending sort by a derived value use `sort_by_desc`.

```python title="examples/collections.py"
result = collect([5, 3, 1, 2, 4]).sort_desc().all()

# [5, 4, 3, 2, 1]
```

### sort_keys

Sorts by key rather than by value, keeping each key paired with its value. Only
meaningful on a keyed collection.

```python title="examples/collections.py"
result = collect({"id": 1, "first": "John", "last": "Doe"}).sort_keys().all()

# {'first': 'John', 'id': 1, 'last': 'Doe'}
```

### sort_keys_desc

`sort_keys` in reverse key order.

```python title="examples/collections.py"
result = collect({"id": 1, "first": "John", "last": "Doe"}).sort_keys_desc().all()

# {'last': 'Doe', 'id': 1, 'first': 'John'}
```

### sort_keys_using

Sorts by key using the callback to derive the sort value for each key. The
callback is a key function receiving one key and returning something sortable.

```python title="examples/collections.py"
result = collect({"ID": 1, "first": "John", "last": "Doe"}).sort_keys_using(str.lower).all()

# {'first': 'John', 'ID': 1, 'last': 'Doe'}
```

### splice

Removes `length` items starting at `offset` and returns them as a new
collection, **mutating the original in place**. Omitting `length` removes
everything from `offset` onwards. A `replacement` iterable is spliced in where
the removed items were.

```python title="examples/collections.py"
items = collect([1, 2, 3, 4, 5])
removed = items.splice(1, 2)

# removed.all() == [2, 3], items.all() == [1, 4, 5]

items = collect([1, 2, 3, 4, 5])
removed = items.splice(1, 2, [10, 11])

# removed.all() == [2, 3], items.all() == [1, 10, 11, 4, 5]
```

### split

Splits the collection into exactly `number_of_groups` groups, distributing any
remainder into the earliest groups. Asking for more groups than there are items
yields empty groups at the end, rather than fewer groups.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).split(3).map(lambda group: group.all()).all()

# [[1, 2], [3, 4], [5]]

result = collect([1, 2]).split(4).map(lambda group: group.all()).all()

# [[1], [2], [], []]
```

### split_in

Splits into groups of a fixed size — `ceil(count / number_of_groups)` — so the
last group takes whatever is left. This differs from `split`, which balances the
groups instead.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]).split_in(3).map(lambda group: group.all()).all()

# [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10]]
```

### sum

Sums the items. The optional argument is a dot-notation key or a callable used
to pull the number out of each item. `None` values are skipped rather than
raising.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4, 5]).sum()

# 15

result = collect([{"pages": 176}, {"pages": 1096}]).sum("pages")

# 1272

result = collect([{"p": [1, 2]}, {"p": [3]}]).sum(lambda item: len(item["p"]))

# 3
```

### take

Returns the first `limit` items, or the last `abs(limit)` items when `limit` is
negative.

```python title="examples/collections.py"
result = collect([0, 1, 2, 3, 4, 5]).take(3).all()

# [0, 1, 2]

result = collect([0, 1, 2, 3, 4, 5]).take(-2).all()

# [4, 5]
```

### take_until

Keeps items until the callback returns true, stopping before the matching item.
Passing a plain value instead of a callback stops at the first item equal to it.

```python title="examples/collections.py"
result = collect([1, 2, 3, 4]).take_until(lambda n: n >= 3).all()

# [1, 2]

result = collect([1, 2, 3, 4]).take_until(3).all()

# [1, 2]
```

### take_while

Keeps items while the callback returns true and stops at the first failure, so
later passing items are not included. Callback only — no value form.

```python title="examples/collections.py"
result = collect([1, 2, 3, 1]).take_while(lambda n: n < 3).all()

# [1, 2]
```

### tap

Hands the collection to the callback and returns the same collection, letting
you inspect or act on it mid-chain without breaking the chain. The callback's
return value is discarded.

```python title="examples/collections.py"
result = collect([2, 4, 3]).sort().tap(lambda c: print(c.all())).map(lambda n: n * 2).all()

# tap prints [2, 3, 4]
# result is [4, 6, 8]
```

### times

Class method that builds a collection by invoking the callback with the numbers
`1` through `count` — note the index is 1-based, not 0-based. Without a callback
you get the numbers themselves.

```python title="examples/helpers.py"
from almasix.support import Collection

result = Collection.times(4, lambda n: n * 9).all()

# [9, 18, 27, 36]

result = Collection.times(3).all()

# [1, 2, 3]
```

### to_array

Alias for `all()`: a list when the keys are a contiguous range from zero, a dict
otherwise. It is **not** recursive — nested collections are returned as
`Collection` objects, not converted.

```python title="examples/collections.py"
result = collect({"a": 1, "b": 2}).to_array()

# {'a': 1, 'b': 2}

result = collect([collect([1, 2])]).to_array()

# [Collection([1, 2])]
```

### to_json

Serialises `to_array()` with `json.dumps`. Any keyword arguments are passed
straight through to `json.dumps`, and `default=str` is applied so values without
a JSON representation are stringified instead of raising.

```python title="examples/collections.py"
result = collect({"name": "Desk", "price": 200}).to_json()

# {"name": "Desk", "price": 200}

result = collect({"b": 1, "a": 2}).to_json(sort_keys=True)

# {"a": 2, "b": 1}
```

### to_pretty_json

`to_json` with `indent=4` defaulted in. Keyword arguments still reach
`json.dumps`, so passing `indent` explicitly overrides the default.

```python title="examples/collections.py"
result = collect({"name": "Desk"}).to_pretty_json()

# {
#     "name": "Desk"
# }

result = collect({"name": "Desk"}).to_pretty_json(indent=2)

# {
#   "name": "Desk"
# }
```

### transform

Applies the callback to every item and **replaces the collection's contents in
place**, returning the same collection rather than a new one. Use `map` when you
want a new collection. The callback may take `(item)` or `(item, key)`.

```python title="examples/collections.py"
items = collect([1, 2, 3, 4, 5])
items.transform(lambda n: n * 2)

# items.all() == [2, 4, 6, 8, 10]

result = collect({"a": 1, "b": 2}).transform(lambda v, k: f"{k}={v}").all()

# {'a': 'a=1', 'b': 'b=2'}
```

### undot

Expands dot-notation keys into a nested dict. It is the inverse of `dot`, but
numeric segments become string keys rather than list indices, so a round trip
through `dot().undot()` does not restore lists.

```python title="examples/collections.py"
result = collect({"name.first_name": "Marie", "name.last_name": "Valentine"}).undot().all()

# {'name': {'first_name': 'Marie', 'last_name': 'Valentine'}}

result = collect({"a.0": "x", "a.1": "y"}).undot().all()

# {'a': {'0': 'x', '1': 'y'}}
```

### union

Adds the given items to the collection, keeping the original value whenever a
key collides. For list-like collections the keys are the integer indices, so
unioning a longer list only picks up the items past the end.

```python title="examples/collections.py"
result = collect({"a": "hello"}).union({"a": "bye", "b": "world"}).all()

# {'a': 'hello', 'b': 'world'}

result = collect([1, 2, 3]).union([4, 5, 6, 7]).all()

# [1, 2, 3, 7]
```

### unique

Returns the items with duplicates removed, comparing with `==`. The optional
argument is a key or callable that produces the value to compare on. Keys are
preserved, so removing items from a list-like collection leaves gaps and
`.all()` returns a dict — chain `.values()` to get a list back.

```python title="examples/collections.py"
result = collect([1, 1, 2, 2, 3, 4, 2]).unique().all()

# {0: 1, 2: 2, 4: 3, 5: 4}

result = collect([1, 1, 2, 2, 3, 4, 2]).unique().values().all()

# [1, 2, 3, 4]

items = [{"n": "iPhone", "b": "Apple"}, {"n": "iPad", "b": "Apple"}, {"n": "Galaxy", "b": "Samsung"}]
result = collect(items).unique("b").pluck("n").all()

# ['iPhone', 'Galaxy']
```

### unique_strict

`unique` with identity (`is`) comparison instead of `==`, so equal-but-distinct
objects are both kept.

```python title="examples/collections.py"
first, second = [1], [1]
result = collect([first, second, first]).unique_strict().all()

# [[1], [1]]

result = collect([first, second, first]).unique().all()

# [[1]]
```

### unless

Runs the callback when the condition is falsy — the inverse of `when`. The
optional third argument runs when the condition is truthy instead. Returns
whatever the callback returns, or the collection when no branch ran.

```python title="examples/collections.py"
result = collect([1, 2, 3]).unless(False, lambda c: c.push(4)).all()

# [1, 2, 3, 4]

result = collect([1, 2, 3]).unless(True, lambda c: c.push(4), lambda c: c.push(5)).all()

# [1, 2, 3, 5]
```

### unless_empty

Runs the callback when the collection is **not** empty. Identical to
`when_not_empty`; the name reads as "unless it is empty".

```python title="examples/collections.py"
result = collect([1, 2, 3]).unless_empty(lambda c: c.push(4)).all()

# [1, 2, 3, 4]

result = collect([]).unless_empty(lambda c: c.push(4)).all()

# []
```

### unless_not_empty

Runs the callback when the collection **is** empty. Identical to `when_empty`,
and the opposite of `unless_empty`.

```python title="examples/collections.py"
result = collect([]).unless_not_empty(lambda c: c.push(4)).all()

# [4]

result = collect([1]).unless_not_empty(lambda c: c.push(4)).all()

# [1]
```

### unwrap

Class method that returns the underlying items of a collection, or the value
unchanged if it is not a collection. The counterpart to `wrap`.

```python title="examples/helpers.py"
from almasix.support import Collection

result = Collection.unwrap(collect([1, 2, 3]))

# [1, 2, 3]

result = Collection.unwrap("Desk")

# Desk
```

### value

Retrieves the value at the given dot-notation key from the **first** item,
falling back to `default`. Handy after a `where` when you only need one field.

```python title="examples/collections.py"
items = [{"product": "Desk", "price": 200}, {"product": "Speaker", "price": 400}]
result = collect(items).value("price")

# 200

result = collect([{"product": "Desk"}]).value("price", 0)

# 0
```

### values

Returns a new collection of the values with the keys reset to a contiguous range
from zero. Useful after key-preserving operations such as `filter`, `unique`, or
the `where` family.

```python title="examples/collections.py"
result = collect({10: "a", 20: "b"}).values().all()

# ['a', 'b']
```

### when

Runs the callback when the condition is truthy, and the optional third argument
when it is not. The return value is whatever the callback returns — it is not
coerced back to the collection — so a callback returning a scalar gives you that
scalar. With no branch taken, the collection itself is returned.

```python title="examples/collections.py"
result = collect([1, 2, 3]).when(True, lambda c: c.push(4)).all()

# [1, 2, 3, 4]

result = collect([1, 2, 3]).when(False, lambda c: c.push(4), lambda c: c.push(5)).all()

# [1, 2, 3, 5]

result = collect([1, 2, 3]).when(True, lambda c: c.sum())

# 6
```

### when_empty

Runs the callback only when the collection has no items, with an optional
default callback for the non-empty case.

```python title="examples/collections.py"
result = collect([]).when_empty(lambda c: c.push("adam")).all()

# ['adam']

result = collect(["michael"]).when_empty(lambda c: c.push("adam")).all()

# ['michael']
```

### when_not_empty

Runs the callback only when the collection has at least one item — the mirror of
`when_empty`.

```python title="examples/collections.py"
result = collect(["michael"]).when_not_empty(lambda c: c.push("adam")).all()

# ['michael', 'adam']

result = collect([]).when_not_empty(lambda c: c.push("adam")).all()

# []
```

### where

Filters by comparing the value at a dot-notation key. The two-argument form
tests equality; the three-argument form takes an operator string in the middle —
one of `=`, `==`, `!=`, `<>`, `<`, `<=`, `>`, `>=`, `===`, `!==`. An unknown
operator falls back to equality. Keys are preserved, so `.all()` on a filtered
list-like collection returns a dict keyed by the original indices; chain
`.values()` for a list.

```python title="examples/collections.py"
items = [{"product": "Desk", "price": 200}, {"product": "Chair", "price": 100}, {"product": "Door", "price": 100}]
result = collect(items).where("price", 100).all()

# {1: {'product': 'Chair', 'price': 100}, 2: {'product': 'Door', 'price': 100}}

result = collect(items).where("price", ">", 100).values().pluck("product").all()

# ['Desk']

result = collect([{"o": {"p": 1}}, {"o": {"p": 2}}]).where("o.p", 2).values().all()

# [{'o': {'p': 2}}]
```

### where_between

Keeps items whose value at the key falls within the inclusive range given as a
two-element sequence. Items whose value is `None` are excluded.

```python title="examples/collections.py"
items = [{"product": "Desk", "price": 200}, {"product": "Chair", "price": 100}, {"product": "Bookcase", "price": 150}]
result = collect(items).where_between("price", [100, 150]).values().pluck("product").all()

# ['Chair', 'Bookcase']
```

### where_in

Keeps items whose value at the key is in the given iterable. The candidates are
collected into a `set`, so they must be hashable, and membership uses `==` —
`True` matches `1`. Use `where_in_strict` for identity.

```python title="examples/collections.py"
items = [{"product": "Desk", "price": 200}, {"product": "Chair", "price": 100}, {"product": "Bookcase", "price": 150}]
result = collect(items).where_in("price", [150, 200]).values().pluck("product").all()

# ['Desk', 'Bookcase']

result = collect([{"v": 1}, {"v": True}]).where_in("v", [1]).values().all()

# [{'v': 1}, {'v': True}]
```

### where_in_strict

`where_in` using identity (`is`) rather than `==`, so only the exact objects you
pass in match.

```python title="examples/collections.py"
first, second = [1], [1]
result = collect([{"v": first}, {"v": second}]).where_in_strict("v", [first]).count()

# 1
```

### where_instance_of

Keeps items that are instances of the given class. Accepts anything
`isinstance` does, including a tuple of classes. Note Python's rule that `bool`
is a subclass of `int`.

```python title="examples/collections.py"
result = collect([1, "a", 2, None, 3.5]).where_instance_of(int).values().all()

# [1, 2]

result = collect([1, "a", 2.5]).where_instance_of((int, float)).values().all()

# [1, 2.5]
```

### where_not_between

The complement of `where_between`: keeps items outside the inclusive range, and
also keeps items whose value at the key is `None`.

```python title="examples/collections.py"
items = [{"product": "Desk", "price": 200}, {"product": "Chair", "price": 100}, {"product": "Bookcase", "price": 150}]
result = collect(items).where_not_between("price", [100, 150]).values().pluck("product").all()

# ['Desk']
```

### where_not_in

Keeps items whose value at the key is **not** in the given iterable. Same
hashability and `==` semantics as `where_in`.

```python title="examples/collections.py"
items = [{"product": "Desk", "price": 200}, {"product": "Chair", "price": 100}, {"product": "Bookcase", "price": 150}]
result = collect(items).where_not_in("price", [150, 200]).values().pluck("product").all()

# ['Chair']
```

### where_not_in_strict

`where_not_in` using identity (`is`), so an equal-but-distinct object is kept
rather than excluded.

```python title="examples/collections.py"
first, second = [1], [1]
result = collect([{"v": first}, {"v": second}]).where_not_in_strict("v", [first]).values().all()

# [{'v': [1]}]
```

### where_not_null

Keeps items whose value at the key is not `None`. A missing key reads as `None`
via `data_get`, so absent keys are excluded too.

```python title="examples/collections.py"
items = [{"n": "Desk"}, {"n": None}, {"n": "Bookcase"}]
result = collect(items).where_not_null("n").values().all()

# [{'n': 'Desk'}, {'n': 'Bookcase'}]
```

### where_null

Keeps items whose value at the key is `None`, including items where the key is
absent. Keys are preserved, hence the dict below.

```python title="examples/collections.py"
items = [{"n": "Desk"}, {"n": None}, {"n": "Bookcase"}]
result = collect(items).where_null("n").all()

# {1: {'n': None}}
```

### where_strict

Compares with `is` instead of `==`. This is identity, not type-strict value
equality, so two equal integers or strings that are not the same
object will not match — it is reliable for sentinels, `None`, and enum members,
not for numbers built at runtime.

```python title="examples/collections.py"
marker = object()
result = collect([{"flag": marker}, {"flag": None}]).where_strict("flag", marker).count()

# 1

result = collect([{"n": int("1000")}]).where_strict("n", int("1000")).count()

# 0
```

### wrap

Class method that returns the value as a collection: collections pass through
unchanged, mappings become keyed collections, `None` becomes empty, lists,
tuples and sets are wrapped as-is, and anything else becomes a single-item
collection.

```python title="examples/helpers.py"
from almasix.support import Collection

result = Collection.wrap("Desk").all()

# ['Desk']

result = Collection.wrap(None).all()

# []
```

### zip

Pairs each item with the item at the same index in each of the given iterables,
producing a collection of lists. Extra items past the shortest input are dropped
rather than padded — use `pad` first if you need to keep them.

```python title="examples/collections.py"
result = collect([1, 2, 3]).zip([4, 5, 6]).all()

# [[1, 4], [2, 5], [3, 6]]

result = collect([1, 2]).zip([3, 4], [5, 6]).all()

# [[1, 3, 5], [2, 4, 6]]

result = collect([1, 2, 3]).zip([4, 5]).all()

# [[1, 4], [2, 5]]
```
