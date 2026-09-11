---
title: Search
description: Full-text search for Articulate models — the Searchable mixin, search builders, engines from your own table to Meilisearch, and indexes that keep themselves in step.
---

## Introduction

Search adds full-text search to Articulate models. Mix `Searchable` into a
model and it keeps a search index in step with the database on its own: a save
indexes the row, a delete removes it, and `Model.search()` reads it back.

```python title="app/models/example.py"
from almasix.orm import Model
from almasix.scout import Searchable


class Post(Searchable, Model):
    searchable_columns = ("title", "body")

    def to_searchable_array(self) -> dict:
        return {"id": self.id, "title": self.title, "body": self.body}
```

```python title="examples/search.py"
posts = await Post.search("almasix").where("published", True).get()
```

Which engine answers is `config/scout.py`'s business. The default, `database`,
searches the table you already have — nothing to install and nothing to keep
in sync. When an application outgrows that, `meilisearch` points the same code
at a real index.

## File map

| Piece | Path |
| --- | --- |
| Mixin | `src/almasix/scout/searchable.py` — `Searchable` |
| Search builder | `src/almasix/scout/builder.py` — `SearchBuilder` |
| Façade | `src/almasix/scout/facade.py` — `Scout` |
| Manager | `src/almasix/scout/manager.py` — `EngineManager` |
| Engines | `src/almasix/scout/engines/` — database, collection, meilisearch, null |
| Queued indexing | `src/almasix/scout/jobs.py` — `MakeSearchable`, `RemoveFromSearch` |
| After-commit indexing | `src/almasix/scout/pending.py` — `flush_search()` |
| Query / collection methods | `src/almasix/scout/macros.py` |
| Testing | `src/almasix/scout/testing.py` — `FakeEngine` |
| Provider | `src/almasix/scout/provider.py` |
| Config | `config/scout.py` |
| Commands | `src/almasix/console/commands/scout.py` |

## Configuration

```python title="config/scout.py"
config = {
    "driver": env("SCOUT_DRIVER", "database"),
    "prefix": env("SCOUT_PREFIX", ""),
    "queue": bool(env("SCOUT_QUEUE", False)),
    "after_commit": False,
    "chunk": {"searchable": 500, "unsearchable": 500},
    "soft_delete": False,
    "meilisearch": {
        "host": env("MEILISEARCH_HOST", "http://localhost:7700"),
        "key": env("MEILISEARCH_KEY"),
        "index-settings": {},
    },
}
```

| Engine | What it does |
| --- | --- |
| `database` | `LIKE`, prefix, and full-text clauses against the model's own table |
| `collection` | Reads the rows and filters them in Python — prototypes and tests |
| `meilisearch` | A real index, over Meilisearch's HTTP API |
| `null` | Indexes nothing and finds nothing — the off switch |

`Scout.extend("mine", resolver)` registers an engine of your own; the resolver
is called with the application, the engine's configuration, and its name, and
returns an `Engine`.

### Queueing

Set `queue` to `True` and every index write becomes a job, which is what you
want with an engine that talks over the network:

```python title="examples/search.py"
"queue": {"connection": "redis", "queue": "scout"},
```

A job carries the model class and the keys, not the models: queue payloads are
plain JSON here, so any driver can hold them, and the job re-reads the rows
when it runs. If nothing is configured to run jobs, the write still happens —
losing the index write would be a poor trade for a rule nobody set.

Set `after_commit` and index writes wait for the surrounding transaction, so a
rolled-back row never reaches the index.

## Configuring searchable data

The whole `to_dict()` form of the model goes into the index unless the model
says otherwise:

```python title="app/models/example.py"
class Post(Searchable, Model):
    def to_searchable_array(self) -> dict:
        return {"id": self.id, "title": self.title, "author": self.author.name}
```

| Override | Default | What it decides |
| --- | --- | --- |
| `to_searchable_array()` | `to_dict()` | What is indexed |
| `searchable_as()` | the table, behind `scout.prefix` | Which index |
| `get_scout_key()` | the primary key | The record's id |
| `get_scout_key_name()` | `primary_key` | The id's attribute name |
| `searchable_using()` | the configured engine | Which engine |
| `should_be_searchable()` | `True` | Whether the row belongs in the index |
| `search_index_should_be_updated()` | `True` | Whether this write is worth re-indexing |
| `make_all_searchable_using(query)` | the query | Eager loads for a full import |
| `make_searchable_using(models)` | the models | A last look before indexing |

`searchable_as()`, `get_scout_key_name()`, and `searchable_using()` are
classmethods: `scout:import` and friends ask a class, and there is nothing
per-row about any of them.

### Only some rows

```python title="app/models/example.py"
class Post(Searchable, Model):
    def should_be_searchable(self) -> bool:
        return bool(self.published)
```

A row that says no is removed from the index rather than left stale. The check
applies to saves, deletes, and imports; indexing a model or a collection
directly is explicit and overrides it.

## Searching

```python title="examples/search.py"
posts = await Post.search("almasix").get()
```

| Method | What it does |
| --- | --- |
| `where(field, value)` | An equality filter the engine applies |
| `where_in` / `where_not_in` | Membership filters |
| `order_by(column, direction)`, `latest()`, `oldest()` | Ordering |
| `take(n)` | At most this many results |
| `within(index)` | Search a named index instead of the model's |
| `options({...})` | Engine-specific search parameters |
| `query_using(callback)` | Shape the database query behind the results |
| `when` / `unless` / `tap` | Build the search conditionally |
| `get()` / `first()` / `keys()` / `count()` / `raw()` | Run it |
| `cursor()` | Stream the results one model at a time |
| `paginate()` / `simple_paginate()` | A page of results |
| `paginate_raw()` / `simple_paginate_raw()` | A page, unmapped |
| `with_trashed()` / `only_trashed()` | Soft deleted records |

A search engine ranks and a database does not, so the rows come back in the
engine's order, not the database's.

`query_using()` is named that way because a Python attribute and a method
cannot share a name and `builder.query` is the phrase being searched for:

```python title="examples/search.py"
posts = await Post.search("almasix").query_using(
    lambda query: query.with_("author")
).get()
```

With the `database` engine those constraints are part of the search query, so
they filter as well as shape. With every other engine the models are already
chosen by the time the callback runs — filter with `where()` instead.

### Customizing the engine's own search

The second argument to `search()` is handed the engine, the phrase, and the
payload about to be sent, and whatever it returns is used as the results:

```python title="examples/search.py"
def nearby(engine, query, payload):
    payload["filter"] = "_geoRadius(lat, lng, 2000)"
    return engine._request("POST", "/indexes/posts/search", payload)

posts = await Post.search("cafe", nearby).get()
```

## Keeping the index in step

Saving, deleting, and restoring a model do the right thing on their own. The
rest is for everything that does not go through a single model:

```python title="examples/search.py"
await post.searchable()                     # this one row
await post.unsearchable()

await Post.query().where("published", "=", True).searchable()
await (await Post.all()).unsearchable()

await Post.make_all_searchable()            # every row that belongs there
await Post.remove_all_from_search()         # empty the index
```

`searchable()` is an upsert: a record already in the index is updated.

### Pausing

```python title="examples/search.py"
with Post.without_syncing_to_search():
    await post.save()
```

Almasix takes a `with` block, which is what the rest of the framework does for
`unguarded()` and `without_timestamps()`. `Post.disable_search_syncing()` and
`Post.enable_search_syncing()` are there for the cases where a block does not
fit.

## Soft deleting

Set `soft_delete` in `config/scout.py` and a trashed row stays in the index
behind a hidden `__soft_deleted` flag instead of being removed:

```python title="examples/search.py"
await Post.search("almasix").with_trashed().get()
await Post.search("almasix").only_trashed().get()
```

Without the setting a trashed row leaves the index, which is what most
applications want. A force delete always removes it.

## Commands

| Command | What it does |
| --- | --- |
| `scout:import [model]` | Index every row of a model — every searchable model when none is named |
| `scout:queue-import [model]` | The same import, one queued job per chunk |
| `scout:flush [model]` | Empty a model's index |
| `scout:index name` | Create an index |
| `scout:delete-index name` | Delete an index |
| `scout:delete-all-indexes` | Delete every index the engine knows about |
| `scout:sync-index-settings` | Push `index-settings` from the configuration |
| `scout:status` | Which engine, which settings, which models |

`scout:status` exists because "which engine is this application actually
using" is the first question every search bug asks.

## Testing

```python title="examples/search.py"
from almasix.scout import Scout

fake = Scout.fake([post])            # what searches will find

await Post.query().searchable()
fake.assert_synced(Post, [post.id])
fake.assert_searched("almasix")
fake.assert_nothing_synced()         # raises: something was indexed
```

`Scout.fake()` swaps the engine for one that records instead of indexing, so a
controller can be exercised with no search service anywhere near the test.
When indexing is deferred to a commit, `await flush_search()` waits for the
writes the commit set going.

## Documents

Document models (see [Documents](/articulate/documents/)) are searchable under
the same mixin with the `collection`, `meilisearch`, and `null` engines. The
`database` engine is SQL — it builds `LIKE` clauses against a table — so a
document store answers with `collection` or a real index instead.

## Design notes

- **`query_using()`, not `query()`** — `builder.query` is the phrase; one name
  cannot be both.
- **Meilisearch over the HTTP client, no SDK** — the requests are the ones in
  Meilisearch's API reference, and `Http.fake()` fakes search too. Algolia and
  Typesense are engines an application can add with `Scout.extend()`; they are
  not shipped, because a driver nobody has exhausted is a claim, not a feature.
- **Queue payloads carry keys, not models** — a JSON payload works on every
  queue driver, and the row is re-read when the job runs.
- **`without_syncing_to_search()` is a context manager**, matching
  `unguarded()` and `without_timestamps()`.
- **`searchable_columns`** declares what the `database` engine searches —
  naming the columns is reliable even when `to_searchable_array` reads live
  attributes.
- **Prefix and full-text strategies are class attributes**
  (`search_using_prefix`, `search_using_full_text`). Full text is spoken on
  PostgreSQL and MySQL; other dialects fall back to `LIKE`, which is slower
  and never wrong.
- **`scout:status`** is an addition, and there is no `scout:queue-table`:
  Almasix's queue tables come from `queue:table`.

## Try it in your app

Mix `Searchable` into a model, set `searchable_columns`, then from your app
root:

```bash title="terminal"
python smith scout:import "app.models.Post"
```

```python title="examples/search.py"
posts = await Post.search("engines").get()
```

Or expose a small search endpoint and `curl` it with `?q=…`. The default
`database` engine needs no extra services.
