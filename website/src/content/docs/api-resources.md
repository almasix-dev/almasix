---
title: API Resources
description: Transform models into JSON with JsonResource, ResourceCollection, conditional attributes, and pagination.
---

## Introduction

When you build an API, you rarely want to hand the client a model exactly as it
is stored. An API resource is the transformation layer that sits between your
Articulate models and the JSON your users see.

```python title="app/http/controllers/example_controller.py"
from almasix.http.resources import JsonResource


class UserResource(JsonResource):
    def to_dict(self, request=None):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at,
        }
```

Return one from a controller and it becomes the response:

```python title="examples/api-resources.py"
async def show(user_id: int):
    return UserResource(await User.query().find_or_fail(user_id))
```

```json title="examples/api-resources.json"
{
  "data": {"id": 1, "name": "Ada", "created_at": "2026-09-08T12:30:00"}
}
```

Anything with a `to_response()` method can be returned from a controller —
the framework turns it into an HTTP response for you.

## File map

| Piece | Path |
| --- | --- |
| Resource | `src/almasix/http/resources/resource.py` — `JsonResource` |
| Collections | `src/almasix/http/resources/collection.py` — `ResourceCollection` |
| Response + wrapping | `src/almasix/http/resources/response.py` |
| Missing / merge markers | `src/almasix/http/resources/missing.py` |
| Generator | `smith make:resource`, stub `resource.stub` |

## Generating resources

```bash title="terminal"
smith make:resource UserResource
smith make:resource UserCollection            # a collection, by name
smith make:resource UserResource --collection # or by flag
smith make:resource Api/UserResource          # nested namespace
```

Files land in `app/http/resources/`, snake_cased: `app/http/resources/user_resource.py`.

## Writing resources

A resource wraps one object, available as `self.resource`. Attributes fall
through, so `self.name` reads the model's `name`:

```python title="examples/api-resources.py"
class UserResource(JsonResource):
    def to_dict(self, request=None):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
        }
```

If you never override `to_dict`, the resource serializes whatever it was given
— a model through its own `to_dict()`, a mapping as-is.

### Relationships

Nest resources inside each other. Only the **outermost** resource is wrapped:

```python title="examples/api-resources.py"
class PostResource(JsonResource):
    def to_dict(self, request=None):
        return {
            "title": self.title,
            "author": UserResource(self.get_relations()["author"]),
            "comments": CommentResource.collection(self.get_relations()["comments"]),
        }
```

In practice you want `when_loaded()` — see conditional relationships below.

## Resource collections

`SomeResource.collection(items)` wraps many:

```python title="examples/api-resources.py"
return UserResource.collection(await User.query().get())
```

```json title="examples/api-resources.json"
{"data": [{"id": 1, "name": "Ada"}, {"id": 2, "name": "Bob"}]}
```

For collection-level metadata, declare a collection class:

```python title="app/http/controllers/example_controller.py"
from almasix.http.resources import ResourceCollection


class UserCollection(ResourceCollection):
    collects = UserResource

    def with_(self, request=None):
        return {"meta": {"team": "engineering"}}
```

Without `collects`, a `UserCollection` looks for a `UserResource` in the same
module and falls back to the plain `JsonResource`.

### Preserving collection keys

Collections renumber by default. To keep the keys of a keyed collection:

```python title="examples/collections.py"
class UserCollection(ResourceCollection):
    collects = UserResource
    preserve_keys = True
```

## Data wrapping

The outermost resource is wrapped in `data`. Turn that off, or rename it,
once at boot — usually in a service provider:

```python title="examples/api-resources.py"
JsonResource.without_wrapping()
JsonResource.wrap_with("record")
```

One resource can differ from the rest by declaring its own key:

```python title="examples/api-resources.py"
class UserResource(JsonResource):
    wrap = "user"
```

If your `to_dict()` already returns a `data` key, it is not wrapped twice.

## Pagination

Hand a paginator to a collection and the response gains `meta`:

```python title="examples/api-resources.py"
return UserResource.collection(await User.query().paginate(per_page=15))
```

```json title="examples/api-resources.json"
{
  "data": [...],
  "meta": {
    "current_page": 1, "per_page": 15, "from": 1, "to": 15,
    "last_page": 4, "total": 60, "path": "https://example.test/api/users"
  },
  "links": {
    "first": "https://example.test/api/users?page=1",
    "last": "https://example.test/api/users?page=4",
    "prev": null,
    "next": "https://example.test/api/users?page=2"
  }
}
```

`path` and `links` need a URL, so they appear only when there is a request to
read one from — inside a controller, they are there; in a unit test with a
bare paginator, they are not.

A paginated payload is always wrapped, even when wrapping is disabled, because
`meta` needs somewhere to sit beside the rows.

`simple_paginate()` reports `has_more` instead of `total` and `last_page`.

### Customizing pagination information

```python title="examples/collections.py"
class UserCollection(ResourceCollection):
    collects = UserResource

    def pagination_information(self, request, paginated, default):
        default["meta"]["team"] = "engineering"
        return default
```

## Conditional attributes

Include a key only sometimes. Anything that resolves to *missing* disappears
from the output entirely — at any depth.

```python title="examples/api-resources.py"
class UserResource(JsonResource):
    def to_dict(self, request=None):
        return {
            "id": self.id,
            "secret": self.when(request.user.is_admin, "value"),
            "lazy": self.when(condition, lambda: expensive()),
            "with_default": self.when(condition, "yes", "no"),
        }
```

| Method | Includes the value when |
| --- | --- |
| `when(condition, value, default)` | the condition is truthy |
| `unless(condition, value, default)` | the condition is falsy |
| `when_has(attribute, value, default)` | the underlying object has that attribute |
| `when_not_null(value, default)` | the value is not `None` |

Conditions, values, and defaults may each be callables, evaluated only when
needed.

### Merging conditional attributes

Sometimes a whole block of keys should appear together:

```python title="examples/api-resources.py"
"merged": self.merge_when(request.user.is_admin, {
    "first_secret": "value",
    "second_secret": "value",
}),
"always": self.merge({"seen": True}),
"guest": self.merge_unless(request.user.is_admin, {"role": "guest"}),
```

The key you file a merge under (`"merged"` above) is discarded — its contents
are spliced into the parent. Merging a list renumbers into the parent instead.

### Conditional relationships

```python title="examples/api-resources.py"
class PostResource(JsonResource):
    def to_dict(self, request=None):
        return {
            "title": self.title,
            "author": self.when_loaded("author"),
            "author_name": self.when_loaded("author", lambda author: author.name),
            "comments_count": self.when_counted("comments"),
            "votes": self.when_aggregated("comments", "votes", "sum"),
            "full_name": self.when_appended("full_name"),
        }
```

| Method | Includes the value when |
| --- | --- |
| `when_loaded(relation, value, default)` | the relation was eager loaded |
| `when_counted(relation, value, default)` | `with_count()` loaded that count |
| `when_aggregated(relation, column, aggregate, …)` | `with_sum()` / `with_avg()` / … loaded it |
| `when_appended(attribute, value, default)` | the model appends that accessor |
| `when_pivot_loaded(table, value, default)` | the intermediate row is present |
| `when_pivot_loaded_as(accessor, table, value, default)` | same, under a renamed accessor |

`when_loaded` never triggers a query — an unloaded relation simply vanishes
from the payload, which is what makes N+1 impossible here.

```python title="examples/api-resources.py"
"added_by": self.when_pivot_loaded("post_tag", lambda pivot: pivot.added_by),
```

## Adding metadata

`with_()` adds top-level data to **every** response of a resource;
`additional()` adds it to **one**:

```python title="examples/collections.py"
class UserCollection(ResourceCollection):
    def with_(self, request=None):
        return {"meta": {"key": "value"}}
```

```python title="examples/api-resources.py"
return UserResource(user).additional({"meta": {"token": token}})
```

## Resource responses

Status and headers are fluent, and `with_response()` is the hook for anything
else:

```python title="examples/api-resources.py"
return UserResource(user).status(201).header("X-Rate-Limit", "60")
```

```python title="examples/api-resources.py"
class UserResource(JsonResource):
    def with_response(self, request, response):
        response.headers["X-Value"] = "True"
```

`response(request=None)` builds the response yourself; the request defaults to
the one being handled.

Dates, decimals, UUIDs, and sets serialize without a custom encoder.

## Python-shaped details

- **`to_dict()`** takes an optional `request` because Almasix reads the current
  request from context rather than injecting it everywhere.
- **`with_()` and `merge()`** carry trailing or shortened names because `with`
  is a Python keyword.
- **`links` and `meta.path` appear only when a request URL is available.**
  The resource layer reads the current request instead of inventing a URL when
  the paginator has no path of its own.
- **`status()` / `header()` / `headers()` live on the resource**, because
  Starlette responses have no fluent header setter to chain from.
- **`collects` is a class attribute holding the class itself**, not a string
  class name, because Python has no autoloading to resolve one from.

## Related

- [Articulate: Serialization](/articulate/serialization/) — `hidden`,
  `visible`, `appends`, and how a model turns itself into a dict.
- [Responses](/responses/) — everything else a controller can return.
