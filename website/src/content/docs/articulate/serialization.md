---
title: Serialization
description: Convert Articulate models and collections to dicts and JSON, and control what appears.
---

When building APIs you often need to convert models and their relationships to dicts or JSON. Articulate includes methods for those conversions, plus controls over which attributes appear in the serialized output.

## Serializing models and collections

### Serializing to a dict

`to_dict()` converts a model and its **loaded** relations. It recurses, so relations of relations are converted too:

```python
user = await User.query().with_("roles").first()

user.to_dict()
```

To convert only the attributes, skipping relations, use `attributes_to_dict()`. The mirror image, `relations_to_dict()`, returns just the loaded relations:

```python
user.attributes_to_dict()
user.relations_to_dict()
```

Collections convert the same way:

```python
users = await User.all()

users.to_dict()      # a list of dicts
```

### Serializing to JSON

`to_json()` returns a JSON string. Extra keyword arguments are passed through to `json.dumps`, so formatting options work as usual:

```python
user.to_json()
user.to_json(indent=2)
```

:::note[Relation keys]
Loaded relations appear as keys on the serialized output under the relation's own name — `articles`, not `Articles`. Articulate relations are already snake_case, so no case conversion happens on the way out.
:::

## Hiding attributes

To keep an attribute such as a password hash out of the serialized output, list it in `hidden`:

```python
class User(Model):
    hidden = ("password",)
```

To hide a relation, name the relation in `hidden` as well.

Alternatively, `visible` is an allowlist. When it is set, only the attributes it names are serialized:

```python
class User(Model):
    visible = ("first_name", "last_name")
```

Both apply to attributes **and** relations.

### Changing visibility for one model

Each of these affects only the model you call it on — never the class, and never other instances:

```python
user.make_visible("password").to_dict()      # reveal a normally hidden attribute
user.merge_visible(["name", "email"]).to_dict()

user.make_hidden("email").to_dict()          # hide more attributes
user.merge_hidden(["name", "email"]).to_dict()

user.set_visible(["id", "name"]).to_dict()   # replace the allowlist outright
user.set_hidden(["email", "password"]).to_dict()
```

They all return the model, so they chain. `get_hidden()` and `get_visible()` report what is currently in effect.

On a collection, the same four helpers apply to every model at once:

```python
users.make_hidden("email")
users.set_visible(["id", "name"])
```

## Appending values

Sometimes you want to serialize a value that has no column. Define the accessor first:

```python
from almasix.orm import Attribute, Model


class User(Model):
    is_admin = Attribute(get=lambda _value, attributes: attributes["role"] == "admin")
```

Then add its name to `appends` so it is always included:

```python
class User(Model):
    appends = ("is_admin",)
```

Appended attributes respect `visible` and `hidden`, exactly as columns do.

### Appending at runtime

```python
user.append("is_admin").to_dict()
user.merge_appends(["is_admin", "status"]).to_dict()
user.set_appends(["is_admin"]).to_dict()     # replace the list
user.without_appends().to_dict()             # drop every appended key
```

`get_appends()` reports the appended keys currently in effect, and `users.append("is_admin")` applies to a whole collection.

## Date serialization

Dates serialize to ISO-8601 by default. To change that for every date on a model, set `date_format`:

```python
class User(Model):
    date_format = "%Y-%m-%d"
```

For full control, override `serialize_date`. It affects serialization only, never how values are stored:

```python
class User(Model):
    def serialize_date(self, value) -> str:
        return value.strftime("%d %b %Y")
```

To set the format for a single attribute, put it on the cast — see [Mutators & Casts](/articulate/casts/#date-casting-and-serialization):

```python
class User(Model):
    casts = {"birthday": "date:%Y-%m-%d", "joined_at": "datetime:%Y-%m-%d %H:00"}
```

:::note
Formats use Python `strftime` codes, not PHP's date characters.
:::

## When to reach for a resource instead

`hidden` / `visible` / `appends` shape a model everywhere it is serialized —
in an API response, a queue payload, a log line. When only the API should look
different, or the shape depends on who is asking, that belongs in an
[API Resource](/api-resources/) rather than on the model.

## Related

- [API Resources](/api-resources/) — the transformation layer for API output
- [Mutators & Casts](/articulate/casts/) — accessors and the cast that shapes a value
- [Collections](/articulate/collections/) — the collection methods behind `to_dict()`
- [Articulate: Getting Started](/articulate/) — models and retrieval
