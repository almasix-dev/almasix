---
title: How to read these docs
description: Nouns, journey order, and where to go next if you are new to Almasix.
---

Almasix docs assume you know **Python** and the basics of the web (HTTP, HTML,
JSON). They do **not** assume you know another web framework.

## Words you will see

| Term | Meaning |
| --- | --- |
| **Almasix** | The framework (`pip install almasix`) |
| **`almasix new`** | Creates a new application directory |
| **Smith** | The in-app CLI — prefer `python smith …` from the app root |
| **Articulate** | The ORM — models, queries, migrations |
| **Prism** | The template engine (`.prism.html` files) |
| **ASGI** | The async server interface Almasix apps run on (Uvicorn by default) |

## Code examples

Every example shows a **file path** above the code (the tab on the code block).
That path is where the snippet belongs in a typical app from `almasix new` —
for example `routes/web.py` or `app/http/controllers/post_controller.py`.
Shell commands use the path `terminal`.

Copy the idea into the matching file in your project; adjust names to fit.

## Suggested path

1. [Installation](/installation/) — create an app and open it in the browser
2. [Directory Structure](/structure/) — where files live
3. [Routing](/routing/) → [Controllers](/controllers/) → [Requests](/requests/) → [Responses](/responses/)
4. [Views](/views/) and the [Prism](/prism/) group when you render HTML
5. [Validation](/validation/), [Session](/session/), then [Authentication](/authentication/)
6. [Database](/database/) and [Articulate](/articulate/) when you persist data
7. [Deployment](/deployment/) before production

Sidebar groups fold; open **The Basics** and walk top to bottom.

## When something fails

- [Error Handling](/errors/) and [Logging](/logging/)
- [Testing](/testing/) for HTTP and console tests
- GitHub Issues on [almasix-dev/almasix](https://github.com/almasix-dev/almasix)
