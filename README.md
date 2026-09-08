<p align="center">
  <img src="https://raw.githubusercontent.com/coolsam726/avalon/main/website/src/assets/avalon-banner.svg" alt="Avalon" width="300">
</p>

<p align="center"><strong>Laravel's application shape, in async Python.</strong></p>

<p align="center">
  A full-stack web framework on FastAPI and Starlette — routing, validation, an ORM, a view engine,
  auth, queues, mail, cache, events, a scheduler, and a first-class CLI — arranged the way Laravel
  arranges them, and asynchronous all the way down.
</p>

<p align="center">
  <a href="pyproject.toml"><img alt="version" src="https://img.shields.io/badge/dynamic/toml?url=https%3A%2F%2Fraw.githubusercontent.com%2Fcoolsam726%2Favalon%2Fmain%2Fpyproject.toml&query=%24.project.version&style=flat-square&label=version&prefix=v&color=4c1d95"></a>
  <a href="https://github.com/coolsam726/avalon/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/coolsam726/avalon/ci.yml?branch=main&style=flat-square&label=CI&logo=githubactions&logoColor=white"></a>
  <a href="docs/SMOKE.md"><img alt="coverage" src="https://img.shields.io/badge/coverage-99%25-31c48d?style=flat-square&logo=codecov&logoColor=white"></a>
  <a href="tests"><img alt="tests" src="https://img.shields.io/badge/tests-1%2C886-31c48d?style=flat-square&logo=pytest&logoColor=white"></a>
  <a href="pyproject.toml"><img alt="python" src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-3776ab?style=flat-square&logo=python&logoColor=white"></a>
  <a href="website/src/content/docs"><img alt="docs" src="https://img.shields.io/badge/docs-53%20pages-bc52ee?style=flat-square&logo=astro&logoColor=white"></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/github/license/coolsam726/avalon?style=flat-square&color=0f766e"></a>
</p>

<!--
  Avalon is not published to PyPI yet — the `avalon` name there belongs to an unrelated placeholder
  project. Once a release name is settled, add the release/download badges here:
    https://img.shields.io/pypi/v/<name>?style=flat-square
    https://img.shields.io/pypi/dm/<name>?style=flat-square
-->

## Why Avalon

Python has excellent HTTP libraries and very few opinions about what an application looks like.
Avalon supplies the opinions. It takes the conventions that make a Laravel codebase legible on
first read — the directory layout, service providers, facades, fluent builders, `Route` groups,
Eloquent-style models, Blade-style templates, Artisan-style commands — and implements them in
modern Python. Requests, the ORM, queue workers, and the scheduler all run on `asyncio`, and the
FastAPI application underneath is never taken away from you.

It is a parity project, not an homage. Each area of the framework is built against the
corresponding page of Laravel's documentation, method by method, and every deliberate divergence
is named in Avalon's own page for that feature — so `Str`, `Collection`, the query builder, and the
scheduler behave the way your muscle memory expects, while `async`/`await`, type hints, context
managers, and dataclasses are used where Python has the better answer.

| Piece | What it is |
| --- | --- |
| **Avalon** (`avalon`) | the framework |
| **`avalon new`** | the application installer |
| **Grail** (`grail …`) | the in-app CLI — `grail serve`, `grail make:model`, `grail queue:work`, `grail fiddle` |
| **Caliburn** (`avalon.caliburn`) | the view engine — `.cal.html` templates, directives, components, stacks |
| **Articulate** (`avalon.orm`) | the ORM — models, relationships, migrations, pagination, on SQLAlchemy Core |

## A tour in five files

Routes are declarative and grouped, controllers are plain classes, and route names and middleware
sit where you'd look for them:

```python
# routes/web.py
from app.http.controllers.post_controller import PostController
from avalon.routing import Route

with Route.group(middleware=["web"]):
    Route.get("/posts", [PostController, "index"], name="posts.index")
    Route.get("/posts/{post}", [PostController, "show"], name="posts.show")
```

Models carry their own casts, scopes, and relationships:

```python
# app/models/post.py
from app.models.user import User
from avalon.orm import Model, SoftDeletes, relation


class Post(SoftDeletes, Model):
    fillable = ("title", "body", "published")
    casts = {"published": "bool", "published_at": "datetime"}

    def scope_published(query):
        return query.where("published", True)

    @relation
    def author(self):
        return self.belongs_to(User)
```

Controllers read like their Laravel counterparts, with `await` at the edges:

```python
# app/http/controllers/post_controller.py
from app.models.post import Post
from avalon.caliburn import view
from avalon.http import Controller


class PostController(Controller):
    async def index(self):
        posts = await Post.query().published().with_("author").latest().get()
        return view("posts.index", {"posts": posts})
```

Templates are Caliburn — Blade's directives, compiled to Python:

```html
{{-- resources/views/posts/index.cal.html --}}
@extends('layouts.app')

@section('content')
  @foreach(posts as post)
    <article>
      <h2>{{ post.title }}</h2>
      <p>by {{ post.author.name }} — {{ post.created_at }}</p>
    </article>
  @endforeach
@endsection
```

Console commands and scheduled work are declared together, and run under `grail`:

```python
# routes/console.py
from avalon.console import Artisan, schedule


def send_digest(command) -> int:
    command.info("digest sent")
    return 0


Artisan.command("digest:send", send_digest).purpose("Mail yesterday's digest")

schedule.command("digest:send").daily_at("07:00").timezone("Africa/Nairobi").without_overlapping()
schedule.command("model:prune").daily().on_one_server()
```

## Getting started

### Create an application

Avalon is not on PyPI yet — the `avalon` name there belongs to an unrelated project — so install it
from Git:

```bash
python -m venv .venv && source .venv/bin/activate
pip install "avalon @ git+https://github.com/coolsam726/avalon.git"

avalon new blog
cd blog
pip install -e .        # the framework requirement is already satisfied
grail serve             # or: python grail serve
```

`avalon new` writes a complete application: `app/`, `bootstrap/`, `config/`, `routes/`,
`resources/views` with error pages, `database/migrations`, `storage/`, a Vite config, and a root
`grail` script. Use `grail …` when Avalon is on your `PATH`, or `python grail …` to run the app's
own script explicitly.

### Work on the framework

```bash
git clone https://github.com/coolsam726/avalon.git && cd avalon
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make test          # full unit + smoke suite
make test-cov      # the same, with the coverage gate
make lint          # ruff
make docs          # the documentation site, locally
```

## What ships today

The framework is built in milestones, each closed against a Laravel documentation page. Closed
today:

- **The basics** — routing and route groups, controllers, middleware and aliases, requests and
  responses, session, CSRF, validation with form requests, URL generation, error handling and the
  debug page, logging, asset bundling.
- **Caliburn views** — layouts and sections, includes, control directives, components and slots,
  stacks, and a `dd()` dump page.
- **Articulate ORM** — models with casts and serialization, the whole relationship surface, eager
  loading, soft deletes, pruning, migrations, seeding, pagination, and streaming reads through lazy
  collections.
- **Digging deeper** — the Grail console with prompts and closure commands, the task scheduler
  (frequencies, constraints, hooks, sub-minute tasks), cache, Redis, queues and workers, mail,
  notifications, events, the filesystem, collections, helpers and `Str`, the HTTP client,
  localization, and encryption.
- **Security** — authentication guards and providers, hashing, gates and policies, email
  verification, password confirmation and resets.

Every closed milestone ships four things: the implementation, tests, a documentation page, and a
runnable demonstration in the living example app.

## Documentation

[`website/`](website/) holds 53 pages of application-developer documentation (Astro Starlight),
written to follow Laravel's structure page for page — including a section per method for
[collections](website/src/content/docs/collections.md),
[strings](website/src/content/docs/strings.md), and
[helpers](website/src/content/docs/helpers.md). Run `make docs` to read it locally at
`http://localhost:4321`; the hosted site is not published yet.

[`examples/progress`](examples/progress) is the living example — a real Avalon application that
demonstrates each closed milestone through routes you can visit and `grail progress:*` commands you
can run. Its `/progress` page is the project's milestone board.

## How the project is built

[**`docs/PLAN.md`**](docs/PLAN.md) is the binding architecture and milestone document: 51
milestones, each mapped to the Laravel documentation it must match, with the parity audit and the
named deviations recorded in place. [**`docs/SMOKE.md`**](docs/SMOKE.md) records the exit criteria
that close a milestone.

The gates are enforced in CI on Python 3.11, 3.12, and 3.13:

| Gate | Command |
| --- | --- |
| Milestone smoke tests | `make smoke` |
| Contract regressions | `make regression` |
| Full suite, coverage **≥ 98%** (aim 100%) | `make test-cov` |

`make lint` runs ruff locally but is not a CI gate yet, and does not pass — choosing a rule set and
clearing the backlog is [M51](docs/PLAN.md).

Currently **1,886 tests** at **99.38%** coverage.

## Status

**25 of 51 milestones closed.** M5 (Articulate ORM) and M30 (Grail console exhaust) are
deliberately partial, with the remainder scheduled. Next up: **M42 — query builder and database
exhaust**.

## Repository layout

```text
src/avalon/
  framework/     # Application, container, providers, bootstrap
  config/        # env + config repository
  http/          # kernel, request, response, middleware
  routing/       # Route DSL → FastAPI bridge
  validation/    # form requests, rules, messages
  orm/           # Articulate — models, relations, builder, migrations
  caliburn/      # Caliburn views — compiler, directives, components
  auth/          # guards, providers, gates and policies
  console/       # Grail commands, prompts, scheduler, fiddle
  queue/         # jobs, dispatcher, workers, failed jobs
  cache/         # cache repository and stores
  mail/          # mailables and transports
  notifications/ # channels and notifiables
  events/        # dispatcher, listeners, subscribers
  filesystem/    # Storage disks
  client/        # HTTP client
  support/       # collections, helpers, Str, Number
  translation/   # __(), trans_choice(), locales
  installer/     # avalon new
  grail/         # the grail CLI
docs/            # PLAN.md, SMOKE.md — the binding project documents
website/         # the documentation site (Astro Starlight)
examples/        # the living example application
tests/           # unit, smoke, and regression suites
grail            # root script → the same CLI as `grail`
```

## Contributing

Read [`docs/PLAN.md`](docs/PLAN.md) first — it is the source of truth for what belongs where and
what parity means for the area you are touching. Work in milestone order, keep the coverage gate
green, add the documentation page alongside the code, and extend
[`examples/progress`](examples/progress) so the new surface can be demonstrated, not just claimed.

## License

[MIT](LICENSE) © Avalon Contributors
