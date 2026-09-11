---
title: Soft Deletes & Events
description: Soft delete models, define query scopes, and listen for model lifecycle events.
---

## Query scopes

### Local scopes

Local scopes let you name a common set of query constraints and reuse them. Name the method `scope_<name>`. The **query is the first argument**:

```python title="app/models/post.py"
class Post(Model):
    def scope_published(query):
        return query.where("published", True)

await Post.query().published().get()
```

Also accepted: `scope_published(cls, query)` as a classmethod, or `(self, query)` style. Returning a builder is optional — mutating `query` in place is fine.

### Global scopes

A **global scope** applies to every query on the model unless you opt out:

```python title="app/models/user.py"
User.add_global_scope("active", lambda query: query.where("active", True))
await User.without_global_scope("active").get()
await User.without_global_scopes().get()
```

## Soft deleting

In addition to actually removing records from your database, Articulate can **soft delete** models. Soft deletes do not remove the row; they set a `deleted_at` timestamp so normal queries hide the row until you restore or permanently delete it.

```python title="app/models/post.py"
from almasix.orm import Model, SoftDeletes

class Post(SoftDeletes, Model):   # mixin before Model
    fillable = ("title",)

await post.delete()               # sets deleted_at
await Post.query().get()          # excludes trashed
await Post.with_trashed().get()
await Post.only_trashed().get()
await Post.without_trashed().get()  # the default, stated explicitly
post.trashed()
await post.restore()
await post.force_delete()         # hard DELETE
```

Add `table.soft_deletes()` on your migration blueprint.

Trashed rows still occupy the table. To clear them out on a schedule, make the model [prunable](/articulate/#pruning-models).

## Events

Articulate models dispatch several events, allowing you to hook into the following moments: `retrieved`, `creating`, `created`, `updating`, `updated`, `saving`, `saved`, `deleting`, `deleted`, `restoring`, `restored`, and `replicating`.

```python title="app/models/post.py"
Post.listen("creating", lambda model: ...)

class PostObserver:
    def created(self, model):
        ...

Post.observe(PostObserver)
```

A listener that returns `False` aborts that lifecycle step (`save` / `delete` / `restore`). Async listeners are awaited on the async path. `retrieved` and `replicating` fire in a sync context — do not pass async callbacks there.

### Muting events

```python title="app/http/controllers/example_controller.py"
await post.save_quietly()
await post.delete_quietly()
await post.force_delete_quietly()
await post.restore_quietly()

with Model.without_events():      # a whole block
    await Post.create(title="Silent")
```

The `*_quietly` methods mute events on that instance only, so concurrent work keeps firing its own. `without_events()` is process-wide for the duration of the block.
