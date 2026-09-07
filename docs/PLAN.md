# Avalon — Canonical Plan

> **Status:** Binding. This document is the source of truth for architecture and milestones.
> Change it deliberately (PR / explicit decision), not casually mid-implementation.
> Last aligned: 2026-09-05 (M9 complete; post-M13 Digging Deeper + Articulate NoSQL queued).

## Working identity

- **Project / repo / distribution:** `avalon` (PyPI: `avalon`)
- **Import root:** `avalon` with intentional **subpackages**
- **CLIs (Laravel parallel):**
  - **`avalon new <app>`** — installer / project creator (like `laravel new`) — `avalon.installer`
  - **`python grail …`** — in-app commands via a root `grail` script (like `php artisan …`) — `avalon.grail`
  - Do **not** use Grail for project creation; do **not** use `avalon` for day-to-day app commands
- **HTTP engine:** FastAPI on Starlette (ASGI) — hidden behind Avalon’s programming model, with an escape hatch to the underlying FastAPI app for advanced cases
- **Validation / OpenAPI:** Pydantic v2 via Form Request–style classes
- **Views:** **Caliburn** (`avalon.caliburn`) — Blade-familiar syntax, featherweight render path, templates as **`.cal.html`**
- **Theme:** Arthurian naming for products/tools (`grail`, `Caliburn`); keep public APIs Laravel-familiar (`Route`, `Controller`, `Middleware`, `config()`, `@extends`)
- **App layout naming:** Python snake_case packages/modules (`app/models/post.py`); PascalCase **classes** and Laravel-shaped directory *roles* (`models`, `http/controllers`). See [Directory Structure](../website/src/content/docs/structure.md).

## Design picture (target DX)

Developers create apps with `avalon new`, then run `python grail …` inside the app (controllers, providers, `routes/`, `config/`). Avalon boots a service container, registers providers, compiles routes into FastAPI, and serves via Uvicorn. FastAPI/Starlette remain implementation details of the HTTP kernel. Views compile Caliburn templates (`.cal.html`) to fast Python callables.

```mermaid
flowchart LR
  subgraph appDev [App_code]
    Routes[routes/web_and_api]
    Controllers[Controllers]
    Providers[Providers]
    Models[Models]
    Commands[Console_commands]
    Jobs[Jobs]
    CalTemplates[cal.html_templates]
  end

  subgraph avalonPkg [avalon]
    Installer[avalon_new_CLI]
    Grail[python_grail_CLI]
    Framework[avalon.framework]
    Http[avalon.http]
    Routing[avalon.routing]
    ProvidersPkg[avalon.providers]
    Console[avalon.console]
    Filesystem[avalon.filesystem]
    Queue[avalon.queue]
    Orm[avalon.orm]
    Caliburn[avalon.caliburn]
  end

  subgraph engine [Engine]
    FastAPI[FastAPI]
    SA[SQLAlchemy_2]
    Workers[queue_workers]
  end

  Installer -.->|scaffolds_app_with_grail_script| Grail
  Grail --> Framework
  Grail --> Console
  ProvidersPkg --> Framework
  Routes --> Routing
  Routing --> Http
  Http --> FastAPI
  Controllers --> Framework
  Commands --> Console
  Jobs --> Queue
  Queue --> Workers
  Queue --> Filesystem
  Models --> Orm
  Orm --> SA
  CalTemplates --> Caliburn
  Http --> Caliburn
```

## Package layout

```text
avalon/
  pyproject.toml
  src/avalon/
    framework/                 # Application, container, boot lifecycle
    config/                    # config repository, env
    providers/                 # core service providers + Provider base
    http/                      # kernel, request, response, middleware, controllers (+ M23 API Resources)
    routing/                   # Route DSL → FastAPI bridge
    validation/                # FormRequest
    translation/               # M4 — translator, plurals, Number, lang tooling
    grail/                     # in-app CLI entry (python grail …)
    exceptions/                # M8 — handler, debug page, error rendering
    log/                       # M8 — channels, log()
    console/                   # M9 — commands, scheduling
    filesystem/                # M10 — disks / FlySystem-shaped Storage
    queue/                     # M11 — jobs, workers, failed jobs
    mail/                      # M12 — Mailable, Mailer, transports
    notifications/             # M13 — Notifiable, channels (mail, database, …)
    support/                   # Collections (shipped); Helpers + Str (M14)
    cache/                     # M15 — Cache store + drivers
    redis/                     # M16 — Redis connection + session/cache/queue drivers
    encryption/                # M17 — Crypt façade
    events/                    # M18 — app event dispatcher (model events stay in orm)
    auth/                      # M7 (+ M19 Gates/Policies)
    client/                    # M20 — outbound HTTP client (or avalon.http.client)
    process/                   # M21 — Laravel Processes parity
    concurrency/               # M22 — concurrent closures / pools
    scout/                     # M27 — search (optional extra)
    broadcasting/              # M26 — Echo-class fan-out
    testing/                   # M28 — TestCase helpers beyond pytest baseline
    installer/                 # avalon new …
    orm/                       # M5 (+ M24 factories, M25 NoSQL/document stores)
    caliburn/                  # M6 — optional for API apps
    session/                   # M7 — session, CSRF, cookie encrypt
  tests/
  examples/
  docs/
```

**Import examples:**

- `from avalon.framework import Application`
- `from avalon.routing import Route`
- `from avalon.http import Controller, Middleware`
- `from avalon.providers import ServiceProvider`
- `from avalon.validation import FormRequest`
- `from avalon.translation import __, trans, trans_choice, Number, Lang`
- `from avalon.orm import Model`
- later: `from avalon.caliburn import ViewFactory`
- later: `from avalon.filesystem import Storage`
- later: `from avalon.queue import Job, dispatch`
- later: `from avalon.mail import Mail, Mailable`
- later: `from avalon.notifications import notify, Notifiable`
- later: `from avalon.support import collect, Str`  # Helpers/Str expand in M14
- later: `from avalon.cache import Cache`
- later: `from avalon.encryption import Crypt`
- later: `from avalon.events import Event, dispatch as event`
- later: `from avalon.auth import Gate, Policy`  # M19
- later: `from avalon.http.client import Http`  # M20 naming TBD
- later: `from avalon.process import Process`
- later: `from avalon.concurrency import Concurrency`
- `from avalon.exceptions import Handler`
- `from avalon.log import log`
- `from avalon.console import Command, schedule`

### Subpackage boundaries

| Subpackage | Responsibility |
| --- | --- |
| `avalon.framework` | Application, IoC container, boot |
| `avalon.config` | `.env`, config files, `config()` |
| `avalon.providers` | Provider base + framework providers |
| `avalon.http` | Kernel, request/response, middleware, base controller |
| `avalon.routing` | Route definitions, groups, compiling onto FastAPI |
| `avalon.validation` | FormRequest / validation errors |
| `avalon.translation` | Translator, `lang/` catalogs, `__()` / `trans()` / `trans_choice()`, namespaces, Number/date helpers, locale resolution (M4) |
| `avalon.grail` | In-app CLI entrypoint (`python grail …`) — thin Typer surface over console kernel |
| `avalon.exceptions` | Handler (`report`/`render`), debug page, error views (M8) — distinct from `avalon.http.exceptions`, which holds the `HttpException` classes |
| `avalon.log` | Log channels + `log()` helper (M8) |
| `avalon.console` | Command base, discovery, scheduler (M9) |
| `avalon.filesystem` | Disks, Storage façade, FlySystem-shaped drivers (M10) |
| `avalon.queue` | Jobs, queues, workers, failed-job handling (M11) |
| `avalon.mail` | Mailable, Mailer, transports, Markdown mail (M12) |
| `avalon.notifications` | Notifiable, notification channels, database notifications (M13) |
| `avalon.support` | Support `Collection` (shipped); Laravel Helpers + `Str` (M14) |
| `avalon.cache` | Cache store + drivers (M15) |
| `avalon.redis` | Redis connection manager + drivers for cache/session/queue (M16) |
| `avalon.encryption` | `Crypt` façade — encrypt/decrypt/serialize (M17); cookie encrypt already under `avalon.session` (M7) |
| `avalon.events` | Application event dispatcher / listeners / subscribers (M18) |
| `avalon.installer` | Installer CLI (`avalon new`) |
| `avalon.orm` | Eloquent-like ORM (M5); model factories (M24); NoSQL / document-store drivers (M25) |
| `avalon.caliburn` | Caliburn compiler/runtime (M6) |
| `avalon.auth` | Guards, middleware (M7); Gates / Policies (M19) |

## Ecosystem growth

Start as **one installable `avalon`**. When Caliburn, kits, filesystem drivers, or queues get large:

1. **Same repo, optional extras** — e.g. `pip install avalon[caliburn]`, or
2. **Monorepo of distributions** still under the `avalon.*` namespace, plus starter-kit packages

Do **not** rename the project to `avalon_framework`. “Framework” is the `avalon.framework` subpackage.

**Rules:**

- Core happy path must not require Caliburn; API apps never import `avalon.caliburn`
- `avalon.caliburn` stays framework-light and dependency-thin; integrate via a view provider
- Starter kits and heavy subsystems stay out of the default import surface
- App code uses `avalon.*` only — no FastAPI imports on the happy path

## Decision: ORM (Eloquent-like)

**Chosen approach:** Eloquent-shaped **Active Record + Query Builder API** as `avalon.orm`, built on **SQLAlchemy 2.0 Core (async-first)**.

**Parity target:** full Eloquent parity — models, query builder, every relationship type, eager loading, collections, casts, accessors/mutators, scopes, soft deletes, events/observers, pagination, transactions, and migrations. M5 is **not** a subset; it exhausts this contract.

**Core over ORM (binding):** Avalon uses SQLAlchemy **Core** (expression language, dialects, pooling, async engine) and implements Active Record itself. SQLAlchemy's declarative/Session unit-of-work is deliberately **not** used — it contradicts Active Record semantics (identity map, flush ordering, detached instances) and would leak through the DX. This keeps `avalon.orm` in control of the model lifecycle.

**Async-first (binding):** Every query/persistence operation is awaited, because Avalon runs on ASGI:

```python
user = await User.query().where("email", email).first()
posts = await Post.query().with_("author", "comments").find(1)
published = await user.posts().where("published", True).get()
```

Sync Eloquent-style calls are **not** offered — a hidden sync bridge under async is a footgun, not DX.

**Internal rule:** App code depends on `avalon.orm`, not SQLAlchemy — except documented escape hatches (`DB.raw`, `DB.connection().execute`).

### Decision: Articulate multi-store (SQL + NoSQL) — binding for M25

M5 exhausted **SQL** Eloquent parity on SQLAlchemy Core. **NoSQL is not a second ORM and not a forever-Later extra** — it is a scheduled Articulate core track (**M25**) so document stores share the same Active Record mental model where semantics match, without pretending every SQL feature exists on Mongo.

**Why bake into Articulate (not a satellite package):** a bolt-on `avalon.mongo` that reimplements models/collections/events will fork the DX and force apps to learn two ORMs. Queuing NoSQL as Articulate work forces the connection/model boundary to stay honest while SQL remains the default happy path.

**Contract (binding when M25 lands; design constraint from now):**

| Concern | Rule |
| --- | --- |
| Package home | `avalon.orm` — same `Model` / `DB` / `Collection` import root; store-specific code behind connection drivers |
| Default | SQL connections stay the scaffold default; NoSQL is opt-in via `config/database.py` + extras (`avalon[mongo]`, …) |
| Connection | Every connection declares a **store kind** (`sql` \| `document` / driver name). Models bind to a connection (explicit or default) |
| Shared DX | Casts, accessors/mutators, dirty tracking, soft deletes (where meaningful), model events/observers, Support/Eloquent collections, pagination shapes — reuse when semantics are honest |
| Divergent DX | Schema builder / SQL migrations do **not** fake-map onto document collections; relationships are reference/embed (or driver-documented equivalents), not SQL join theater; query builder exposes only what the driver can honor |
| Escape hatches | Driver-native APIs behind documented façades (e.g. Mongo collection access) — never leak motor/pymongo types into happy-path app signatures |
| Exhaust rule | M25 exhausts **MongoDB** as the first document driver end-to-end (config → model → query → tests → docs). Other NoSQL (Cosmos API, Dynamo-shaped, …) may follow as additional drivers under the same store abstraction — do not claim them in M25 unless exhausted |
| Non-goals | Replacing SQL Articulate; dual-write magic; automatic SQL↔document sync; pretending `belongs_to_many` pivots exist on documents |

**Until M25:** do not add ad-hoc Mongo helpers outside this contract. SQL M5 APIs may keep evolving, but new Articulate internals should prefer connection/driver seams that M25 can plug into rather than hard-wiring SQLAlchemy types into every public path.

### Parity ladder (all in M5)

1. **Connections:** `config/database.py`, multiple connections, SQLite / PostgreSQL / MySQL+MariaDB / SQL Server (Laravel first-party set) plus optional Oracle, `DB` façade, raw queries, transactions (+ nested via savepoints)
2. **Model:** table/key inference, `fillable`/`guarded` + `MassAssignmentException`, `casts`, defaults, accessors/mutators, dirty tracking (`is_dirty` / `get_changes` / `get_original`), timestamps, `hidden`/`visible`/`appends`, `to_dict`/`to_json`, `save`/`update`/`delete`/`refresh`/`replicate`/`is_`
3. **Builder:** full `where` family (in / null / between / date parts / column / like / nested closures / or-variants), ordering, grouping + having, limit/offset, select + distinct + raw, joins, aggregates, `pluck`/`value`, `exists`, `find_or_fail`, `first_or_create`, `update_or_create`, `increment`/`decrement`, dialect-native `upsert` (SQLite/PG `ON CONFLICT`, MySQL `ON DUPLICATE KEY`; probe fallback otherwise), `chunk`/`cursor`/`each`, `when`/`unless`, `to_sql`
4. **Relationships:** `has_one`, `has_many`, `belongs_to`, `belongs_to_many` (pivot columns, `attach`/`detach`/`sync`/`toggle`), `has_one_through`, `has_many_through`, polymorphic (`morph_one`, `morph_many`, `morph_to`, `morph_to_many`, `morphed_by_many`)
5. **Eager loading:** `with_` (nested + constrained), `with_count`, lazy `load` / `load_missing`, `has` / `doesnt_have` / `where_has` / `where_doesnt_have`. **Attribute lazy-load is off by default** (unloaded `model.rel` raises). Opt in with `Model.lazy_relations = True` so `await model.rel` loads — still an explicit `await`, never hidden sync IO on attribute access.
6. **Collections:** Eloquent-shaped `Collection` returned from every multi-row read
7. **Scopes & lifecycle:** local scopes, global scopes, soft deletes (`trashed` / `with_trashed` / `only_trashed` / `restore` / `force_delete`), model events + observers
8. **Pagination:** `paginate` / `simple_paginate` with a JSON-serializable paginator
9. **Migrations:** Schema builder (`Schema.create` + `Blueprint`) over SQLAlchemy DDL; ordered Python migration files + a `migrations` table (not Alembic revisions); `make:model` (+`-m`), `make:migration` with Laravel TableGuesser name inference (create/update/blank stubs + StudlyCase class from slug), `migrate`, `migrate:rollback`, `migrate:fresh`, `migrate:status`. **Column modifiers (shipped):** chain on the creation line — `nullable()`, `default(...)`, `unique()`, **`index()`**, `primary()`, `after` / `before` (MySQL/MariaDB), `constrained()` — matching Laravel `$table->string('email')->index()`. Table-level `index([...])` / `unique([...])` also ship.
10. **Seeders:** `Seeder` with `call` / `call_with` / `call_silent` / `call_once` / `resolve` / invoke; `WithoutModelEvents`; `make:seeder`; `db:seed` / `migrate --seed` / `migrate:fresh --seed` (`--class` / `--seeder`); scaffold `DatabaseSeeder`. **Model factories are deferred to M24** — seeders must stay usable without them; factories later feed `DatabaseSeeder` the Laravel way (`User::factory()->count(10)->create()`).

**Rules:**

- N+1 must be *fixable*: eager loading is not optional polish, it ships with relationships.
- No SQLAlchemy types in app-facing signatures or return values.
- Mass assignment is guarded by default — `fillable` opt-in, never silently accept arbitrary input.
- Model events must fire for the documented lifecycle, including soft-delete restore.
- Migrations must round-trip: `migrate` → `migrate:rollback` returns the schema to its prior state.

**Deferred (declared, not M5):** database sessions/queue drivers (M11), model caching, read/write connection splitting, **model factories** (**M24**), and **NoSQL / document stores** (**M25** — Articulate multi-store; see decision above).

## Decision: Documentation site (`website/`)

App-facing docs live in Astro Starlight under [`website/`](../website/). `PLAN.md` / `SMOKE.md` stay contributor contracts in `docs/`.

**Keep in plan (not blocking product milestones forever, but Basics is blocking before M7 code):**

1. **Major-version docs** — publish and switch among major Avalon versions (e.g. `1.x` / `2.x`) from the docs site, Laravel-style. Exact mechanics TBD (Starlight versioning, separate versioned content trees, or a thin version switcher); the requirement is that readers can open docs for the major they run.
2. **Prologue** — a top-level sidebar group (Laravel “Prologue”) holding **Release Notes / Changelog**, **Upgrade Guide**, and related orientation pages, versioned with the docs set above.
3. Changelogs and upgrade guides are **first-class docs content**, not only GitHub Releases prose.
4. **The Basics** — Laravel’s “The Basics” sidebar is the reader’s mental map of the HTTP stack. Avalon must mirror that map (Avalon names where they differ). Empty Basics (only Middleware) is a **docs bug**, not a product gap for most of those topics.

Do not invent a second docs engine; extend the Starlight site.

### The Basics — Laravel map → Avalon (binding)

Mirror Laravel’s Basics **order and coverage**. Deep Caliburn how-tos stay in the **Caliburn** sidebar (like Laravel’s separate Blade section); Basics **Views** is the short entry + pointer.

| Laravel Basics | Avalon docs slug (target) | Code status | Docs action |
| --- | --- | --- | --- |
| Routing | `routing` | **Shipped (M2)** — `Route` DSL, groups, polarity | **Done** |
| Middleware | `middleware` | **Shipped (M2)** | **Done** |
| CSRF Protection | `csrf` | **Shipped (M7 foundation)** — `VerifyCsrfToken` + `@csrf` | **Done** |
| Controllers | `controllers` | **Shipped (M2/M3)** — base `Controller`, `make:controller`, DI | **Done** |
| Requests | `requests` | **Shipped (M2)** — `Request` bag | **Done** |
| Responses | `responses` | **Shipped (M2)** — `Response`, `html()`, JSON polarity | **Done** |
| Views | `views` | **Shipped (M6)** — `view()` / `ViewFactory` | **Done** — overview + link to Caliburn |
| Blade Templates | *(Caliburn section)* | **Shipped (M6)** | **Done** as Caliburn group (not duplicated under Basics) |
| Asset Bundling | `asset-bundling` | **Partial (M6)** — `asset()` / `@asset` + `public/` on `grail serve`; default `avalon new` ships **Vite + Tailwind** → `public/build`; Python core stays Node-free; starter kits may replace/extend | **Partial** — default scaffold + docs; full `@vite` helper follow-up |
| URL Generation | `urls` | **Partial (M3)** — `url()`, `asset()`, `redirect()`; named `route()` = Later | **Done** |
| Session | `session` | **Shipped (M7 foundation)** — cookie driver, encrypt, flash | **Done** |
| Authentication | `authentication` | **Shipped (M7)** — guards, remember-me, events, docs | **Done** |
| Hashing | `hashing` | **Shipped (M7)** — bcrypt + optional argon2id | **Done** |
| Passwords | `passwords` | **Shipped (M7)** — broker + confirm; outbound mail **M12**/**M13** | **Done** |
| Validation | `validation` | **Shipped (M3)** — `FormRequest` | **Done** |
| Error Handling | `errors` | **Shipped (M8)** — Handler, polarity pages, publish | **Done** |
| Logging | `logging` | **Shipped (M8)** | **Done** |

**Starlight sidebar target for “The Basics”:**

```
The Basics
  Routing
  Middleware          # existing
  CSRF Protection     # M7 (placeholder OK until then)
  Controllers
  Requests
  Responses
  Views
  Asset Bundling
  URL Generation
  Session             # M7
  Validation
  Error Handling      # thin now / full M8
  Logging             # M8
```

Caliburn remains its own top-level group (Blade equivalent). Do **not** put the full Caliburn tutorial under Basics.

**Gate before starting M7 implementation:** Basics pages for shipped surfaces are published and linked in `website/astro.config.mjs` (**met**). Expand CSRF / Session / Logging placeholders when those milestones land — not fake APIs.

### Digging Deeper — scheduled surfaces (binding when milestones land)

Laravel’s Digging Deeper / Security / Packages clusters map onto Avalon as follows. Starlight sidebars grow when each surface ships — do not stub fake APIs ahead of the milestones.

| Laravel | Avalon docs slug (target) | Milestone | Docs action |
| --- | --- | --- | --- |
| Collections | `collections` | Support Collections | **Done** |
| Localization | `localization` | **M4** (code **Done**) | **Docs gap** — write Starlight Localization page (code already exhausted) |
| Helpers | `helpers` | **M14** | Shipped |
| Strings | `strings` | **M14** | Shipped |
| Cache | `cache` | **M15** | Shipped |
| Redis | `redis` | **Done (M16)** | Redis page + Cache/Session/Queues updates |
| Encryption | `encryption` | **M17** | `Crypt` façade, JSON-safe encrypt, `APP_PREVIOUS_KEYS`, `key:generate` |
| Events | `events` | **M18** | Write when app event dispatcher ships (model events already in Articulate) |
| Broadcasting | `broadcasting` | **M26** | Write when broadcasting ships |
| Authorization | `authorization` | **M19** | Write when Gates/Policies ship |
| HTTP Client | `http-client` | **M20** | Write when HTTP client ships |
| Processes | `processes` | **M21** | Write when Processes ship |
| Concurrency | `concurrency` | **M22** | Write when Concurrency ships |
| Eloquent: Mutators & Casting | Articulate page / section | **M5** (code **Done**) | **Docs deepen** — dedicated Mutators & Casts how-to (surface lives in Articulate index today) |
| Eloquent: Serialization | `articulate/serialization` | **M23** | Write with API Resources |
| Eloquent: API Resources | `eloquent-resources` / `api-resources` | **M23** | Write when Resources ship |
| Eloquent: Factories | `database/factories` | **M24** | Write when factories ship |
| MongoDB / NoSQL | `database/nosql` (+ Articulate pages) | **M25** | Write when document-store driver ships — core Articulate multi-store, not a satellite ORM |
| Scout / Search | `scout` / `search` | **M27** | Write when search ships |
| Queues | `queues` | **M11** | Write when queues ship |
| Mail | `mail` | **M12** | Write when mail ships |
| Notifications | `notifications` | **M13** | Write when notifications ship |
| Testing | `testing` (+ subpages) | **M28** | Write when testing toolkit expands |
| Packages | `packages` | **M29** | Write package-dev guidelines when that milestone lands |

Starlight **Digging Deeper** / **Security** / **Database** / **Packages** sidebars grow with those pages.

## Decision: Views — Caliburn

Caliburn is a **first-class view engine for Python**, not a thin wrapper around Jinja or FastAPI templates. **M6 exhausts full Laravel Blade parity** for the documented surface — the same exhaust rule as Articulate and localization. A partial “MVP forever” exit is not allowed.

| Item | Choice |
| --- | --- |
| Product name | Caliburn |
| Package | `avalon.caliburn` |
| Template extension | **`.cal.html`** |
| Inline code | **`@python` / `@endpython` only** (no freeform Python embedding) |
| DX north star | **Full Blade parity** — layouts, inheritance, components, slots, directives |
| Performance north star | **Featherweight** — first-class constraint |
| Docs | **Own Starlight section** (`website/…/caliburn/`) — thorough, Laravel Blade–shaped; write pages as surfaces ship |

Logic belongs in controllers, view models, and composers. `@python` is an escape hatch, not the default style.

### Parity target (binding)

Match Blade’s mental model end-to-end for app authors:

1. **Echo & comments** — `{{ }}` (escaped), `{!! !!}` (raw), `{{-- --}}`
2. **Layout inheritance** — `@extends`, `@section` / `@endsection` / `@show`, `@yield`, `@parent`, `@include` / `@includeIf` / `@includeWhen` / `@each`
3. **Control flow** — `@if` / `@elseif` / `@else` / `@unless` / `@isset` / `@empty` / `@auth` / `@guest` (auth wired when M7 exists; stubs/no-ops until then where needed), `@for` / `@foreach` / `@forelse` / `@while`, `@php` → **`@python` / `@endpython`**
4. **Components & slots** — class-based and anonymous components, `<x-name>` / `@component`, **slots** (`@slot`, `$slot`, named slots), attribute bags (`$attributes`), `@props`, `@aware`
5. **Stacks** — `@push` / `@prepend` / `@stack` / `@once`
6. **Framework directives** — `@csrf`, `@error`, `@lang` / `@choice` / `__()`, `@vite`-class asset helpers as `asset()` / `@asset` (subpath-aware from day one). **No Node dependency in Python core** — M6 owns URL helpers + `public/` serving for `grail serve`. Default `avalon new` (no starter kit) ships **Vite + Tailwind** scaffolding that emits into `public/build/`. Starter kits may replace or extend that toolchain. A first-class Caliburn `@vite` / hot-file helper is a follow-up on top of `asset()`.
7. **Extensibility** — `Engine.directive(...)` / service-provider registration for **custom `@directive`s**; app-owned Blade-style component libraries under `resources/views/components`
8. **Tooling** — `view()`, `ViewFactory`, compiled view cache, `grail view:clear` / `view:cache` when the console kernel can host them (M9); until then engine APIs + tests

**Rules:**

- Compile ahead, render thin — no re-lex/parse on the request hot path.
- XSS defaults match Blade: escape by default; raw is explicit.
- Caliburn templates are Avalon’s own (`.cal.html`), not “Jinja with Blade lipstick.”
- Do not claim M6 complete until the parity ladder below is exhausted **and** the Caliburn docs section covers it for app developers.

### Performance principles (non-negotiable)

- **Compile ahead, render thin** — no re-lex/parse on the request path
- **Aggressive compiled-cache** — mtime invalidate in dev; warm cache in prod
- **Minimal runtime** — thin dependency graph on the hot path
- **Zero-cost unused features**
- **Benchmark from day one** — echo, layout+sections, foreach, components; regression guards
- **Compare honestly** — Caliburn vs Jinja2 on shared fixtures

### Iteration ladder (exhaust inside M6)

1. **Layouts & echo:** `{{ }}`, `{!! !!}`, `@extends` / `@section` / `@yield` / `@parent`, `@include*` / `@each`, `{{-- --}}` — **shipped (advanced include variants)**
2. **Control flow:** `@if` family, `@isset` / `@empty(expr)`, `@foreach` / `@forelse` / `@for` / `@while`, `@auth` / `@guest` stubs, `@python` — **shipped**
3. **Components & slots:** `@component` / `<x-*>`, named + default slots, `<x-slot>`, attribute bags, `@props`, `@aware`, class-based `Component`, nested components
4. **Stacks + framework directives:** `@push` / `@stack`, `@lang` / `@choice` / `__()`, `@csrf` / `@error` / `@asset` stubs, asset helpers — **shipped (advanced surfaces)**
5. **Advanced:** composers, creators, fragment `@cache`, custom `Engine.directive`, `cache_views` / `clear_cache` — **shipped**

### Documentation (binding)

Ship a dedicated **Caliburn** sidebar group (peer to Articulate / Database), Laravel Blade–shaped topics, for example:

- Getting Started / Rendering Views
- Layouts & Inheritance
- Components & Slots
- Control Structures
- Including Subviews
- Stacks & Custom Directives
- Localization in views (`@lang` / `__`)

Pages land as each ladder rung ships — do not wait for M6 close to start the section.
## Decision: Scope discipline

Bite-sized milestones. **No** queues, notifications, scheduler, or mail until the **HTTP + validation + i18n + ORM + views + auth** core path is boring and tested (through M7). Seeders ship with M5 ORM; **model factories follow at M24**; **Articulate NoSQL / document stores at M25** (multi-store core — see ORM decision). Caliburn is its own track after the core gate. Error handling, console (incl. a Tinker-class REPL), filesystem, queues, **mail**, and **notifications** are sketched as **M8–M13**; Digging Deeper + Articulate follow-ons (helpers through packages, including NoSQL) are sketched as **M14–M29** so the roadmap is honest — they are not next work until their predecessors land. Multi-version docs + Prologue stay on the docs track (see Documentation site decision). **Localization docs** and **Articulate Mutators/Casts docs** are docs-track follow-ups on already-shipped M4/M5 code — they may land before M14.

**Localization is the one deliberate exception to “defer until needed.”** It sits at M4 because retrofitting translations across four message-producing layers costs far more than building them translatable. M4 exhausts **full Laravel localization parity** (not a thin core) — see the localization decision.

**Exhaust means full parity within the milestone’s declared scope.** Do not ship thin placeholders that claim a feature is done. Iterate inside the milestone (API + tests + living example) until the Laravel/Adonis-class DX for that slice is real, then move on. “Optional if light” / partial façades are not an exit criteria.

## Decision: Support Collections (`avalon.support`)

Laravel’s [`Illuminate\Support\Collection`](https://laravel.com/docs/collections) is **not** Eloquent’s model collection. Articulate already returns an Eloquent-shaped `Collection` from multi-row reads; Avalon also ships a first-class **Support** collection for general list/map work — `collect()` + fluent chains — matching Laravel’s Collections docs.

| Concern | Contract |
| --- | --- |
| Package | `avalon.support` — `Collection`, `collect()`, class helpers (`times`, `range`, `wrap`, `unwrap`, `make`) |
| Keys | Ordered-map semantics (list → contiguous int keys; dict keeps keys) |
| Returns | Transformers return **new** instances; `push` / `put` / `pop` / `pull` / `transform` match Laravel mutability |
| Macros | `Collection.macro(name, callback)` |
| Eloquent | `avalon.orm.collection.Collection` **extends** Support `Collection` (`load` / `load_missing` / `model_keys`) |
| Lazy | `LazyCollection` deferred until a streaming consumer needs it |
| Docs | Starlight **Collections** page (Support) + pointer from Articulate |

**Gate:** eager `Collection` exhausts the Laravel “Available Methods” list (skip Lazy / `dd` / `dump`); tests + docs green; Articulate regressions still pass. Can ship alongside M7 — does not block auth exhaust.

**Status (Collections):** Support `Collection` + `collect()` shipped — method surface (incl. `splice`, `multiply`, `reduce_spread`, assoc/using diffs & intersects, `to_pretty_json` / `from_json`), key-preserving filters, macros, Starlight **Collections** docs, `tests/test_support_collection.py`. Articulate `orm.Collection` extends Support. `LazyCollection` still deferred.

## Decision: Production serving (ASGI)

Avalon apps are **plain ASGI**. There is no proprietary production server.

| Environment | How |
| --- | --- |
| Local | `python grail serve` → Uvicorn on `bootstrap.app:asgi` (dev reload; port walk 3000–3099) |
| Production | Uvicorn (or Gunicorn + Uvicorn workers / Hypercorn) on the same ASGI import path, behind a reverse proxy (Caddy / Nginx / Traefik) for TLS, compression, and optional static files |

**Rules:**

- App code never imports the process server; Grail/`uvicorn` are entrypoints only
- Production docs show workers + proxy; optional later: `python grail serve --workers N` (not required for M3)
- Static/asset CDN remains outside the Python process when possible; Avalon still generates correct public URLs (see subpath)

## Decision: Subpath hosting (first-class)

Laravel’s common failure mode — apps under `/apps/foo` with broken absolute `/…` assets and redirects — is **out of scope as a “proxy only” problem**. Avalon treats the public mount path as framework config.

| Config | Role |
| --- | --- |
| `APP_URL` | Canonical public origin (scheme + host[+port]), e.g. `https://example.com` |
| `APP_BASE_PATH` | Public path prefix, e.g. `/apps/foo` (empty or `/` = site root) |

**Contract (binding):**

1. **URL helpers** (`url()`, `route()`, `redirect()`, asset helpers) always honor `APP_BASE_PATH`
2. **Router / ASGI** either compile routes under the prefix or mount the ASGI app at it — one mechanism, documented; no double-prefix bugs
3. **Trusted proxies** (`X-Forwarded-Proto` / `Host` / `Prefix` as configured) so generated URLs match the public edge
4. **Caliburn asset helpers** (M6) must be prefix-aware from day one — never bake root-absolute asset paths that ignore `APP_BASE_PATH`

**Milestone homes:** design locked here; **M3 shipped URL generation** (`url()` / `asset()` / `redirect()`). **ASGI mount at `APP_BASE_PATH` ships with the HTTP kernel** — `grail serve` serves the app under the prefix and redirects `/` → `{base}/`. Caliburn asset helpers (M6) must stay prefix-aware; do not regress the mount.

## Decision: Route files — web vs api

Scaffolded apps ship **`routes/web.py`** and **`routes/api.py`**. They are not interchangeable dumps of the same handlers.

| File | Audience | Response | State | Middleware intent |
| --- | --- | --- | --- | --- |
| `routes/web.py` | Browsers | **HTML** (`text/html`) | **Stateful** (cookies / session once M7 exists) | Future `web` group: session, cookie encryption, CSRF |
| `routes/api.py` | Machines / SPAs / clients | **JSON** (`application/json`) | **Stateless** | Future `api` group: no session/CSRF; auth via token/bearer |

**Contract (binding; shipped in M2):**

1. Controllers registered in `web.py` return HTML (string / `html()` helper / later Caliburn `view()`). Do **not** default web routes to JSON dicts.
2. Controllers registered in `api.py` return JSON (dict/list / `json()`). Do **not** return HTML from API routes.
3. Framework does **not** auto-negotiate content type from `Accept` to paper over mixing the two files — put the route in the right file.
4. Stateful `web` means session + CSRF + encrypted cookies (M7); `api` stays bearer-only.
5. Until Caliburn (M6), web HTML may be hand-built strings via `html()` — still HTML, not JSON-as-HTML.
6. `HttpException` on API stays JSON `{message, status, errors?}`. On web, prefer HTML error pages once views exist; until then a minimal HTML error body is acceptable for web-only routes.

**Known boundary:** `avalon.http.Response` is currently Starlette's `Response` re-exported so controllers can annotate HTML actions without importing Starlette. App code still imports `avalon.*` only. An Avalon-owned response object is a candidate for a later DX pass — only if it earns its keep.

**Middleware groups (shipped):** `config/http.py` declares empty `middleware_groups` shells; **`bootstrap/app.py`** registers aliases and fills `web` / `api` via `Application.configure().with_middleware(...)`. Route files still reference groups by name (`Route.group(middleware=["web"])`). The kernel expands group names into their members before resolving aliases, recursively, and raises on circular references. **`web`** includes EncryptCookies, StartSession, VerifyCsrfToken, StartAuth; **`api`** stays without session/CSRF (StartAuth for bearer only). API throttling/CORS remain in the hardening pass.

**Living example rule:** Request-bag / verb demos that return structured data live under **`/api/…`**. Browser pages (`/`, progress board) live under **`web.py`** and render HTML.

## Decision: Router DX beyond core verbs

**M2 delivered:** `get` / `post` / `put` / `patch` / `delete` / `options` / `any` / `match`; per-route `middleware=` / `name=`; **`Route.group(prefix=, middleware=)`** as a context manager, **nestable** — prefixes concatenate and middleware accumulates outer→inner, stack pops on exit. Group middleware may name a **middleware group** (`web` / `api`) or an alias.

Group DX is deliberately **context-manager only**. Laravel's fluent `Route::middleware([...])->prefix(...)->group(...)` chain is not a goal; `with Route.group(...)` is the Pythonic shape and stays the one way to group.

`name=` is currently stored on `RouteDefinition` and passed to the engine, but nothing reads it back until the `route()` helper lands.

**Deferred (do not reopen M2):**

| Item | Home |
| --- | --- |
| `head`, `redirect` / `permanentRedirect`, `fallback`, named `route()` helper | Small DX pass after M3 (or end of M3 if `make:*` is light) |
| **Group options: `name=` (name prefixing), `controller=`, `domain=`, `where=` constraints, `without_middleware`** | Same post-M3 DX pass; `name=` should land with `route()` since they pair |
| `resource` / `apiResource` | When CRUD scaffolding needs them (post-M5 or with API starter) |
| `view` routes | Caliburn (M6) |

## Decision: Security roadmap

M2 shipped the middleware **pipeline + group mechanism** only — `web` and `api` default stacks are empty. Security is **not** implied by M2.

| Concern | Approach | Milestone home |
| --- | --- | --- |
| Security headers (CSP baseline, `X-Frame-Options`, `Referrer-Policy`, etc.) | Default middleware pack; config knobs in `config/http.py` | After M3 / with web hardening — no session dependency |
| CORS | Config + middleware for API apps | Same hardening pass |
| CSRF | Token + session; Caliburn `@csrf` | With sessions (M7 or dedicated web-security slice immediately before/with M7) |
| Cookie signing / encryption | Session / cookie stack | M7 |
| XSS escaping | `{{ }}` escaped vs `{!! !!}` raw | Caliburn M6 |
| CSP nonces | Tied to view rendering | Caliburn M6 ladder (framework directives) |
| Trusted proxies | Request / URL generation | With subpath helpers |
| Rate limiting | Optional middleware | Later |
| `auth` / `guest` | Guards | M7 |

**Rules:**

- Do **not** ship CSRF theater without a real session store
- Default **web** middleware should be secure-by-default once the web stack exists; API scaffolds may omit CSRF
- Exhaust one milestone at a time — do not fold this whole table into M3

## Decision: Request capture (Laravel parity)

`avalon.http.Request` is the app-facing request type. Controllers must not need Starlette/FastAPI request types.

| Concern | Contract |
| --- | --- |
| Hydration | Kernel builds `Request` via `await Request.create(...)` once per request (query + JSON/form body + files) |
| `all()` / `input()` | Query **merged with** body; **body wins**; route params are **not** included |
| `query()` / `post()` / `json()` | Query-only, body-only, parsed JSON |
| `route()` | Path parameters |
| Selection | `only()`, `except_()` (Laravel `except`), `keys()`, `has`, `has_any`, `filled`, `missing` |
| Coercion | `boolean()`, `integer()`, `float()`, `string()` |
| Mutation | `merge()`, `replace()` (middleware-friendly) |
| Files | `UploadedFile`, `file()`, `files()`, `has_file()` |
| Meta | `method`, `path`, `url`, `headers`, `cookies`, `header()`, `cookie()`, `bearer_token()`, `ip()`, `user_agent()`, `is_method()`, `is_json()` |
| Controller injection | `Request` by type/name; route params by name; other type hints via container `make()` |
| Validation | **`FormRequest` (M3)** — not ad-hoc `$request->validate()` on the base Request for M2 exit |

**M2 is closed:** this table is implemented, tested, and exercised in `examples/progress`.

## Decision: Localization (i18n)

i18n is **infrastructure, not a feature bolted on late**. It lands as **M4**, immediately after validation and before ORM, views, auth, and error pages — so every layer that produces user-facing text is born translatable instead of being retrofitted four times.

**Parity target:** everything Laravel ships on its [Localization](https://laravel.com/docs/localization) page plus the `Lang` / `Translator` surface and the localization-adjacent Number / date helpers. M4 is **not** a thin core with follow-ups — exhaust Laravel parity inside the milestone.

**Why early (binding rationale):** at the end of M3 the framework owns roughly 25 English strings, all in `avalon.validation` plus a few exception defaults. That is the entire retrofit cost today. Every later milestone (Caliburn views, auth messages, M8 error pages) multiplies it.

**Catalog layout** (Laravel-shaped, app-owned `lang/`):

```text
lang/
  en/
    validation.py      # framework message overrides (app wins)
    auth.py
    passwords.py
    pagination.py
    messages.py        # app strings
  sw/
    validation.py
    messages.py
  en.json              # flat "string as key" catalog
  sw.json
  vendor/
    some_package/
      en/
        messages.py    # app override of a package catalog
```

Python files return a `dict` (nested ok). JSON files are flat `str → str`. Both forms are first-class.

**Contract — translator:**

| Concern | Contract |
| --- | --- |
| Helpers | `__()` / `trans()` — dotted `file.key` for PHP-style catalogs; literal string key for JSON catalogs |
| Choice | `trans_choice()` / `Lang.choice()` — pipe plurals (`one\|other`), interval forms (`{0} none\|[1,19] some\|[20,*] many`), and **CLDR plural categories** via Babel (zero/one/two/few/many/other per locale) |
| Placeholders | Laravel `:name` replacement; case transforms `:Name` / `:NAME` / `:NaMe` mirror Laravel |
| Count placeholder | `:count` auto-injected by `trans_choice` |
| Locale | `APP_LOCALE` + `APP_FALLBACK_LOCALE`; `app.set_locale()` / `get_locale()` / `is_locale()`; **request-scoped** under ASGI |
| Fallback | missing key → fallback locale → return the key itself (never exception, never blank) |
| Introspection | `Lang.has(key)`, `Lang.has_for_locale(key, locale)` |
| Namespaces | `package::file.key`; packages register via `Lang.add_namespace(name, path)` |
| Vendor overrides | `lang/vendor/<package>/<locale>/…` wins over the package's own catalog |
| Loader surface | `add_path`, `add_json_path`, `add_lines` (runtime lines), matching Laravel's loader API |
| Missing keys | `Lang.handle_missing_keys_using(callback)` — optional app hook; default still returns the key |
| Loading | Catalogs load once and cache; reload in debug / on explicit clear |
| Locale resolution | `SetLocale` middleware: explicit `set_locale()` wins, then request signal (`Accept-Language` for `api`; session/cookie once M7 exists for `web`), then config default |
| Framework messages | Shipped `en` catalogs for `validation` (+ stubs for `auth` / `passwords` / `pagination`); apps override per key without forking the framework |
| Validation retrofit | M3 422/403 envelope and English wording stay **byte-identical** for `en`; messages resolve through the translator thereafter |

**Contract — localization helpers (Laravel-adjacent, in scope):**

| Concern | Contract |
| --- | --- |
| Numbers | `Number.format` / `percentage` / `currency` / `file_size` / `for_humans` — locale-aware via Babel; mirrors `Illuminate\Support\Number` |
| Dates | Setting the app locale also sets the active date locale (Babel/pendulum or equivalent) so formatted dates follow `APP_LOCALE` unless overridden |

**Contract — tooling:**

| Concern | Contract |
| --- | --- |
| Publish | `python grail lang:publish` — scaffolds `lang/` and publishes framework catalogs (Laravel `lang:publish`) |
| Make | `python grail make:lang <locale>` — empty locale tree for a new language |
| Missing | `python grail lang:missing [--locale=xx]` — reports keys present in the fallback but absent in the target |

**Rules:**

- The active locale is **request-scoped**. A process-wide mutable locale is a concurrency bug under ASGI — do not ship one.
- Missing keys must degrade visibly (return the key), not silently render blank.
- Framework strings must be overridable by apps without vendoring the framework catalog.
- Pluralization must be **locale-correct**, not English one/other pretending to be universal — **Babel is a binding dependency** for CLDR plural rules and Number/date formatting.
- `lang:*` / `make:lang` ship on the existing thin Typer `grail` surface (same pattern as M3's `make:*`); they do **not** wait for the M9 console kernel.
- Do not invent features Laravel does not ship (gettext / `.po`, locale-prefixed `/en/…` URLs as framework core).
- Do not fold Caliburn directives, ORM, or auth *copy* into M4 — M4 owns the translator; later milestones **consume** it. Caliburn **must** ship `@lang` / `@choice` / `__()` in views as part of M6's exhaust, wired to this translator.

**Explicitly deferred (not Laravel core i18n):**

| Item | Home |
| --- | --- |
| `@lang` / `@choice` / `__()` Caliburn directives | **M6** — required consumer of M4; not optional |
| Session/cookie locale persistence for `web` | **M7** — once sessions exist; M4 ships `Accept-Language` + explicit set |
| Locale-prefixed URLs (`/en/…`) | Not Laravel core; community pattern only if demand appears later |
| gettext / `.po` interop | Not Laravel; out of scope |

## Decision: Error handling (exceptions + logging)

Exception handling is a **layer**, not a side effect of the HTTP kernel. It gets its own milestone (**M8**) rather than being smuggled into validation or auth work.

**Shipped in M2 (locked, do not regress):**

- `HttpException` subclasses with `{message, status, errors?}`
- Conversion happens **inside** the middleware pipeline, so route middleware decorates error responses
- Unhandled exceptions → 500; message hidden unless `APP_DEBUG`

That is the floor. It is deliberately not a handler layer: there is no app-level hook, no reporting, no HTML error pages, no logging.

**Contract for M8:**

| Concern | Contract |
| --- | --- |
| App handler | `app/Exceptions/Handler.py`, resolved from the container, overridable; framework default when absent |
| Split | `report(exc)` — logging/telemetry side; `render(request, exc)` — response side |
| Suppression | `dont_report` list; `reportable()` / `renderable()` registration hooks |
| Per-exception hooks | Exception classes may define their own `report()` / `render()` |
| Negotiation | **Follows route polarity, not `Accept` guessing** — web routes render HTML; api routes render the JSON envelope. A web route that sends `Accept: application/json` still gets HTML; put the route in `api.py` (or return JSON from the controller) if the client needs the envelope |
| Debug vs production | **Security gate is `APP_DEBUG` only** (not `APP_ENV`). `true` → rich debug page (traceback, source excerpts, request/route context) on **web**; `false` → production error views with a generic safe message. Api always uses the JSON envelope; debug only expands `message` (exception text / class), never dumps stack traces into JSON |
| Production pages | Resolve order: app `resources/views/errors/{status}.cal.html` → published/custom override → framework fallback (dependency-free HTML if Caliburn is unavailable). Cover at least `404`, `419`, `429`, `500`, `503` |
| Publish | `python grail errors:publish [--bundle=default\|tailwind\|bootstrap] [--force]` — copies a chosen set into `resources/views/errors/` for customization (Laravel `vendor:publish --tag=laravel-errors`). Scaffold / `avalon new` ships the **default** set; starter kits may pre-select Tailwind or Bootstrap |
| Bundle variants | Framework ships three **look** bundles under `avalon.exceptions` stubs: `default` (plain CSS, no toolchain), `tailwind`, `bootstrap`. Markup stays Caliburn; CSS/class conventions match the bundle. Core never depends on Node/Tailwind/Bootstrap — kits own compilation; published views assume the kit’s assets when non-default |
| Status mapping | Table mapping common framework/domain exceptions to HTTP status codes |
| JSON envelope | `{message, status, errors?}` is a **locked M2 contract** — M8 extends, never breaks it. Unhandled exceptions on api → `500` with that shape; validation stays `422` with `errors` |
| Logging | `config/logging.py`, channels (`stack`, `single`, `daily`, `stderr`), levels, context; `log()` helper; `report()` writes through it |

**Rules:**

- A debug page that leaks env/secrets when `APP_DEBUG` is false is a security bug — gate it on `APP_DEBUG` and test the gate (`APP_ENV=production` alone is not enough and must not re-enable the debug page)
- Do not ship `report()` without a real log destination; half a logging layer is exactly the placeholder this plan forbids
- Do not reopen M2 polarity for errors: no `Accept`-driven HTML↔JSON flip on the handler path
- Published error views are app-owned after `errors:publish`; framework fallbacks remain for apps that never publish
- Console-side exception rendering belongs to **M9** (console), not here
- Validation failures (M3) use the existing 422 envelope; M3 does **not** open the handler layer

## Milestones

### M0 — Skeleton — **complete**

- Repo/project `avalon`, installable distribution `avalon`
- Subpackage stubs: `framework`, `config`, `providers`, `http`, `routing`, `validation`, `grail`, `installer`, plus placeholders for `orm`, `caliburn`, `auth`
- Root `grail` script: `python grail version` works
- **`avalon new <name>`** scaffolds a Laravel-like app tree (incl. root `grail`, `bootstrap/app.py`, controllers, routes, config)
- **`python grail serve`** runs Uvicorn against `bootstrap.app:asgi` (M0 minimal FastAPI entry; Avalon HTTP kernel replaces this in M2)
- pytest harness + GitHub Actions CI (Python 3.11–3.13)
- Smoke plan: [`docs/SMOKE.md`](SMOKE.md); automated suite under `tests/smoke/`
- Coverage gate: **≥ 98%** on full `avalon` (`pytest-cov` in CI); **always aim for 100%**, especially on the package under the active milestone (Caliburn: `make test-cov-caliburn`).

### M1 — Application kernel — **complete**

- `Application.bootstrap()`: env → config → register providers → boot
- `.env` loader (`load_environment` / `env()`) and `ConfigRepository` + `config()`
- Service container: bind / singleton / instance / alias / resolve / `make` / constructor autowiring
- `ServiceProvider` + `FoundationServiceProvider`; `app.providers` from `config/app.py`
- Scaffolded apps boot the kernel from `bootstrap/app.py`
- Living example: [`examples/progress`](../examples/progress) (milestone board at `/progress`)
- Smoke: [`docs/SMOKE.md`](SMOKE.md) M1 section + `tests/smoke/test_m1_smoke.py`

### M2 — HTTP + routing — **complete**

- Router DSL: `Route.get/post/...`, nestable groups, prefixes, middleware aliases
- Controllers resolved from the container; async actions
- Middleware pipeline (`handle(request, next)`) with `config/http.py` defaults **and** Laravel 11-shaped registration in `bootstrap/app.py`: `Application.configure(...).with_middleware(...).create()` (`alias`, `web`/`api`/`group` append|prepend|replace, global `append`/`prepend`/`use`, **`trust_proxies` / `trust_hosts`**)
- `config/http.py` keeps empty group shells; app stacks, aliases, and proxy/host trust are registered in bootstrap (Progress demonstrates `demo.tag` this way)
- `HttpKernel` compiles Avalon routes onto FastAPI (engine stays hidden)
- **`Request` Laravel-parity input bag + controller capture** (see Decision above)
- `HttpException` JSON shape `{message, status, errors?}`, converted **inside** the pipeline so route middleware still decorates error responses
- **Route polarity:** `html()` + `Response` exported from `avalon.http`; scaffold ships HTML `routes/web.py` and JSON `routes/api.py`
- App bootstrap: `asgi = application.asgi` — **no FastAPI imports in app code**
- Smoke/regression: `tests/smoke/test_m2_smoke.py`, `tests/regression/test_m2_contracts.py`, `tests/test_m2_polarity.py`
- Living example: `/` + `/progress` render HTML; `/api/*` exhausts verbs, nested groups, Request bag, DI, exceptions

**Out of scope for M2 (unchanged):** production workers UX, `APP_BASE_PATH` mount, CSRF/CSP packs, `resource`/`view` routes, FormRequest, real sessions.

### M3 — Validation + DX — **complete**

- **`FormRequest`** on Pydantic v2: fields declared as annotations, schema built per subclass, `@field_validator` / `@model_validator` carried through
- Hooks: `authorize()` (false → 403), `prepare_for_validation()`, `passed_validation()`, `messages()`, `attributes()`, `validation_data()`
- Access: `data` (typed model), `validated(*keys)`, and proxying to the underlying `Request` for the full M2 input bag
- Kernel injects and validates before the action runs — invalid input never reaches controllers
- Laravel-shaped messages keyed by familiar rule names (`required`, `min`, `max`, `boolean`, `array`, `regex`, …), with string/collection size wording split as Laravel does
- Validation failures reuse the **locked 422 envelope** (`{message, status, errors}`) — M3 did **not** open the handler layer (that is M8)
- `python grail make:controller` / `make:middleware` / `make:provider` / `make:request` — nested namespaces, `__init__.py` creation, `--force`, duplicate + bad-name guards
- **URL generation:** `url()`, `asset()`, `redirect()`, `UrlGenerator` honoring `APP_URL` + `APP_BASE_PATH`; scaffolded apps and the living example use them for every link
- Living example: `POST /api/items` backed by `StoreItemRequest`
- Tests: `tests/test_m3_validation.py`, `test_m3_make.py`, `test_m3_urls.py`, `tests/smoke/test_m3_smoke.py`, `tests/regression/test_m3_contracts.py`

**Gate met:** example boots, routes, injects, validates, responds — no FastAPI imports in app code.

**Out of scope for M3:** exception handler layer + logging (M8), `route()` named-URL helper (post-M3 DX pass). ASGI mounting at `APP_BASE_PATH` is implemented on the HTTP kernel (see subpath decision).

### M4 — Localization (`avalon.translation`) — **complete**

Full Laravel localization parity before ORM/views/auth. See the decision above for the binding contract — M4 exhausts that contract, not a thin subset.

- `Translator` + `Lang` façade bound in the container; `__()` / `trans()` / `trans_choice()` exported from `avalon.translation`
- Catalog loading: `lang/<locale>/<file>.py` (nested dicts) + flat `lang/<locale>.json` (string-as-key); cached; `add_path` / `add_json_path` / `add_lines`
- Placeholders with Laravel case transforms (`:name` / `:Name` / `:NAME`); `:count` in choices
- Pluralization: pipe forms, interval forms (`{0}|[1,19]|[20,*]`), and **Babel CLDR** plural categories per locale
- Namespaces (`package::file.key`), vendor overrides (`lang/vendor/<package>/…`), `has` / `has_for_locale`, missing-key callback
- `APP_LOCALE` / `APP_FALLBACK_LOCALE`; `set_locale` / `get_locale` / `is_locale` — **request-scoped**
- `SetLocale` middleware (`Accept-Language` for `api`; explicit always wins)
- Localization helpers: `Number.format` / `percentage` / `currency` / `file_size` / `for_humans`; date locale follows app locale
- Tooling: `grail lang:publish`, `grail make:lang`, `grail lang:missing`
- **Retrofit:** `avalon.validation` messages resolve through the shipped `en` catalog (plus `auth` / `passwords` / `pagination` stubs); M3 422/403 envelope + `en` wording stay byte-identical
- Scaffold ships `lang/en/` + locale middleware; `avalon new` apps are translatable out of the box
- Living example: `/api/locale` answers in `en` / `sw` via `Accept-Language`

**Gate met:** dual-locale endpoint, CLI tooling, validation retrofit, coverage ≥ 95%.

### M5 — `avalon.orm` — **complete**

Full Eloquent parity — see the ORM decision above for the binding ladder. M5 exhausts it.

- Connections + `DB` façade + transactions (savepoint nesting); `config/database.py` (SQLite / PostgreSQL / MySQL+MariaDB / SQL Server + optional Oracle)
- `Model` base: casts, accessors/mutators, mass-assignment guard, dirty tracking, timestamps, serialization
- Query builder: complete `where` family (canonical `where("col", "=", val)`, two-arg `=` shortcut), joins, aggregates, chunking, `upsert`, `to_sql`
- All relationship types incl. through + polymorphic; eager loading, `with_count`, `where_has`
- `Collection` return type; `paginate` / `simple_paginate`
- Local + global scopes, soft deletes, model events + observers
- Schema builder over SQLAlchemy DDL; Python migrator (`make:model`, `make:migration` with name inference, `migrate` / `rollback` / `fresh` / `status`) — not Alembic revisions. Column-line modifiers include **`->index()`** / `->unique()` (and table-level `index` / `unique`)
- Seeders: `Seeder` call API, `WithoutModelEvents`, `make:seeder`, `db:seed` / `migrate --seed` / `migrate:fresh --seed`, scaffold `DatabaseSeeder` (factories deferred — **M24**)
- Living example: `GET /api/orm` feature tour; `/api/posts` / `/api/users` cover eager load, scopes, soft deletes, pivot roles, morph comments, pagination, upsert
- Feature docs: [`website/…/articulate/`](../website/src/content/docs/articulate/) + [`database/`](../website/src/content/docs/database/)

**Gate met:** models, relations, migrator, seeders, coverage ≥ 95%.

### M6 — Caliburn (`avalon.caliburn`)

**Full Blade parity** — see the Views decision. M6 exhausts that ladder; it is a major product surface (a new Python view engine), not a stopgap.

- Compile-to-Python + mtime/warm cache; `view()` / `ViewFactory` via provider (`avalon[caliburn]` extra may stay empty while Caliburn is core)
- Layout inheritance, includes, control flow, **components & slots**, stacks, custom directives
- Replace hand-built web HTML in the living example with `.cal.html` (including componentized UI where it pays off)
- **i18n (required):** `@lang` / `@choice` / `__()` wired to `avalon.translation`
- **Docs (required):** dedicated Starlight **Caliburn** section — thorough how-tos, not a single stub page
- Benchmark suite from day one; continue parity without blocking auth
- **Subpath:** asset helpers + smoke under `APP_BASE_PATH`
- XSS defaults: escaped `{{ }}` vs raw `{!! !!}`
- **Tooling:** `grail make:component` (anonymous `.cal.html` under `resources/views/components`)
- **Assets:** `asset()` / `@asset` + serve `public/` in `grail serve`. Default scaffold ships Vite + Tailwind (`package.json`, `resources/css|js`, → `public/build`). Progress may keep plain CSS/JS under `public/` for the living demo while still carrying the default Vite tree for scaffold baseline parity. Full `@vite` directive is a follow-up.

**Gate:** ladder exhausted, Caliburn docs section covers shipped surfaces, progress example is Caliburn-first, coverage **100%** on `avalon.caliburn` (statements + branches on the M6 test suite). Real `@csrf` / `@auth` / `@guest` token wiring waits on M7 sessions; `grail view:*` CLI waits on M9 console kernel (engine `cache_views` / `clear_cache` APIs ship now).

### M7 — `avalon.auth`

**Parity target:** Laravel’s [Authentication](https://laravel.com/docs/authentication) + [Hashing](https://laravel.com/docs/hashing) + [Passwords](https://laravel.com/docs/passwords) documented surfaces — exhaust inside M7, same rule as M4/M5/M6. A thin “session cookie + middleware alias” exit is **not** allowed.

**In scope (framework core):**

| Ladder rung | Contract |
| --- | --- |
| Hashing | `Hash.make` / `check` / `needs_rehash` / `is_hashed` (bcrypt default; config-driven) |
| Contracts | `Authenticatable`, `UserProvider`; Articulate model provider |
| Config | `config/auth.py` — defaults, guards, providers, passwords brokers |
| Session guard | `attempt` / `validate` / `login` / `logout` / `login_using_id` / `once` / `once_using_id` / remember-me |
| Token guard | Classic API token lookup via user provider (stateless `api` guard) |
| Helpers | `auth()` manager; retrieve user / `check` / `guest` / `id` / `guard(name)` |
| Middleware | `auth` (optional `:guard`), `guest`, `password.confirm`, HTTP Basic |
| Password confirm | Session timestamp + `password.confirm` middleware |
| Password broker | Reset tokens table/API, `send_reset_link` / `reset` (delivery pluggable until **M12**/**M13**) |
| Catalogs | Wire `lang/en/auth.py` + `passwords.py` through attempts / broker statuses |
| Rehash | Automatic rehash on login when `needs_rehash` |
| Docs | Starlight **Authentication**, **Hashing**, **Passwords** (+ Session/CSRF already in Basics) |
| Living example | Progress: password column, `attempt()` login, protected route, bearer/token demo |

**Explicitly deferred (not M7):**

| Item | Home |
| --- | --- |
| Starter-kit auth UI (Breeze-class scaffolds) | Starter kits |
| Sanctum / Passport / Socialite | First-party packages / Later |
| Authorization (Gates / Policies) | **M19** (Laravel’s separate Authorization docs) |
| Email verification | **M13** notifications (+ mail channel) |
| Real outbound reset mail | **M12** mail / **M13** notifications — broker + token API ships now |

**Gate:** ladder exhausted, Auth/Hashing/Passwords docs published, progress uses real credentials, coverage ≥ 98% (auth + hashing + passwords packages aim 100%).

**Status (M7):** Ladder shipped — session/CSRF/EncryptCookies; `Hash` (bcrypt + optional `argon2`/`argon2id`); session + token guards (`attempt`/`login`/`logout`/`once*`/`login_using_id`, remember-me **Set-Cookie**, rehash-on-login); `auth`/`guest`/`password.confirm`/`auth.basic`/`auth.start`; `Request.user()`; intended URL; auth events; `Password` broker (memory + optional DB table); catalogs; scaffold `config/auth.py` + `config/hashing.py`; Starlight Authentication/Hashing/Passwords; progress login + `/api/me`. **Deferred by design:** Sanctum/Passport/Socialite; Gates/Policies → **M19**; email verification → **M13**; outbound reset mail → **M12**/**M13**.

### M8 — Error handling (`avalon.exceptions` + `avalon.log`)

Turns M2's minimal kernel behavior into a real handler layer. See the decision above for the binding contract.

- `Handler` base in `avalon.exceptions`; app override at `app/Exceptions/Handler.py`, resolved from the container
- `report()` / `render()` split, `dont_report`, `reportable()` / `renderable()` hooks
- Per-exception `report()` / `render()` methods honored before the handler default
- **Polarity-aware rendering:** HTML for web, locked JSON envelope for api — **no** `Accept` flip
- `APP_DEBUG` web debug page (traceback, source excerpts, request/route context) with a test proving it is off when debug is false; api debug only widens `message`, never embeds a stack trace in JSON
- Production error views: `resources/views/errors/{status}.cal.html` + framework fallback; statuses at least `404` / `419` / `429` / `500` / `503`
- `python grail errors:publish [--bundle=default|tailwind|bootstrap] [--force]`; `avalon new` ships **default**; Tailwind/Bootstrap sets for kits / opt-in publish
- Logging slice: `config/logging.py`, channels (`stack`, `single`, `daily`, `stderr`), levels, context, `log()` helper
- Living example: a deliberate failure on a web route rendering HTML, the same failure on an api route rendering JSON

**Depends on:** M2 route polarity (done) and M6 Caliburn for error views. Do not start before M6 — HTML error pages without a view engine is exactly the placeholder trap.

**Status (M8):** Ladder shipped — `Handler` (`report`/`render`, hooks, `dont_report`); polarity-aware HTML vs JSON; unmatched-route path polarity; status mapping (`ModelNotFoundError` → 404, …); `APP_DEBUG` web debug page; production `errors/{status}` views + framework / Caliburn-off fallbacks; `errors:publish` (`default`/`tailwind`/`bootstrap`, CDN-free); `avalon.log` channels + `log().with_()` context; `lang/en/errors.py`; `ServiceUnavailableHttpException`; scaffold + progress `/boom` + `/api/explode`; smoke + Error Handling / Logging docs.

### M9 — Console + scheduler (`avalon.console`)

Grail today is a thin Typer entry (`version`, `serve`, `make:*`, `migrate`, …). M9 turns it into a Laravel-shaped **console kernel**.

- `Command` base: signature / help / `handle()`, IoC-resolved
- Command discovery: `app/Console/Commands`, `python grail list`, `python grail make:command`
- Framework commands stay in `avalon.console`; app commands register via provider or auto-discover
- Input / output helpers (arguments, options, tables, confirm) — exhaust the DX, not a stub Typer wrapper
- **Avalon Prompts** (`avalon.console.prompts`) — Laravel Prompts-class interactive UI: `text`, `textarea`, `password`, `number`, `confirm`, `select`, `multiselect`, `suggest`, `search`, `spin`, `progress`, `note`/`info`/`warning`/`error`/`alert`, with non-TTY / CI fallbacks; Command `ask` / `choice` / `secret` / `anticipate`
- **Scheduler:** `routes/console.py` or `app/Console/Kernel` schedule DSL (`daily`, `hourly`, `every_minute`, cron expressions)
- `python grail schedule:run` / `schedule:work` (long-running ticker) suitable for cron or a dedicated process
- Overlap / mutex for scheduled tasks (filesystem lock is enough until **M15** cache / **M16** Redis)
- Console-side rendering of uncaught exceptions, wired to the M8 handler
- **Interactive REPL (Tinker-class) — `python grail fiddle`** — user-friendly Python shell with the app booted (container, helpers, models, DB). Laravel parallel: `php artisan tinker`. Prefer **IPython** (`avalon[fiddle]` / `avalon[dev]`) with colored prompts + syntax highlighting; else ptpython; else Rich-enhanced fallback (never a bare undecorated `code.interact` without guidance). Boot `Application` once; pretty repr; history/completion when the preferred shell is available.
- Living example: at least one app command + one scheduled task + a smoke that the REPL boots and can resolve a model / run a trivial query

**Depends on:** solid Application boot (done); M8 for console exception rendering. Does **not** require queues — scheduled closures/commands run in-process; queue integration is M11. The REPL may land with M9 or as a fast follow once the console kernel exists — it must not be forgotten.

**Status (M9):** Ladder shipped — `Command` base + discovery (`app/console/commands`, `avalon.console.commands`); `grail list` / `make:command` / `inspire`; schedule DSL (`every_minute` / `hourly` / `daily` / cron) + `schedule:run` / `schedule:work` + filesystem mutex; console exceptions report through M8 Handler; **`grail fiddle`** REPL (IPython preferred → ptpython → Rich fallback); **Avalon Prompts** (`avalon.console.prompts` — Laravel Prompts-shaped `text`/`select`/`confirm`/`spin`/`progress` + Command `ask`/`choice`/`secret`/`anticipate`); **`dump()` / `dd()`** (`avalon.debug` — Rich CLI + HTML/JSON HTTP dump pages); progress `progress:hello` / `progress:prompts` + `/dd` · `/api/dd` + `routes/console.py`; smoke + docs.

### M10 — Filesystem (`avalon.filesystem`)

FlySystem-shaped **Storage** façade — app code never talks to raw `pathlib` for “disk” operations on the happy path.

- `Storage.disk("local")` / `Storage.put` / `get` / `exists` / `delete` / `copy` / `move` / `url` / `temporary_url` (where driver supports)
- Drivers: **local** (required), **S3-compatible** (optional extra), memory (tests)
- Config: `config/filesystems.py` — default disk, roots under `storage/app`, public disk + symlink story (`python grail storage:link`)
- Stream / large-file friendly APIs; visibility (`public` / `private`)
- Integrate with existing `Request` uploads (`UploadedFile` → `Storage`)
- Provider + `storage()` helper; smoke against local disk

**Depends on:** M2 request files (done). Natural prerequisite for queue failed-job payloads and **M12** mail attachments.

**Status (M10):** Ladder exhausted — `Storage` / `storage()` / disks (`local`, `public`, `memory`, S3 via `avalon[s3]`); real `read_stream` / `write_stream` on local; visibility (+ chmod best-effort); `config/filesystems.py`; `storage:link`; UploadedFile `store` / `store_as` + `put_file` / `put_file_async`; **`temporary_url` raises on local/memory** (S3-only, Laravel-honest); provider; progress + docs + tests.

### M11 — Queues + job workers (`avalon.queue`)

- `Job` base: `handle()`, `dispatch()`, delay, tries, backoff, timeout
- `ShouldQueue` vs sync dispatch; `dispatch_sync` escape hatch
- Queue connection drivers: **database** (after M5) and/or **Redis** (**M16** driver); **sync** driver for tests/dev default
- `python grail queue:work` / `queue:listen` / `queue:retry` / `queue:failed`
- Failed jobs table/store + `failed()` hook on Job; failures report through the **M8** handler
- Middleware / job pipeline (rate limit, unique jobs — subset, exhaust what you claim)
- Horizon-class dashboard is **out of scope**; process supervision is docs (systemd / Docker)
- Living example: dispatch from a controller or command; worker processes the job

**Depends on:** M5 for database queue; M8 for failure reporting; M9 for `queue:*` commands; M10 nice-to-have for job artifacts.

**Unblocks:** queued mailables (M12) and queued notifications (M13).

**Status (M11):** Ladder exhausted — `Job` / `ShouldQueue` / `dispatch` / `dispatch_sync`; **`timeout` enforced** via `asyncio.wait_for`; sync + database drivers; `queue:work` / `listen` / `failed` / `retry`; middleware + unique id; living demo `progress:demo` / `ProgressDigestJob`; tests + Queues docs.

### M12 — Mail (`avalon.mail`)

**Parity target:** Laravel’s [Mail](https://laravel.com/docs/mail) documented surface — `Mailable`, `Mail` façade, transports, Markdown mailables. A thin “SMTP wrapper” exit is **not** allowed.

**In scope (framework core):**

| Ladder rung | Contract |
| --- | --- |
| Config | `config/mail.py` — default mailer, from address, transport settings |
| Mailable | Class-based messages: `envelope` / `content` / `attachments` (Laravel 9+ shape) or exhaust an equivalent fluent API |
| Mailer | `Mail.to(...).send(Mailable)` / `cc` / `bcc` / `send` / `queue` (queue when M11 exists; sync always) |
| Transports | **log** + **array** (tests/dev) + **SMTP** (production baseline); optional extras later (SES, Mailgun, …) as drivers behind the same API |
| Markdown mail | Caliburn/Markdown templates under `resources/views/mail` (or agreed path); themeable components |
| Attachments | From paths / `Storage` disks (M10) / raw bytes |
| Assertions | Test helpers: assert sent / not sent / queued (array driver) |
| Docs | Starlight **Mail** (Digging Deeper) |
| Living example | Progress (or mail-focused demo): send a welcome / password-reset mailable via log or SMTP in `.env` |

**Explicitly deferred (not M12):**

| Item | Home |
| --- | --- |
| Notification channels / `Notifiable` | **M13** |
| Email verification UX | **M13** (+ auth) |
| Broadcast / Slack / SMS channels | **M26** / first-party extras |
| Full third-party ESP kit matrix | Optional extras after SMTP baseline |

**Depends on:** M6 Caliburn for Markdown/HTML mail views; M10 for attachment disks (soft — path attachments can ship earlier); M11 for `ShouldQueue` mailables (sync send ships without waiting on workers).

**Gate:** ladder exhausted, Mail docs published, array/log drivers green in CI, SMTP documented, coverage ≥ 98% on `avalon.mail` (aim 100%).

**Status (M12):** Ladder exhausted — `Mailable` (`envelope` / `content` / `attachments`); `ShouldQueue` honored on `send()` via serializable `SendQueuedMailable`; `Mail.to(…).send/queue`; log + array + SMTP; Markdown themes (`mail.themes.default` + builtin fallback) + `<x-mail.*>` components; Storage/path/bytes attachments; `MailAssertions`; living `WelcomeMail` via `progress:demo`; tests + Mail docs.

### M13 — Notifications (`avalon.notifications`)

**Parity target:** Laravel’s [Notifications](https://laravel.com/docs/notifications) documented surface — `Notifiable`, notification classes, channels, database notifications. Closes M7 deferrals that need outbound delivery.

**In scope (framework core):**

| Ladder rung | Contract |
| --- | --- |
| Notifiable | Mixin/trait on models: `notify` / `notify_now` / route notification for mail |
| Notification | Class with `via(notifiable)` + channel builders (`to_mail`, `to_database`, …) |
| Channels | **mail** (M12), **database** (notifications table + Articulate), **log/array** for tests |
| Queue | `ShouldQueue` notifications when M11 exists; sync always available |
| Database UI data | Stored payload for in-app notification lists (no full SPA required) |
| Auth wiring | Password-reset delivery via notification/mail; **email verification** (`MustVerifyEmail`-shaped) |
| Docs | Starlight **Notifications** (+ update Passwords / Authentication for real delivery) |
| Living example | Progress: reset-password notification + verified-email flow (or equivalent demo) |

**Explicitly deferred (not M13):**

| Item | Home |
| --- | --- |
| Broadcast / Slack / SMS / push | **M26** / first-party packages |
| Notification inbox SPA | Starter kits / app code |
| Marketing drip / bulk mail | Outside framework core |

**Depends on:** M12 Mail (mail channel); M5 ORM (database channel); M7 auth (verification + reset consumers); M11 for queued notifications (optional for sync).

**Gate:** ladder exhausted, Notifications docs published, mail + database channels tested, password-reset outbound no longer pluggable-only theater, coverage ≥ 98% on `avalon.notifications` (aim 100%).

**Status (M13):** Ladder exhausted — `Notifiable` / `Notification` / channels (mail/database/log/array); `ShouldQueue` via serializable `SendQueuedNotification` (no double-send); `MustVerifyEmail` + **signed** verification URLs + **`verified` middleware** + progress `/email/verify*` routes; `ResetPasswordNotification` as password-broker default; Authentication + Passwords docs updated; living `progress:demo` notify path; progress `User` is Notifiable; tests + Notifications docs.

### M14 — Helpers + Strings (`avalon.support`)

Laravel [Helpers](https://laravel.com/docs/helpers) + [Strings](https://laravel.com/docs/strings) parity on top of the shipped Support `Collection`.

- Global / module helpers mirroring Laravel’s helper catalog that Avalon does not already own (`abort_if`, `blank`, `filled`, `data_get` / `data_set`, `value`, `tap`, `with_`, `optional`, `retry`, `throw_if`, …) — exhaust what you claim; skip PHP-only relics
- `Str` / `Stringable` fluent string API (`avalon.support.Str`) — `of`, `camel`, `snake`, `slug`, `limit`, `contains`, `replace_*`, `uuid`, … Laravel Strings surface
- Docs: Starlight **Helpers** + **Strings**; Collections page stays the collection-only entry
- Living example / tests for the helper surface used by scaffolded apps

**Depends on:** Support Collections (done). Natural early Digging Deeper milestone — does not require M10–M13.

**Gate:** claimed helper + `Str` surface exhausted, docs published, coverage ≥ 98% on new modules.

**Status (M14):** Ladder exhausted — `Arr`, `Number`, `data_*` / misc helpers (`blank`, `tap`, `optional`, `retry`, `abort_if`, path helpers, …); `Str` / `Stringable` / `str_()`; Starlight Helpers + Strings; progress `progress:helpers`; tests + smoke.

### M15 — Cache (`avalon.cache`)

Laravel [Cache](https://laravel.com/docs/cache) store — first consumer of schedule mutex upgrades and queue unique locks.

- `Cache` façade: `get` / `put` / `forever` / `forget` / `flush` / `remember` / `remember_forever` / `add` / `pull` / `touch` / `many` / `put_many` / locks (`lock` / `block` / `restore_lock` / `flush_locks` / `without_overlapping`)
- Drivers: **array** (tests), **file**, **database** (M5); Redis driver lands with **M16**
- Atomic `add` on all stores; database locks via `cache_locks` table; file locks via `flock`
- Tags on **array** only (file/database raise — Laravel-honest); Redis tags in M16
- `config/cache.py`; `cache()` helper; `Cache.extend` for custom drivers
- Upgrade M9 schedule mutex to prefer cache locks when configured
- Docs: Starlight **Cache**

**Depends on:** M5 for database driver; M9 for scheduler consumer. Soft-depends on M10 for file paths under `storage/framework/cache`.

**Gate:** façade + array/file/database green; docs published; coverage ≥ 98%.

**Status (M15):** Ladder exhausted — `Cache` / `cache()`; array + file + database + null stores; atomic `add` / locks (`cache_locks`, file flock); tags on array only; `touch` / `restore_lock` / `flush_locks` / `extend`; schedule `without_overlapping` prefers cache locks; scaffold `config/cache.py`; progress `progress:cache`; Starlight Cache; tests + smoke.

### M16 — Redis (`avalon.redis` + drivers)

Laravel [Redis](https://laravel.com/docs/redis) connection manager and first-party drivers for session, cache, and queues.

- Redis connection / cluster config (`config/database.py` redis connections or `config/redis.py`)
- Drivers: **session** (M7 session stack), **cache** (M15), **queue** (M11) — opt-in via config; file/cookie/database remain defaults for local
- `Redis` façade for app-level get/set/pubsub primitives used by those drivers
- Docs: Starlight **Redis**; update Session / Cache / Queues pages for the Redis driver

**Depends on:** M7 session, M11 queues, M15 cache. Optional `avalon[redis]` extra.

**Gate:** at least one driver path proven end-to-end (cache or session); docs honest about extras; coverage ≥ 98% on Redis package.

**Status (M16):** Ladder exhausted — `Redis` / `redis()` façade; `config/redis.py`; `avalon[redis]` extra; Redis drivers for **cache** (tags + locks), **session**, and **queue**; Worker generalized beyond database; Starlight Redis; progress `progress:redis`; tests via FakeRedis (no server required in CI).

**Status (M17):** Ladder exhausted — `Crypt` / helpers; JSON-safe `encrypt`/`decrypt` (no pickle); `encrypt_string`/`decrypt_string`; `APP_PREVIOUS_KEYS` rotation; shared cipher with M7 cookie encrypt; `grail key:generate`; Starlight Encryption; progress `progress:encryption`.

### M18 — Events (`avalon.events`)

Application-level event dispatcher — distinct from Articulate **model** events (already shipped).

- `Event` / `dispatch` / `listen` / `subscribe`; queued listeners when M11 exists
- `EventServiceProvider`-shaped registration or `Event::listen` in providers
- Wildcard / class listeners; `ShouldBroadcast` hooks deferred to **M26**
- Docs: Starlight **Events** (Digging Deeper); Articulate model-events page stays separate

**Depends on:** Application container (done); M11 for queued listeners (sync always).

**Gate:** dispatcher + provider registration exhausted, docs published, coverage ≥ 98%.

### M19 — Authorization (`avalon.auth` Gates / Policies)

Laravel [Authorization](https://laravel.com/docs/authorization) — Gates and Policies (deferred from M7).

- `Gate::define` / `allows` / `denies` / `authorize` / `any` / `none`
- Policy classes + `make:policy`; auto-discovery; `Authorizable` on user
- Controller/`FormRequest` integration (`authorize` resource abilities)
- Caliburn `@can` / `@cannot` when views need them
- Docs: Starlight **Authorization** (Security sidebar)

**Depends on:** M7 auth (done); M6 for `@can` directives.

**Gate:** Gates + Policies exhausted, docs published, progress demo of a policy, coverage ≥ 98%.

### M20 — HTTP Client

Laravel [HTTP Client](https://laravel.com/docs/http-client) — outbound fluent HTTP for apps and package code.

- `Http.get/post/…`, fluent headers/auth/timeout, JSON helpers, retry, pool
- Fake / sequence assertions for tests
- Async-friendly under ASGI (httpx or equivalent behind the façade)
- Docs: Starlight **HTTP Client**

**Depends on:** nothing hard; natural after core HTTP stack is boring.

**Gate:** façade + fakes green in CI, docs published, coverage ≥ 98%.

### M21 — Processes

Laravel [Processes](https://laravel.com/docs/processes) — first-class subprocess DX.

- `Process::run` / `start` / `pool` / `concurrently`; timeouts; input/output; fake for tests
- Docs: Starlight **Processes**

**Depends on:** console/testing helpers nice-to-have; otherwise independent.

**Gate:** claimed surface exhausted, fakes work, docs published.

### M22 — Concurrency

Laravel [Concurrency](https://laravel.com/docs/concurrency) — run closures concurrently and collect results.

- `Concurrency::run([...])` (async tasks / process driver as appropriate under ASGI)
- Docs: Starlight **Concurrency**

**Depends on:** M21 Processes if process driver is claimed; otherwise asyncio-only driver first.

**Gate:** documented drivers work; docs published.

### M23 — API Resources + Serialization

Laravel [Eloquent API Resources](https://laravel.com/docs/eloquent-resources) + deeper [serialization](https://laravel.com/docs/eloquent-serialization) docs/DX.

- `JsonResource` / `ResourceCollection`; `to_array` / `with_` / `additional`; conditional attributes
- `make:resource`; wrap / pagination awareness
- Articulate serialization docs: `hidden` / `visible` / `appends` / `to_dict` / `to_json` / date serialization (code largely M5 — exhaust docs + any gaps)
- Docs: **API Resources** + Articulate **Serialization**

**Depends on:** M5 ORM (done); API route polarity (done).

**Gate:** Resources usable on `routes/api.py`, docs published, coverage ≥ 98%.

### M24 — Model factories

Eloquent/Laravel Factory parity — primary consumer is **seeders**.

- `Factory` base, `definition()` / states / sequences, `make:factory`, `Model.factory()`, `create` / `make` / `count` / relationships
- Wire `DatabaseSeeder` demos to factories the Laravel way
- Docs: Database **Factories** (+ seeding page update)

**Depends on:** M5 seeders (done). Homes after Articulate is boring in real apps.

**Gate:** factory → seeder path green in progress/example, docs published, coverage ≥ 98%.

### M25 — Articulate NoSQL / document stores

Bake **document stores into Articulate core** under the multi-store contract (see ORM decision above) — first driver **MongoDB**, same `avalon.orm` DX where semantics match.

- Connection store kinds in `config/database.py`; Mongo connection + `avalon[mongo]` extra (Motor/pymongo behind the driver — never in app signatures)
- Document `Model` path: collection naming, `_id` / key inference, casts, accessors/mutators, dirty tracking, soft deletes (where meaningful), model events/observers
- Query builder subset the driver can honor (`where` family, ordering, limit, aggregates that Mongo supports); honest errors for SQL-only APIs
- Relationships: references + embeds (document-native); do **not** fake SQL pivots/joins
- Schema story: collection indexes / setup commands — **not** SQL Blueprint theater mapped onto BSON
- Factories (M24) and seeders work against document models once M25 lands (or soft-depend: document factory support in this milestone)
- Living example: Progress (or dedicated demo) reading/writing a Mongo-backed model alongside SQL
- Docs: Database **NoSQL** / Articulate document-store pages; update Getting Started to show store kinds

**Depends on:** M5 SQL Articulate (done). Prefer after **M24** factories so seed/factory demos can cover both stores; may start design seams earlier without claiming exhaust.

**Gate:** Mongo driver exhausted end-to-end (config → model → query → tests → docs); SQL regressions still green; coverage ≥ 98% on new driver code (aim 100%). Other NoSQL engines are follow-on drivers under the same abstraction — not claimed unless exhausted here.

### M26 — Broadcasting

Laravel [Broadcasting](https://laravel.com/docs/broadcasting) — Echo-class / websocket fan-out (deferred from M13 notification channels).

- Broadcaster drivers (log/null + one real driver — Redis pub/sub or websocket bridge); `ShouldBroadcast` events
- Channel auth; client contract documented (Echo-shaped JS lives in starter kits)
- Docs: Starlight **Broadcasting**

**Depends on:** M18 Events; M16 Redis nice-to-have for Redis broadcaster.

**Gate:** at least null/log + one real path; docs published. Horizon-class UI out of scope.

### M27 — Search

Laravel Scout-class full-text search for Articulate models.

- `Searchable` model mixin; sync / queue indexing; driver abstraction (collection/array for tests; Meilisearch / Typesense / similar as extras)
- `grail scout:*` (or `search:*`) commands when useful
- Docs: Starlight **Search** / Scout equivalent

**Depends on:** M5 ORM; M11 for queued syncing (optional); document models (**M25**) should be searchable under the same mixin when honest.

**Gate:** one driver path + fakes; docs published. Heavy engines stay optional extras.

### M28 — Testing toolkit

Expand beyond the current pytest + smoke/regression baseline toward Laravel’s [Testing](https://laravel.com/docs/testing) map.

- HTTP tests: `AvalonTestCase` / async client helpers (`get`/`post`, assert status/json/session/auth)
- Console tests: `grail` command assertions (exit code, output)
- Mocking: façade fakes (Mail, Notification, Queue, Event, Http, Process) consolidated
- Browser tests: Playwright/Selenium-class optional extra — document honestly; not required in core CI
- Docs: Starlight **Testing** (+ HTTP / Console / Mocking subpages)

**Depends on:** surfaces being faked (M11–M13, M18, M20, M21). Can grow incrementally; this milestone exhausts the documented toolkit.

**Gate:** HTTP + console helpers used by framework tests themselves; docs published.

### M29 — Package development

Laravel [Package Development](https://laravel.com/docs/packages) guidelines for first-party and community packages.

- Service provider discovery / scaffolding; `lang` / `config` / `views` publish tags
- Naming, extras, testing expectations; `avalon` namespace vs third-party prefixes
- Docs: Starlight **Package Development** (Packages / Prologue-adjacent)
- Optional: `grail make:package` stub — only if it earns its keep

**Depends on:** providers + lang namespaces (done); Caliburn/view publish patterns useful.

**Gate:** guidelines published and followed by at least one in-repo optional package or documented example.

### Later (still deferred)

- Additional NoSQL engines beyond Mongo (Cosmos API, Dynamo-shaped, …) — same M25 store abstraction; exhaust per driver when demanded
- Sanctum / Passport / Socialite (first-party packages)
- Starter kits (web kit vs API kit reflecting route polarity)
- Full Caliburn advanced parity (ongoing on M6 track)
- Router DX sugar: `head`, `redirect`, `fallback`, `route()`, then `resource` / `apiResource`
- Default security-headers + CORS middleware pack (post-M3 hardening; before or with M7 web stack — land when ready)
- Production docs / optional `grail serve --workers`
- **Docs site:** major-version switching + **Prologue** (changelogs, upgrade guides, release notes) — see Documentation site decision
- **Docs track (may land anytime):** Localization Starlight page (M4 code done); Articulate **Mutators & Casts** dedicated how-to (M5 code done)
- Rate limiting middleware (pairs with cache locks once M15 exists)
- Notification inbox SPA / marketing drip (outside framework core)

## Quality bar for “solid core”

- Type hints + tests per subpackage boundary
- Canonical `examples/api` updated every core milestone
- Docs per milestone: mental model + engine mapping in the Starlight site [`website/`](../website/) (write the page when the feature ships; `PLAN.md` stays the contract)
- Stable `avalon.*` imports; no Starlette/FastAPI types in happy-path app code
- Caliburn: golden fixtures + render benchmarks with regression guards
- **Coverage ≥ 98%** on `avalon` (CI fail-under on full suite; smoke runs without coverage). **Aim for 100%** always; milestone packages should hit 100% when practical (`make test-cov-caliburn` for M6).
- Milestone smoke + regression contracts (see [`SMOKE.md`](SMOKE.md)); `make smoke` / `make regression` / `make test-cov`

## Next implementation focus

**M17 Encryption gate met** — Crypt + JSON-safe encrypt + previous keys + shared cookie cipher. **Next: M18** Events when ready. Roadmap continues **M18–M29**.

**Docs (anytime):** Localization page (M4 code done); Mutators & Casts Articulate how-to (M5 code done).
