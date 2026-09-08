---
title: Pagination
description: Paginate query results with length-aware or simple paginators.
---

Almasix includes convenient pagination that integrates with the [query builder](/database/queries/) and [Articulate](/articulate/). There are two styles: length-aware pagination and simple pagination.

## Paginating query builder results

```python
# app/http/controllers/example_controller.py
page = await User.query().order_by("id").paginate(15, page=2)
page.items          # Collection of models
page.total
page.last_page
page.has_more_pages()
page.on_first_page()
page.to_dict()      # {data, current_page, per_page, total, last_page, from, to}
```

`paginate` runs a `count` query plus the page query so the paginator knows the total number of results.

## Simple pagination

When you do not need to display the total number of pages — for example, a “Next” link only — use `simple_paginate`:

```python
# app/http/controllers/example_controller.py
simple = await User.query().simple_paginate(15, page=1)
simple.has_more_pages()
simple.to_dict()    # {data, current_page, per_page, has_more}
```

Simple pagination fetches `per_page + 1` rows and only determines whether another page exists.

## Default page size

The default `per_page` is taken from `Model.per_page` (15 unless you override it on the model).

## Displaying results

Pass `page.to_dict()` (or the paginator itself from a JSON route) to your frontend. HTML view helpers for link rendering will arrive with Prism templates.
