---
title: Mutators & Casts
description: Transform Articulate attributes on read and write with accessors, mutators, and casts.
---

Accessors and mutators let you transform attribute values as you read or write them on a model. Casts do the same thing declaratively — telling Articulate that `votes` is an integer or `meta` is JSON, without writing a transform for every column.

## Accessors and mutators

### Attribute objects

Declare an accessor and its mutator together as an `Attribute`:

```python
# app/models/user.py
from avalon.orm import Attribute, Model


class User(Model):
    fillable = ("name",)

    name = Attribute(
        get=lambda value: value.title(),
        set=lambda value: value.strip(),
    )
```

`get` receives the stored value and returns what the model should hand back. `set` receives the assigned value and returns what should be stored:

```python
user = User(name="  ada lovelace ")
user.name                            # "Ada Lovelace"
user.get_raw_attribute("name")       # "ada lovelace"
```

Both callbacks may take **no arguments**, just the **value**, or the value plus the model's **raw attributes** — Articulate passes whichever your callback accepts:

```python
email = Attribute(get=lambda value, attributes: f"{value} <{attributes['name']}>")
```

### Declaring an accessor from a method

When the accessor needs more than a lambda, use `@attribute` on a method that returns an `Attribute`. This is the shape Laravel uses:

```python
from avalon.orm import Attribute, Model, attribute


class User(Model):
    @attribute
    def full_name(self) -> Attribute:
        return Attribute(
            get=lambda _value, attributes: f"{attributes['first']} {attributes['last']}",
        )
```

`full_name` needs no column of its own. Add it to `appends` to include it in `to_dict()`.

### Writing several columns from one attribute

A `set` callback that returns a mapping writes each key, which is how a value object spans columns:

```python
class Place(Model):
    position = Attribute(
        get=lambda _value, attributes: (attributes["lat"], attributes["lng"]),
        set=lambda value: {"lat": value[0], "lng": value[1]},
    )
```

### Caching an accessor

Accessors run on every read. When one is expensive, pass `cache=True` and it computes once per instance, until that attribute is written again:

```python
summary = Attribute(get=lambda value: expensive(value), cache=True)
```

### Magic-method accessors

The `get_<name>_attribute` / `set_<name>_attribute` form also works, and is often the shortest route when you only need one direction:

```python
def get_display_attribute(self, value=None) -> str:
    return f"{self.name} <{self.email}>"


def set_name_attribute(self, value: str) -> str:
    return value.strip()
```

A mutator returning `None` suppresses the write entirely.

## Attribute casting

Declare casts as a dict:

```python
class User(Model):
    casts = {"votes": "int", "active": "bool", "meta": "json"}
```

Or as a `casts()` method, when a cast needs to be constructed:

```python
class User(Model):
    @classmethod
    def casts(cls) -> dict:
        return {"labels": EnumCollection.of(Status)}
```

### Available casts

| Cast | Reads as |
| --- | --- |
| `int` / `integer` | `int` |
| `float` / `double` / `real` | `float` |
| `str` / `string` | `str` |
| `bool` / `boolean` | `bool` — `"1"`, `"true"`, `"yes"`, `"on"` are true |
| `decimal:<places>` | `Decimal`, quantized to `places` |
| `json` / `array` / `dict` / `object` / `collection` | `dict` or `list` |
| `date` / `immutable_date` | `date` |
| `datetime` / `immutable_datetime` | `datetime` |
| `time` | `time` |
| `timestamp` | `int` epoch seconds |
| `encrypted` | decrypted `str` |
| `encrypted:array` (or `:object` / `:collection`) | decrypted, JSON-decoded value |
| `hashed` | the stored digest |
| An `Enum` subclass | that enum member |
| `EnumCollection.of(Enum)` | a list of enum members |

:::note[Immutable dates]
Python's `date` and `datetime` are already immutable, so `immutable_date` and `immutable_datetime` are accepted as aliases rather than distinct types. Nothing can mutate a date in place here, which is the guarantee the Laravel casts exist to provide.
:::

### Encrypted casting

`encrypted` encrypts on write and decrypts on read, using the same key as [Encryption](/encryption/):

```python
class Account(Model):
    casts = {"token": "encrypted", "recovery": "encrypted:array"}
```

The stored column holds ciphertext, so it must be a text column long enough to hold it. Encrypted values cannot be queried with a `where` clause.

### Hashed casting

`hashed` hashes the value on write using [Hashing](/hashing/), and leaves an already-hashed value alone — so re-saving a model does not double-hash:

```python
class User(Model):
    casts = {"password": "hashed"}


user.password = "hunter2"                  # stored as a bcrypt digest
```

### Date casting and serialization

A date cast may carry a `strftime` format, which sets how the attribute serializes. Storage stays ISO-8601:

```python
class Event(Model):
    casts = {"day": "date:%d/%m/%Y", "at": "datetime:%Y-%m-%d %H:%M"}
```

To change the default for every date on a model, set `date_format`, or override `serialize_date`:

```python
class Event(Model):
    date_format = "%Y-%m-%d"

    def serialize_date(self, value) -> str:
        return value.strftime("%d %b %Y")
```

:::note
Avalon uses Python `strftime` codes (`%Y-%m-%d`), not PHP's date format characters.
:::

### Query-time casting

`with_casts` applies casts to one query, which is useful for computed columns and raw selects:

```python
readings = await (
    Reading.query()
    .select_raw("sum(amount) as total")
    .with_casts({"total": "decimal:2"})
    .get()
)
```

`merge_casts` does the same for a single model instance.

## Custom casts

Subclass `CastsAttributes` when a cast needs real logic. `get` transforms a stored value on read, `set` on write:

```python
from avalon.orm import CastsAttributes


class AsJsonLines(CastsAttributes):
    def get(self, model, key, value, attributes):
        return (value or "").splitlines()

    def set(self, model, key, value, attributes):
        return "\n".join(value)


class Report(Model):
    casts = {"lines": AsJsonLines}
```

Declare the class or an instance — `casts = {"lines": AsJsonLines()}` also works, which is how you pass constructor arguments.

### Value-object casts

A `set` returning a mapping writes several columns, and `get` composes them back:

```python
class AsCoordinates(CastsAttributes):
    def get(self, model, key, value, attributes):
        return Point(attributes["lat"], attributes["lng"])

    def set(self, model, key, value, attributes):
        return {"lat": value.lat, "lng": value.lng}
```

The attribute needs no column of its own.

### Inbound-only casts

When a transform cannot be reversed, subclass `CastsInboundAttributes`. Reads pass the stored value through untouched:

```python
from avalon.orm import CastsInboundAttributes


class AsSlug(CastsInboundAttributes):
    def set(self, model, key, value, attributes):
        return str(value).lower().replace(" ", "-")
```

### Castables

A class may name its own cast with a `cast_using` classmethod, so the value type and its cast travel together:

```python
class Money:
    @classmethod
    def cast_using(cls):
        return AsMoney
```

`casts = {"price": Money}` then resolves to `AsMoney`.

## Related

- [Articulate: Getting Started](/articulate/) — models, retrieval, and mass assignment
- [Serialization](/articulate/serialization/) — how cast values reach JSON
- [Encryption](/encryption/) — the key behind `encrypted` casts
- [Hashing](/hashing/) — the driver behind the `hashed` cast
