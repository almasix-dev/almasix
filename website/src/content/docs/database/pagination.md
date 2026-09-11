---
title: Pagination
description: Paginate query results with length-aware, simple, or cursor paginators.
---

Almasix's paginators work with the [query builder](/database/queries/) and
[Articulate](/articulate/), and know the URL they were reached at, so they can
write the links to the pages either side of them.

There are three, and the difference between them is what each one knows:

| Paginator | Query cost | Knows |
| --- | --- | --- |
| `paginate` | a `count` plus the page | page numbers, the last page, the total |
| `simple_paginate` | the page, plus one row | whether there is another page |
| `cursor_paginate` | the page, plus one row | where this page ended |

## Basic usage

### Paginating query builder results

```python title="app/http/controllers/user_controller.py"
async def index():
    users = await DB.table("users").order_by("id").paginate(15)
    return view("users.index", {"users": users})
```

The page comes from the request's `page` query parameter by default. Pass one
to override it:

```python title="app/http/controllers/user_controller.py"
page = await DB.table("users").order_by("id").paginate(15, page=2)
```

If you already know the total — a count you cached, say — hand it over and the
count query is skipped:

```python title="app/http/controllers/user_controller.py"
page = await DB.table("users").order_by("id").paginate(15, total=cached_total)
```

### Paginating Articulate results

```python title="app/http/controllers/user_controller.py"
users = await User.query().where("votes", ">", 100).order_by("id").paginate(15)
```

`Model.per_page` decides the size when you do not pass one; it is 15 unless the
model says otherwise.

### Simple pagination

When the view only needs "Previous" and "Next", `simple_paginate` skips the
count query. It reads one row more than a page and reports whether it found it:

```python title="app/http/controllers/user_controller.py"
users = await User.query().order_by("id").simple_paginate(15)
users.has_more_pages()
```

### Cursor pagination

A cursor is where the last page ended: the ordered columns of its final row,
base64-encoded into the URL. The page after it is a `WHERE` comparison rather
than an `OFFSET`, which means rows inserted while a reader is paging do not
shift the window, and the database does not count past what it returns.

```python title="app/http/controllers/user_controller.py"
users = await User.query().order_by("id").cursor_paginate(15)
users.next_page_url()   # /users?cursor=eyJpZCI6MTUsIl9wb2ludHNUb05leHRJdGVtcyI6dHJ1ZX0
```

The ordering is what the cursor is made of, so the query needs one; several
`order_by` clauses page correctly, compared column by column:

```python title="app/http/controllers/post_controller.py"
posts = await Post.query().order_by("author").order_by("title", "desc").cursor_paginate(15)
```

The cursor is read from the request's `cursor` parameter, or handed over
directly:

```python title="app/http/controllers/post_controller.py"
page = await Post.query().order_by("id").cursor_paginate(15, previous_page.next_cursor())
```

The cost is that there are no page numbers and no jumping about: a cursor
paginator can only go forwards and back.

## Displaying results

### Links

```html title="resources/views/users/index.prism.html"
@foreach(users as user)
  <p>{{ user.name }}</p>
@endforeach

{!! users.links() !!}
```

`links()` renders `pagination.tailwind` (or `pagination.simple-tailwind` for a
simple paginator). Both ship with the framework; write
`resources/views/pagination/tailwind.prism.html` in your application to replace
one, or name another view:

```python title="app/http/controllers/user_controller.py"
users.links("pagination.my-own")
```

Bootstrap 5 views ship too. Say so once, in a service provider, and every
paginator uses them:

```python title="app/providers/app_service_provider.py"
from almasix.orm import Paginator

def boot(self) -> None:
    Paginator.use_bootstrap_five()   # or use_tailwind(), the default
```

A long run of pages is elided at both ends, three either side of the current
page. `on_each_side` widens or narrows that window:

```python title="app/http/controllers/user_controller.py"
users.on_each_side(5).links()
```

### The URL the links point at

The paginator reads the request's path, and each link carries the page number:

```python title="app/http/controllers/user_controller.py"
users.url(3)                # /users?page=3
users.next_page_url()
users.previous_page_url()
users.first_page_url()
users.last_page_url()
users.get_url_range(1, 5)   # {1: "/users?page=1", …}
```

`with_path` says where the pages live when the paginator is built somewhere the
request cannot be read:

```python title="app/http/controllers/user_controller.py"
users.with_path("/admin/users")
```

### Appending query string values

```python title="app/http/controllers/user_controller.py"
users.appends("sort", "votes")           # /users?sort=votes&page=2
users.appends({"sort": "votes", "team": 3})
users.with_query_string()                # carry the request's own parameters
users.fragment("results")                # /users?page=2#results
```

### Converting to JSON

A paginator serializes to a stable API shape:

```python title="app/http/controllers/api/user_controller.py"
return (await User.query().order_by("id").paginate(15)).to_dict()
```

```json title="response.json"
{
  "current_page": 1,
  "data": [],
  "first_page_url": "/users?page=1",
  "from": 1,
  "last_page": 4,
  "last_page_url": "/users?page=4",
  "links": [
    {"url": null, "label": "&laquo; Previous", "active": false},
    {"url": "/users?page=1", "label": "1", "active": true},
    {"url": "/users?page=2", "label": "Next &raquo;", "active": false}
  ],
  "next_page_url": "/users?page=2",
  "path": "/users",
  "per_page": 15,
  "prev_page_url": null,
  "to": 15,
  "total": 50
}
```

A cursor paginator has no page numbers to report, so its JSON carries the
cursors instead:

```json title="response.json"
{
  "data": [],
  "path": "/users",
  "per_page": 15,
  "next_cursor": "eyJpZCI6MTV9",
  "next_page_url": "/users?cursor=eyJpZCI6MTV9",
  "prev_cursor": null,
  "prev_page_url": null
}
```

## Paginator instance methods

| Method | Answers |
| --- | --- |
| `count()` / `len(page)` | How many items are on this page |
| `current_page` | Which page this is |
| `first_item()` / `last_item()` | The result numbers this page spans |
| `from_` / `to` | The same two, as the JSON names them |
| `has_more_pages()` | Whether there is another page |
| `has_pages()` | Whether there is more than one page in all |
| `is_empty()` / `is_not_empty()` | Whether this page found anything |
| `items` | The `Collection` behind the page |
| `last_page` | The last page number (length-aware only) |
| `on_each_side(n)` | How many page numbers flank the current one |
| `on_first_page()` / `on_last_page()` | Where in the run this page is |
| `per_page` | How many fit on a page |
| `through(callback)` | Transform each item, keeping the page around it |
| `total` | How many results there are in all (length-aware only) |
| `to_dict()` / `to_json()` | The JSON shape above |

A cursor paginator adds `cursor`, `next_cursor()` and `previous_cursor()`, each
a `Cursor` — `encode()` writes one into a URL and `Cursor.from_encoded()` reads
it back.
