# Almasix — Canonical Plan

> **Status:** Binding. This document is the source of truth for architecture and milestones.
> Change it deliberately (PR / explicit decision), not casually mid-implementation.
> Last aligned: 2026-09-08 (M0–M20 complete, **M5 Articulate ORM** included now that M42 and
> M43 closed its query builder and schema layer; exhaust milestones M30/M31, M40–M43 and
> M49/M50 landed; **M44 — multi-engine database CI** is next).

## Working identity

- **Project / repo / distribution:** `almasix` (PyPI: `almasix`)
- **Import root:** `almasix` with intentional **subpackages**
- **CLIs (Laravel parallel):**
  - **`almasix new <app>`** — installer / project creator (like `laravel new`) — `almasix.installer`
  - **`python smith …`** — in-app commands via a root `smith` script (like `php artisan …`) — `almasix.smith`
  - Do **not** use Smith for project creation; do **not** use `almasix` for day-to-day app commands
- **HTTP engine:** FastAPI on Starlette (ASGI) — hidden behind Almasix’s programming model, with an escape hatch to the underlying FastAPI app for advanced cases
- **Validation / OpenAPI:** Pydantic v2 via Form Request–style classes
- **Views:** **Prism** (`almasix.prism`) — Blade-familiar syntax, featherweight render path, templates as **`.prism.html`**
- **Theme:** Lapidary naming for products/tools — the project is *almasi* (Swahili, “diamond”), cut by `smith`, viewed through `Prism`, inspected with `loupe`; keep public APIs Laravel-familiar (`Route`, `Controller`, `Middleware`, `config()`, `@extends`)
- **App layout naming:** Python snake_case packages/modules (`app/models/post.py`); PascalCase **classes** and Laravel-shaped directory *roles* (`models`, `http/controllers`). See [Directory Structure](../website/src/content/docs/structure.md).

## Design picture (target DX)

Developers create apps with `almasix new`, then run `python smith …` inside the app (controllers, providers, `routes/`, `config/`). Almasix boots a service container, registers providers, compiles routes into FastAPI, and serves via Uvicorn. FastAPI/Starlette remain implementation details of the HTTP kernel. Views compile Prism templates (`.prism.html`) to fast Python callables.

```mermaid
flowchart LR
  subgraph appDev [App_code]
    Routes[routes/web_and_api]
    Controllers[Controllers]
    Providers[Providers]
    Models[Models]
    Commands[Console_commands]
    Jobs[Jobs]
    PrismTemplates[prism.html_templates]
  end

  subgraph almasixPkg [almasix]
    Installer[almasix_new_CLI]
    Smith[python_smith_CLI]
    Framework[almasix.framework]
    Http[almasix.http]
    Routing[almasix.routing]
    ProvidersPkg[almasix.providers]
    Console[almasix.console]
    Filesystem[almasix.filesystem]
    Queue[almasix.queue]
    Orm[almasix.orm]
    Prism[almasix.prism]
  end

  subgraph engine [Engine]
    FastAPI[FastAPI]
    SA[SQLAlchemy_2]
    Workers[queue_workers]
  end

  Installer -.->|scaffolds_app_with_smith_script| Smith
  Smith --> Framework
  Smith --> Console
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
  PrismTemplates --> Prism
  Http --> Prism
```

## Package layout

```text
almasix/
  pyproject.toml
  src/almasix/
    framework/                 # Application, container, boot lifecycle
    config/                    # config repository, env
    providers/                 # core service providers + Provider base
    http/                      # kernel, request, response, middleware, controllers (+ M23 API Resources)
    routing/                   # Route DSL → FastAPI bridge
    validation/                # FormRequest
    translation/               # M4 — translator, plurals, Number, lang tooling
    smith/                     # in-app CLI entry (python smith …)
    exceptions/                # M8 — handler, debug page, error rendering
    log/                       # M8 — channels, log()
    console/                   # M9 — commands; M31 — scheduling
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
    client/                    # M20 — outbound HTTP client (inbound HTTP stays in http/)
    process/                   # M21 — Laravel Processes parity
    concurrency/               # M22 — concurrent closures / pools
    scout/                     # M27 — search (Scout parity)
    broadcasting/              # M26 — Echo-class fan-out
    testing/                   # M28 — TestCase, client, assertions, fakes, time
    installer/                 # almasix new …
    orm/                       # M5 (+ M24 factories, M25 NoSQL/document stores)
    prism/                  # M6 — optional for API apps
    session/                   # M7 — session, CSRF, cookie encrypt
  tests/
  examples/
  docs/
```

**Import examples:**

- `from almasix.framework import Application`
- `from almasix.routing import Route`
- `from almasix.http import Controller, Middleware`
- `from almasix.providers import ServiceProvider`
- `from almasix.validation import FormRequest`
- `from almasix.translation import __, trans, trans_choice, Number, Lang`
- `from almasix.orm import Model`
- later: `from almasix.prism import ViewFactory`
- later: `from almasix.filesystem import Storage`
- later: `from almasix.queue import Job, dispatch`
- later: `from almasix.mail import Mail, Mailable`
- later: `from almasix.notifications import notify, Notifiable`
- later: `from almasix.support import collect, Str`  # Helpers/Str expand in M14
- later: `from almasix.cache import Cache`
- later: `from almasix.encryption import Crypt`
- later: `from almasix.events import Event, dispatch as event`
- `from almasix.auth import Gate, Policy`  # M19
- `from almasix.client import Http`  # M20
- later: `from almasix.process import Process`
- later: `from almasix.concurrency import Concurrency`
- `from almasix.exceptions import Handler`
- `from almasix.log import log`
- `from almasix.console import Command, schedule`

### Subpackage boundaries

| Subpackage | Responsibility |
| --- | --- |
| `almasix.framework` | Application, IoC container, boot |
| `almasix.config` | `.env`, config files, `config()` |
| `almasix.providers` | Provider base + framework providers |
| `almasix.http` | Kernel, request/response, middleware, base controller |
| `almasix.routing` | Route definitions, groups, compiling onto FastAPI |
| `almasix.validation` | FormRequest / validation errors |
| `almasix.translation` | Translator, `lang/` catalogs, `__()` / `trans()` / `trans_choice()`, namespaces, Number/date helpers, locale resolution (M4) |
| `almasix.smith` | In-app CLI entrypoint (`python smith …`) — thin Typer surface over console kernel |
| `almasix.exceptions` | Handler (`report`/`render`), debug page, error views (M8) — distinct from `almasix.http.exceptions`, which holds the `HttpException` classes |
| `almasix.log` | Log channels + `log()` helper (M8) |
| `almasix.console` | Command base, discovery, scheduler (M9) |
| `almasix.filesystem` | Disks, Storage façade, FlySystem-shaped drivers (M10) |
| `almasix.queue` | Jobs, queues, workers, failed-job handling (M11) |
| `almasix.mail` | Mailable, Mailer, transports, Markdown mail (M12) |
| `almasix.notifications` | Notifiable, notification channels, database notifications (M13) |
| `almasix.support` | Support `Collection` (shipped); Laravel Helpers + `Str` (M14) |
| `almasix.cache` | Cache store + drivers (M15) |
| `almasix.redis` | Redis connection manager + drivers for cache/session/queue (M16) |
| `almasix.encryption` | `Crypt` façade — encrypt/decrypt/serialize (M17); cookie encrypt already under `almasix.session` (M7) |
| `almasix.events` | Application event dispatcher / listeners / subscribers (M18) |
| `almasix.client` | Outbound HTTP client — `Http` façade, fakes, retry, pool (M20) |
| `almasix.installer` | Installer CLI (`almasix new`) |
| `almasix.orm` | Eloquent-like ORM (M5); model factories (M24); NoSQL / document-store drivers (M25) |
| `almasix.prism` | Prism compiler/runtime (M6) |
| `almasix.auth` | Guards, middleware (M7); Gates / Policies (M19) |

## Ecosystem growth

Start as **one installable `almasix`**. When Prism, kits, filesystem drivers, or queues get large:

1. **Same repo, optional extras** — e.g. `pip install almasix[prism]`, or
2. **Monorepo of distributions** still under the `almasix.*` namespace, plus starter-kit packages

Do **not** rename the project to `almasix_framework`. “Framework” is the `almasix.framework` subpackage.

**Distribution name (settled 2026-09-08):** the *import* namespace and the *distribution* name are both `almasix`, so `pip install almasix` gives app code `import almasix` with no split of the kind `python-dotenv`/`dotenv` needs. This was an open constraint only while the project was called Avalon: `avalon` on PyPI is taken by an unrelated placeholder (Development Status :: 1 - Planning). The rename dissolved it — `almasix` was unregistered — so M38 no longer has a name to choose.

**Rules:**

- Core happy path must not require Prism; API apps never import `almasix.prism`
- `almasix.prism` stays framework-light and dependency-thin; integrate via a view provider
- Starter kits and heavy subsystems stay out of the default import surface
- App code uses `almasix.*` only — no FastAPI imports on the happy path

## Decision: ORM (Eloquent-like)

**Chosen approach:** Eloquent-shaped **Active Record + Query Builder API** as `almasix.orm`, built on **SQLAlchemy 2.0 Core (async-first)**.

**Parity target:** full Eloquent parity — models, query builder, every relationship type, eager loading, collections, casts, accessors/mutators, scopes, soft deletes, events/observers, pagination, transactions, and migrations. **M5 shipped the ladder for all of these; the 2026-09-08 audit against the Laravel Database + Eloquent sections found the surface short of exhaust, so M40–M44 finish the contract.**

**Core over ORM (binding):** Almasix uses SQLAlchemy **Core** (expression language, dialects, pooling, async engine) and implements Active Record itself. SQLAlchemy's declarative/Session unit-of-work is deliberately **not** used — it contradicts Active Record semantics (identity map, flush ordering, detached instances) and would leak through the DX. This keeps `almasix.orm` in control of the model lifecycle.

**Async-first (binding):** Every query/persistence operation is awaited, because Almasix runs on ASGI:

```python
user = await User.query().where("email", email).first()
posts = await Post.query().with_("author", "comments").find(1)
published = await user.posts().where("published", True).get()
```

Sync Eloquent-style calls are **not** offered — a hidden sync bridge under async is a footgun, not DX.

**Internal rule:** App code depends on `almasix.orm`, not SQLAlchemy — except documented escape hatches (`DB.raw`, `DB.connection().execute`).

### Decision: Articulate multi-store (SQL + NoSQL) — binding for M25

M5 shipped the **SQL** Eloquent ladder on SQLAlchemy Core (exhaust scheduled as **M40–M44** after the 2026-09-08 audit). **NoSQL is not a second ORM and not a forever-Later extra** — it is a scheduled Articulate core track (**M25**) so document stores share the same Active Record mental model where semantics match, without pretending every SQL feature exists on Mongo.

**Why bake into Articulate (not a satellite package):** a bolt-on `almasix.mongo` that reimplements models/collections/events will fork the DX and force apps to learn two ORMs. Queuing NoSQL as Articulate work forces the connection/model boundary to stay honest while SQL remains the default happy path.

**Contract (binding when M25 lands; design constraint from now):**

| Concern | Rule |
| --- | --- |
| Package home | `almasix.orm` — same `Model` / `DB` / `Collection` import root; store-specific code behind connection drivers |
| Default | SQL connections stay the scaffold default; NoSQL is opt-in via `config/database.py` + extras (`almasix[mongo]`, …) |
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

1. **Major-version docs** — publish and switch among major Almasix versions (e.g. `1.x` / `2.x`) from the docs site, Laravel-style. Exact mechanics TBD (Starlight versioning, separate versioned content trees, or a thin version switcher); the requirement is that readers can open docs for the major they run.
2. **Prologue** — a top-level sidebar group (Laravel “Prologue”) holding **Release Notes / Changelog**, **Upgrade Guide**, and related orientation pages, versioned with the docs set above.
3. Changelogs and upgrade guides are **first-class docs content**, not only GitHub Releases prose.
4. **The Basics** — Laravel’s “The Basics” sidebar is the reader’s mental map of the HTTP stack. Almasix must mirror that map (Almasix names where they differ). Empty Basics (only Middleware) is a **docs bug**, not a product gap for most of those topics.

Do not invent a second docs engine; extend the Starlight site.

### The Basics — Laravel map → Almasix (binding)

Mirror Laravel’s Basics **order and coverage**. Deep Prism how-tos stay in the **Prism** sidebar (like Laravel’s separate Blade section); Basics **Views** is the short entry + pointer.

| Laravel Basics | Almasix docs slug (target) | Code status | Docs action |
| --- | --- | --- | --- |
| Routing | `routing` | **Shipped (M2)** — `Route` DSL, groups, polarity | **Done** |
| Middleware | `middleware` | **Shipped (M2)** | **Done** |
| CSRF Protection | `csrf` | **Shipped (M7 foundation)** — `VerifyCsrfToken` + `@csrf` | **Done** |
| Controllers | `controllers` | **Shipped (M2/M3)** — base `Controller`, `make:controller`, DI | **Done** |
| Requests | `requests` | **Shipped (M2)** — `Request` bag | **Done** |
| Responses | `responses` | **Shipped (M2)** — `Response`, `html()`, JSON polarity | **Done** |
| Views | `views` | **Shipped (M6)** — `view()` / `ViewFactory` | **Done** — overview + link to Prism |
| Blade Templates | *(Prism section)* | **Shipped (M6)** | **Done** as Prism group (not duplicated under Basics) |
| Asset Bundling | `asset-bundling` | **Partial (M6)** — `asset()` / `@asset` + `public/` on `smith serve`; default `almasix new` ships **Vite + Tailwind** → `public/build`; Python core stays Node-free; starter kits may replace/extend | **Partial** — default scaffold + docs; full `@vite` helper follow-up |
| URL Generation | `urls` | **Partial (M3)** — `url()`, `asset()`, `redirect()`; named `route()` = **M33** | **Update with M33** |
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

Prism remains its own top-level group (Blade equivalent). Do **not** put the full Prism tutorial under Basics.

**Gate before starting M7 implementation:** Basics pages for shipped surfaces are published and linked in `website/astro.config.mjs` (**met**). Expand CSRF / Session / Logging placeholders when those milestones land — not fake APIs.

### Digging Deeper — scheduled surfaces (binding when milestones land)

Laravel’s Digging Deeper / Security / Packages clusters map onto Almasix as follows. Starlight sidebars grow when each surface ships — do not stub fake APIs ahead of the milestones.

| Laravel | Almasix docs slug (target) | Milestone | Docs action |
| --- | --- | --- | --- |
| Collections | `collections` | Support Collections, **M49** | **Done** — 155/155 methods, lazy collections, a section per method |
| Localization | `localization` | **M4** (code **Done**) | **Docs gap** — write Starlight Localization page (code already exhausted) |
| Helpers | `helpers` | **M14**, **M50** | **Done** — `Arr` 59, `Number` 20, the global helpers, a section per method |
| Strings | `strings` | **M14**, **M50** | **Done** — `Str` 91, `Stringable` 134 by delegation, a section per method |
| Cache | `cache` | **M15** | Shipped |
| Redis | `redis` | **Done (M16)** | Redis page + Cache/Session/Queues updates |
| Encryption | `encryption` | **M17** | `Crypt` façade, JSON-safe encrypt, `APP_PREVIOUS_KEYS`, `key:generate` |
| Events | `events` | **M18** | Write when app event dispatcher ships (model events already in Articulate) |
| Broadcasting | `broadcasting` | **M26** | Shipped |
| Authorization | `authorization` | **M19** | Write when Gates/Policies ship |
| HTTP Client | `http-client` | **M20** | Shipped |
| Processes | `processes` | **M21** | Write when Processes ship |
| Concurrency | `concurrency` | **M22** | Write when Concurrency ships |
| Eloquent: Mutators & Casting | `articulate/casts` | **Done (M40)** | Page published |
| Eloquent: Serialization | `articulate/serialization` | **Done (M40)** | Page published; links out to API Resources |
| Eloquent: API Resources | `api-resources` | **Done (M23)** | Page published |
| Eloquent: Factories | `database/factories` | **Done (M24)** | Page published |
| MongoDB / NoSQL | `articulate/documents` (+ Database Getting Started) | **Done (M25)** | Page published — core Articulate multi-store, not a satellite ORM |
| Scout / Search | `search` | **Done (M27)** | Page published |
| Queues | `queues` | **M11** | Write when queues ship |
| Mail | `mail` | **M12** | Write when mail ships |
| Notifications | `notifications` | **M13** | Write when notifications ship |
| Testing | `testing` (+ HTTP / Console / Database / Mocking subpages) | **Done (M28)** | Pages published |
| Packages | `packages` | **M29** | Write package-dev guidelines when that milestone lands |

Starlight **Digging Deeper** / **Security** / **Database** / **Packages** sidebars grow with those pages.

## Decision: Views — Prism

Prism is a **first-class view engine for Python**, not a thin wrapper around Jinja or FastAPI templates. **M6 exhausts full Laravel Blade parity** for the documented surface — the same exhaust rule as Articulate and localization. A partial “MVP forever” exit is not allowed.

| Item | Choice |
| --- | --- |
| Product name | Prism |
| Package | `almasix.prism` |
| Template extension | **`.prism.html`** |
| Inline code | **`@python` / `@endpython` only** (no freeform Python embedding) |
| DX north star | **Full Blade parity** — layouts, inheritance, components, slots, directives |
| Performance north star | **Featherweight** — first-class constraint |
| Docs | **Own Starlight section** (`website/…/prism/`) — thorough, Laravel Blade–shaped; write pages as surfaces ship |

Logic belongs in controllers, view models, and composers. `@python` is an escape hatch, not the default style.

### Parity target (binding)

Match Blade’s mental model end-to-end for app authors:

1. **Echo & comments** — `{{ }}` (escaped), `{!! !!}` (raw), `{{-- --}}`
2. **Layout inheritance** — `@extends`, `@section` / `@endsection` / `@show`, `@yield`, `@parent`, `@include` / `@includeIf` / `@includeWhen` / `@each`
3. **Control flow** — `@if` / `@elseif` / `@else` / `@unless` / `@isset` / `@empty` / `@auth` / `@guest` (auth wired when M7 exists; stubs/no-ops until then where needed), `@for` / `@foreach` / `@forelse` / `@while`, `@php` → **`@python` / `@endpython`**
4. **Components & slots** — class-based and anonymous components, `<x-name>` / `@component`, **slots** (`@slot`, `$slot`, named slots), attribute bags (`$attributes`), `@props`, `@aware`
5. **Stacks** — `@push` / `@prepend` / `@stack` / `@once`
6. **Framework directives** — `@csrf`, `@error`, `@lang` / `@choice` / `__()`, `@vite`-class asset helpers as `asset()` / `@asset` (subpath-aware from day one). **No Node dependency in Python core** — M6 owns URL helpers + `public/` serving for `smith serve`. Default `almasix new` (no starter kit) ships **Vite + Tailwind** scaffolding that emits into `public/build/`. Starter kits may replace or extend that toolchain. A first-class Prism `@vite` / hot-file helper is a follow-up on top of `asset()`.
7. **Extensibility** — `Engine.directive(...)` / service-provider registration for **custom `@directive`s**; app-owned Blade-style component libraries under `resources/views/components`
8. **Tooling** — `view()`, `ViewFactory`, compiled view cache, `smith view:clear` / `view:cache` when the console kernel can host them (M9); until then engine APIs + tests

**Rules:**

- Compile ahead, render thin — no re-lex/parse on the request hot path.
- XSS defaults match Blade: escape by default; raw is explicit.
- Prism templates are Almasix’s own (`.prism.html`), not “Jinja with Blade lipstick.”
- Do not claim M6 complete until the parity ladder below is exhausted **and** the Prism docs section covers it for app developers.

### Performance principles (non-negotiable)

- **Compile ahead, render thin** — no re-lex/parse on the request path
- **Aggressive compiled-cache** — mtime invalidate in dev; warm cache in prod
- **Minimal runtime** — thin dependency graph on the hot path
- **Zero-cost unused features**
- **Benchmark from day one** — echo, layout+sections, foreach, components; regression guards
- **Compare honestly** — Prism vs Jinja2 on shared fixtures

### Iteration ladder (exhaust inside M6)

1. **Layouts & echo:** `{{ }}`, `{!! !!}`, `@extends` / `@section` / `@yield` / `@parent`, `@include*` / `@each`, `{{-- --}}` — **shipped (advanced include variants)**
2. **Control flow:** `@if` family, `@isset` / `@empty(expr)`, `@foreach` / `@forelse` / `@for` / `@while`, `@auth` / `@guest` stubs, `@python` — **shipped**
3. **Components & slots:** `@component` / `<x-*>`, named + default slots, `<x-slot>`, attribute bags, `@props`, `@aware`, class-based `Component`, nested components
4. **Stacks + framework directives:** `@push` / `@stack`, `@lang` / `@choice` / `__()`, `@csrf` / `@error` / `@asset` stubs, asset helpers — **shipped (advanced surfaces)**
5. **Advanced:** composers, creators, fragment `@cache`, custom `Engine.directive`, `cache_views` / `clear_cache` — **shipped**

### Documentation (binding)

Ship a dedicated **Prism** sidebar group (peer to Articulate / Database), Laravel Blade–shaped topics, for example:

- Getting Started / Rendering Views
- Layouts & Inheritance
- Components & Slots
- Control Structures
- Including Subviews
- Stacks & Custom Directives
- Localization in views (`@lang` / `__`)

Pages land as each ladder rung ships — do not wait for M6 close to start the section.
## Decision: Scope discipline

Bite-sized milestones. **No** queues, notifications, scheduler, or mail until the **HTTP + validation + i18n + ORM + views + auth** core path is boring and tested (through M7). Seeders ship with M5 ORM; **model factories follow at M24**; **Articulate NoSQL / document stores at M25** (multi-store core — see ORM decision). Prism is its own track after the core gate. Error handling, console (incl. a Tinker-class REPL), filesystem, queues, **mail**, and **notifications** are sketched as **M8–M13**; Digging Deeper + Articulate follow-ons (helpers through packages, including NoSQL) are sketched as **M14–M29** so the roadmap is honest — they are not next work until their predecessors land. Multi-version docs + Prologue stay on the docs track (see Documentation site decision). **Localization docs** and **Articulate Mutators/Casts docs** are docs-track follow-ups on already-shipped M4/M5 code — they may land before M14.

**Localization is the one deliberate exception to “defer until needed.”** It sits at M4 because retrofitting translations across four message-producing layers costs far more than building them translatable. M4 exhausts **full Laravel localization parity** (not a thin core) — see the localization decision.

**Exhaust means full parity within the milestone’s declared scope.** Do not ship thin placeholders that claim a feature is done. Iterate inside the milestone (API + tests + living example) until the Laravel/Adonis-class DX for that slice is real, then move on. “Optional if light” / partial façades are not an exit criteria.

## Decision: Support Collections (`almasix.support`)

Laravel’s [`Illuminate\Support\Collection`](https://laravel.com/docs/collections) is **not** Eloquent’s model collection. Articulate already returns an Eloquent-shaped `Collection` from multi-row reads; Almasix also ships a first-class **Support** collection for general list/map work — `collect()` + fluent chains — matching Laravel’s Collections docs.

| Concern | Contract |
| --- | --- |
| Package | `almasix.support` — `Collection`, `collect()`, class helpers (`times`, `range`, `wrap`, `unwrap`, `make`) |
| Keys | Ordered-map semantics (list → contiguous int keys; dict keeps keys) |
| Returns | Transformers return **new** instances; `push` / `put` / `pop` / `pull` / `transform` match Laravel mutability |
| Macros | `Collection.macro(name, callback)` |
| Eloquent | `almasix.orm.collection.Collection` **extends** Support `Collection` (`load` / `load_missing` / `model_keys`) |
| Lazy | `LazyCollection` deferred until a streaming consumer needs it |
| Docs | Starlight **Collections** page (Support) + pointer from Articulate |

**Gate:** eager `Collection` exhausts the Laravel “Available Methods” list (skip Lazy / `dd` / `dump`); tests + docs green; Articulate regressions still pass. Can ship alongside M7 — does not block auth exhaust.

**Status (Collections):** Support `Collection` + `collect()` shipped — method surface (incl. `splice`, `multiply`, `reduce_spread`, assoc/using diffs & intersects, `to_pretty_json` / `from_json`), key-preserving filters, macros, Starlight **Collections** docs, `tests/test_support_collection.py`. Articulate `orm.Collection` extends Support.

**Correction (2026-09-08 audit):** the method surface is close but not closed, and the docs claim was too generous. 149 of the 155 methods on Laravel's Method Listing exist; `average`, `dd`, `dump`, and `lazy` do not. `LazyCollection` and higher-order messages (`collection.each.method()`) were never built, so Laravel's entire Lazy Collections section — including the `Enumerable` contract, `take_until_timeout`, `tap_each`, `throttle`, `remember`, and `with_heartbeat` — has no counterpart. The docs are the larger gap: Laravel gives each of the 155 methods its own section with an explanation and a runnable example (4,390 lines); Almasix's page is 140 lines built around a method-surface table. **M49** closes both.

## Decision: Production serving (ASGI)

Almasix apps are **plain ASGI**. There is no proprietary production server.

| Environment | How |
| --- | --- |
| Local | `python smith serve` → Uvicorn on `bootstrap.app:asgi` (dev reload; port walk 3000–3099) |
| Production | Uvicorn (or Gunicorn + Uvicorn workers / Hypercorn) on the same ASGI import path, behind a reverse proxy (Caddy / Nginx / Traefik) for TLS, compression, and optional static files |

**Rules:**

- App code never imports the process server; Smith/`uvicorn` are entrypoints only
- Production docs show workers + proxy; optional later: `python smith serve --workers N` (not required for M3)
- Static/asset CDN remains outside the Python process when possible; Almasix still generates correct public URLs (see subpath)

## Decision: Subpath hosting (first-class)

Laravel’s common failure mode — apps under `/apps/foo` with broken absolute `/…` assets and redirects — is **out of scope as a “proxy only” problem**. Almasix treats the public mount path as framework config.

| Config | Role |
| --- | --- |
| `APP_URL` | Canonical public origin (scheme + host[+port]), e.g. `https://example.com` |
| `APP_BASE_PATH` | Public path prefix, e.g. `/apps/foo` (empty or `/` = site root) |

**Contract (binding):**

1. **URL helpers** (`url()`, `route()`, `redirect()`, asset helpers) always honor `APP_BASE_PATH`
2. **Router / ASGI** either compile routes under the prefix or mount the ASGI app at it — one mechanism, documented; no double-prefix bugs
3. **Trusted proxies** (`X-Forwarded-Proto` / `Host` / `Prefix` as configured) so generated URLs match the public edge
4. **Prism asset helpers** (M6) must be prefix-aware from day one — never bake root-absolute asset paths that ignore `APP_BASE_PATH`

**Milestone homes:** design locked here; **M3 shipped URL generation** (`url()` / `asset()` / `redirect()`). **ASGI mount at `APP_BASE_PATH` ships with the HTTP kernel** — `smith serve` serves the app under the prefix and redirects `/` → `{base}/`. Prism asset helpers (M6) must stay prefix-aware; do not regress the mount.

## Decision: Route files — web vs api

Scaffolded apps ship **`routes/web.py`** and **`routes/api.py`**. They are not interchangeable dumps of the same handlers.

| File | Audience | Response | State | Middleware intent |
| --- | --- | --- | --- | --- |
| `routes/web.py` | Browsers | **HTML** (`text/html`) | **Stateful** (cookies / session once M7 exists) | Future `web` group: session, cookie encryption, CSRF |
| `routes/api.py` | Machines / SPAs / clients | **JSON** (`application/json`) | **Stateless** | Future `api` group: no session/CSRF; auth via token/bearer |

**Contract (binding; shipped in M2):**

1. Controllers registered in `web.py` return HTML (string / `html()` helper / later Prism `view()`). Do **not** default web routes to JSON dicts.
2. Controllers registered in `api.py` return JSON (dict/list / `json()`). Do **not** return HTML from API routes.
3. Framework does **not** auto-negotiate content type from `Accept` to paper over mixing the two files — put the route in the right file.
4. Stateful `web` means session + CSRF + encrypted cookies (M7); `api` stays bearer-only.
5. Until Prism (M6), web HTML may be hand-built strings via `html()` — still HTML, not JSON-as-HTML.
6. `HttpException` on API stays JSON `{message, status, errors?}`. On web, prefer HTML error pages once views exist; until then a minimal HTML error body is acceptable for web-only routes.

**Known boundary:** `almasix.http.Response` is currently Starlette's `Response` re-exported so controllers can annotate HTML actions without importing Starlette. App code still imports `almasix.*` only. An Almasix-owned response object is a candidate for a later DX pass — only if it earns its keep.

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
| `resource` / `apiResource` | **M33** |
| `view` routes | Prism (M6) |

## Decision: Security roadmap

M2 shipped the middleware **pipeline + group mechanism** only — `web` and `api` default stacks are empty. Security is **not** implied by M2.

| Concern | Approach | Milestone home |
| --- | --- | --- |
| Security headers (CSP baseline, `X-Frame-Options`, `Referrer-Policy`, etc.) | Default middleware pack; config knobs in `config/http.py` | After M3 / with web hardening — no session dependency |
| CORS | Config + middleware for API apps | Same hardening pass |
| CSRF | Token + session; Prism `@csrf` | With sessions (M7 or dedicated web-security slice immediately before/with M7) |
| Cookie signing / encryption | Session / cookie stack | M7 |
| XSS escaping | `{{ }}` escaped vs `{!! !!}` raw | Prism M6 |
| CSP nonces | Tied to view rendering | Prism M6 ladder (framework directives) |
| Trusted proxies | Request / URL generation | With subpath helpers |
| Rate limiting | Optional middleware | **M35** |
| `auth` / `guest` | Guards | M7 |

**Rules:**

- Do **not** ship CSRF theater without a real session store
- Default **web** middleware should be secure-by-default once the web stack exists; API scaffolds may omit CSRF
- Exhaust one milestone at a time — do not fold this whole table into M3

## Decision: Request capture (Laravel parity)

`almasix.http.Request` is the app-facing request type. Controllers must not need Starlette/FastAPI request types.

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

**Why early (binding rationale):** at the end of M3 the framework owns roughly 25 English strings, all in `almasix.validation` plus a few exception defaults. That is the entire retrofit cost today. Every later milestone (Prism views, auth messages, M8 error pages) multiplies it.

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
| Publish | `python smith lang:publish` — scaffolds `lang/` and publishes framework catalogs (Laravel `lang:publish`) |
| Make | `python smith make:lang <locale>` — empty locale tree for a new language |
| Missing | `python smith lang:missing [--locale=xx]` — reports keys present in the fallback but absent in the target |

**Rules:**

- The active locale is **request-scoped**. A process-wide mutable locale is a concurrency bug under ASGI — do not ship one.
- Missing keys must degrade visibly (return the key), not silently render blank.
- Framework strings must be overridable by apps without vendoring the framework catalog.
- Pluralization must be **locale-correct**, not English one/other pretending to be universal — **Babel is a binding dependency** for CLDR plural rules and Number/date formatting.
- `lang:*` / `make:lang` ship on the existing thin Typer `smith` surface (same pattern as M3's `make:*`); they do **not** wait for the M9 console kernel.
- Do not invent features Laravel does not ship (gettext / `.po`, locale-prefixed `/en/…` URLs as framework core).
- Do not fold Prism directives, ORM, or auth *copy* into M4 — M4 owns the translator; later milestones **consume** it. Prism **must** ship `@lang` / `@choice` / `__()` in views as part of M6's exhaust, wired to this translator.

**Explicitly deferred (not Laravel core i18n):**

| Item | Home |
| --- | --- |
| `@lang` / `@choice` / `__()` Prism directives | **M6** — required consumer of M4; not optional |
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
| Production pages | Resolve order: app `resources/views/errors/{status}.prism.html` → published/custom override → framework fallback (dependency-free HTML if Prism is unavailable). Cover at least `404`, `419`, `429`, `500`, `503` |
| Publish | `python smith errors:publish [--bundle=default\|tailwind\|bootstrap] [--force]` — copies a chosen set into `resources/views/errors/` for customization (Laravel `vendor:publish --tag=laravel-errors`). Scaffold / `almasix new` ships the **default** set; starter kits may pre-select Tailwind or Bootstrap |
| Bundle variants | Framework ships three **look** bundles under `almasix.exceptions` stubs: `default` (plain CSS, no toolchain), `tailwind`, `bootstrap`. Markup stays Prism; CSS/class conventions match the bundle. Core never depends on Node/Tailwind/Bootstrap — kits own compilation; published views assume the kit’s assets when non-default |
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

- Repo/project `almasix`, installable distribution `almasix`
- Subpackage stubs: `framework`, `config`, `providers`, `http`, `routing`, `validation`, `smith`, `installer`, plus placeholders for `orm`, `prism`, `auth`
- Root `smith` script: `python smith version` works
- **`almasix new <name>`** scaffolds a Laravel-like app tree (incl. root `smith`, `bootstrap/app.py`, controllers, routes, config)
- **`python smith serve`** runs Uvicorn against `bootstrap.app:asgi` (M0 minimal FastAPI entry; Almasix HTTP kernel replaces this in M2)
- pytest harness + GitHub Actions CI (Python 3.11–3.13)
- Smoke plan: [`docs/SMOKE.md`](SMOKE.md); automated suite under `tests/smoke/`
- Coverage gate: **≥ 98%** on full `almasix` (`pytest-cov` in CI); **always aim for 100%**, especially on the package under the active milestone (Prism: `make test-cov-prism`).

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
- `HttpKernel` compiles Almasix routes onto FastAPI (engine stays hidden)
- **`Request` Laravel-parity input bag + controller capture** (see Decision above)
- `HttpException` JSON shape `{message, status, errors?}`, converted **inside** the pipeline so route middleware still decorates error responses
- **Route polarity:** `html()` + `Response` exported from `almasix.http`; scaffold ships HTML `routes/web.py` and JSON `routes/api.py`
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
- `python smith make:controller` / `make:middleware` / `make:provider` / `make:request` — nested namespaces, `__init__.py` creation, `--force`, duplicate + bad-name guards
- **URL generation:** `url()`, `asset()`, `redirect()`, `UrlGenerator` honoring `APP_URL` + `APP_BASE_PATH`; scaffolded apps and the living example use them for every link
- Living example: `POST /api/items` backed by `StoreItemRequest`
- Tests: `tests/test_m3_validation.py`, `test_m3_make.py`, `test_m3_urls.py`, `tests/smoke/test_m3_smoke.py`, `tests/regression/test_m3_contracts.py`

**Gate met:** example boots, routes, injects, validates, responds — no FastAPI imports in app code.

**Out of scope for M3:** exception handler layer + logging (M8), `route()` named-URL helper (post-M3 DX pass). ASGI mounting at `APP_BASE_PATH` is implemented on the HTTP kernel (see subpath decision).

### M4 — Localization (`almasix.translation`) — **complete**

Full Laravel localization parity before ORM/views/auth. See the decision above for the binding contract — M4 exhausts that contract, not a thin subset.

- `Translator` + `Lang` façade bound in the container; `__()` / `trans()` / `trans_choice()` exported from `almasix.translation`
- Catalog loading: `lang/<locale>/<file>.py` (nested dicts) + flat `lang/<locale>.json` (string-as-key); cached; `add_path` / `add_json_path` / `add_lines`
- Placeholders with Laravel case transforms (`:name` / `:Name` / `:NAME`); `:count` in choices
- Pluralization: pipe forms, interval forms (`{0}|[1,19]|[20,*]`), and **Babel CLDR** plural categories per locale
- Namespaces (`package::file.key`), vendor overrides (`lang/vendor/<package>/…`), `has` / `has_for_locale`, missing-key callback
- `APP_LOCALE` / `APP_FALLBACK_LOCALE`; `set_locale` / `get_locale` / `is_locale` — **request-scoped**
- `SetLocale` middleware (`Accept-Language` for `api`; explicit always wins)
- Localization helpers: `Number.format` / `percentage` / `currency` / `file_size` / `for_humans`; date locale follows app locale
- Tooling: `smith lang:publish`, `smith make:lang`, `smith lang:missing`
- **Retrofit:** `almasix.validation` messages resolve through the shipped `en` catalog (plus `auth` / `passwords` / `pagination` stubs); M3 422/403 envelope + `en` wording stay byte-identical
- Scaffold ships `lang/en/` + locale middleware; `almasix new` apps are translatable out of the box
- Living example: `/api/locale` answers in `en` / `sw` via `Accept-Language`

**Gate met:** dual-locale endpoint, CLI tooling, validation retrofit, coverage ≥ 95%.

### M5 — `almasix.orm` — **ladder shipped, pages not exhausted**

Eloquent-shaped Active Record on SQLAlchemy Core — see the ORM decision above for the binding ladder. M5 shipped the ladder and the mental model; a 2026-09-08 audit against Laravel's **Database** (6 pages) and **Eloquent** (7 pages) sections found the surface materially short of parity, so the exhaust work is scheduled as **M40–M44** and the earlier claim of "M5 exhausts it" is withdrawn.

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

**Gate met (M5 ladder):** models, relations, migrator, seeders, coverage ≥ 95%.

**Shipped since, by M40 (Articulate model exhaust):** modern casting (`Attribute` accessors, custom / inbound casts, `encrypted*`, `hashed`, enum collections, immutable-date aliases, per-attribute date formats, query-time casts); serialization controls (`append` / `merge_appends` / `set_appends` / `without_appends`, `merge_hidden` / `merge_visible`, `serialize_date`); Eloquent collection methods keyed by model (`find`, `fresh`, `to_query`, `only` / `except_` / `diff` / `intersect` / `unique`) and custom collection classes; UUID / ULID keys, strictness config, `unguarded`, `without_timestamps`, quiet writes, pruning + `model:prune`, streaming cursors and `lazy` / `chunk_by_id`.

**Shipped since, by M42 (Query builder + database exhaust):** the where families (JSON paths, dates, `where_not`, `where_any/all/none`, existence and subquery wheres, full text, vectors), joins through closures and subqueries and laterals, unions, pessimistic locking, raw ordering and grouping, `insert_or_ignore` / `insert_using` / `update_or_insert` / `increment_each` / `truncate` / JSON column updates, `sole` / `implode`, `pipe` and `with_attributes`, `to_sql` / `to_raw_sql` / `dump` / `dd`; and under them read/write connections with `sticky`, `DB.listen` and cumulative query-time monitoring, `DB.insert/update/delete/unprepared/scalar/pretend`, manual transactions with deadlock retries and `after_commit`, pooled connections with a direct twin, and the `db` CLI shell.

**Shipped since, by M43 (Schema, migrations, and pagination exhaust):** the column catalogue and its modifiers, `change()` and the whole drop family, `Schema.rename` / `drop_all_tables` / foreign-key toggling / schema inspection, transactional and pretendable DDL, a migrator with steps, events, per-migration connections, `should_run`, and squashing, the `migrate*` flag set with production guards, and all three paginators with URL-aware links rendered through Prism.

**Still owed by M44**: the engines themselves — the suite runs against SQLite, so PostgreSQL, MySQL/MariaDB, SQL Server, and Oracle are verified by compiled SQL rather than by execution.

### M6 — Prism (`almasix.prism`)

**Full Blade parity** — see the Views decision. M6 exhausts that ladder; it is a major product surface (a new Python view engine), not a stopgap.

- Compile-to-Python + mtime/warm cache; `view()` / `ViewFactory` via provider (`almasix[prism]` extra may stay empty while Prism is core)
- Layout inheritance, includes, control flow, **components & slots**, stacks, custom directives
- Replace hand-built web HTML in the living example with `.prism.html` (including componentized UI where it pays off)
- **i18n (required):** `@lang` / `@choice` / `__()` wired to `almasix.translation`
- **Docs (required):** dedicated Starlight **Prism** section — thorough how-tos, not a single stub page
- Benchmark suite from day one; continue parity without blocking auth
- **Subpath:** asset helpers + smoke under `APP_BASE_PATH`
- XSS defaults: escaped `{{ }}` vs raw `{!! !!}`
- **Tooling:** `smith make:component` (anonymous `.prism.html` under `resources/views/components`). Editor tooling — grammar, highlighting, snippets, formatter, directive completion — is **M45**, the Blade-equivalent IDE support; it waits until the directive vocabulary stops moving.
- **Assets:** `asset()` / `@asset` + serve `public/` in `smith serve`. Default scaffold ships Vite + Tailwind (`package.json`, `resources/css|js`, → `public/build`). Progress may keep plain CSS/JS under `public/` for the living demo while still carrying the default Vite tree for scaffold baseline parity. Full `@vite` directive is a follow-up.

**Gate:** ladder exhausted, Prism docs section covers shipped surfaces, progress example is Prism-first, coverage **100%** on `almasix.prism` (statements + branches on the M6 test suite). Real `@csrf` / `@auth` / `@guest` token wiring waits on M7 sessions; `smith view:*` CLI waits on M9 console kernel (engine `cache_views` / `clear_cache` APIs ship now).

### M7 — `almasix.auth`

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
| Starter-kit auth UI (Breeze-class scaffolds) | Starter kits (**M36**) |
| Sanctum / Passport / Socialite | First-party packages (**M37**) |
| Authorization (Gates / Policies) | **M19** (Laravel’s separate Authorization docs) |
| Email verification | **M13** notifications (+ mail channel) |
| Real outbound reset mail | **M12** mail / **M13** notifications — broker + token API ships now |

**Gate:** ladder exhausted, Auth/Hashing/Passwords docs published, progress uses real credentials, coverage ≥ 98% (auth + hashing + passwords packages aim 100%).

**Status (M7):** Ladder shipped — session/CSRF/EncryptCookies; `Hash` (bcrypt + optional `argon2`/`argon2id`); session + token guards (`attempt`/`login`/`logout`/`once*`/`login_using_id`, remember-me **Set-Cookie**, rehash-on-login); `auth`/`guest`/`password.confirm`/`auth.basic`/`auth.start`; `Request.user()`; intended URL; auth events; `Password` broker (memory + optional DB table); catalogs; scaffold `config/auth.py` + `config/hashing.py`; Starlight Authentication/Hashing/Passwords; progress login + `/api/me`. **Deferred by design:** Sanctum/Passport/Socialite; Gates/Policies → **M19**; email verification → **M13**; outbound reset mail → **M12**/**M13**.

### M8 — Error handling (`almasix.exceptions` + `almasix.log`)

Turns M2's minimal kernel behavior into a real handler layer. See the decision above for the binding contract.

- `Handler` base in `almasix.exceptions`; app override at `app/Exceptions/Handler.py`, resolved from the container
- `report()` / `render()` split, `dont_report`, `reportable()` / `renderable()` hooks
- Per-exception `report()` / `render()` methods honored before the handler default
- **Polarity-aware rendering:** HTML for web, locked JSON envelope for api — **no** `Accept` flip
- `APP_DEBUG` web debug page (traceback, source excerpts, request/route context) with a test proving it is off when debug is false; api debug only widens `message`, never embeds a stack trace in JSON
- Production error views: `resources/views/errors/{status}.prism.html` + framework fallback; statuses at least `404` / `419` / `429` / `500` / `503`
- `python smith errors:publish [--bundle=default|tailwind|bootstrap] [--force]`; `almasix new` ships **default**; Tailwind/Bootstrap sets for kits / opt-in publish
- Logging slice: `config/logging.py`, channels (`stack`, `single`, `daily`, `stderr`), levels, context, `log()` helper
- Living example: a deliberate failure on a web route rendering HTML, the same failure on an api route rendering JSON

**Depends on:** M2 route polarity (done) and M6 Prism for error views. Do not start before M6 — HTML error pages without a view engine is exactly the placeholder trap.

**Status (M8):** Ladder shipped — `Handler` (`report`/`render`, hooks, `dont_report`); polarity-aware HTML vs JSON; unmatched-route path polarity; status mapping (`ModelNotFoundError` → 404, …); `APP_DEBUG` web debug page; production `errors/{status}` views + framework / Prism-off fallbacks; `errors:publish` (`default`/`tailwind`/`bootstrap`, CDN-free); `almasix.log` channels + `log().with_()` context; `lang/en/errors.py`; `ServiceUnavailableHttpException`; scaffold + progress `/boom` + `/api/explode`; smoke + Error Handling / Logging docs.

### M9 — Console + scheduler (`almasix.console`)

Smith today is a thin Typer entry (`version`, `serve`, `make:*`, `migrate`, …). M9 turns it into a Laravel-shaped **console kernel**.

- `Command` base: signature / help / `handle()`, IoC-resolved
- Command discovery: `app/Console/Commands`, `python smith list`, `python smith make:command`
- Framework commands stay in `almasix.console`; app commands register via provider or auto-discover
- Input / output helpers (arguments, options, tables, confirm) — exhaust the DX, not a stub Typer wrapper
- **Almasix Prompts** (`almasix.console.prompts`) — Laravel Prompts-class interactive UI: `text`, `textarea`, `password`, `number`, `confirm`, `select`, `multiselect`, `suggest`, `search`, `spin`, `progress`, `note`/`info`/`warning`/`error`/`alert`, with non-TTY / CI fallbacks; Command `ask` / `choice` / `secret` / `anticipate`
- **Scheduler:** `routes/console.py` or `app/Console/Kernel` schedule DSL (`daily`, `hourly`, `every_minute`, cron expressions)
- `python smith schedule:run` / `schedule:work` (long-running ticker) suitable for cron or a dedicated process
- Overlap / mutex for scheduled tasks (filesystem lock is enough until **M15** cache / **M16** Redis)
- Console-side rendering of uncaught exceptions, wired to the M8 handler
- **Interactive REPL (Tinker-class) — `python smith loupe`** — user-friendly Python shell with the app booted (container, helpers, models, DB). Laravel parallel: `php artisan tinker`. Prefer **IPython** (`almasix[loupe]` / `almasix[dev]`) with colored prompts + syntax highlighting; else ptpython; else Rich-enhanced fallback (never a bare undecorated `code.interact` without guidance). Boot `Application` once; pretty repr; history/completion when the preferred shell is available.
- Living example: at least one app command + one scheduled task + a smoke that the REPL boots and can resolve a model / run a trivial query

**Depends on:** solid Application boot (done); M8 for console exception rendering. Does **not** require queues — scheduled closures/commands run in-process; queue integration is M11. The REPL may land with M9 or as a fast follow once the console kernel exists — it must not be forgotten.

**Status (M9):** Ladder shipped, **page not exhausted** — the Artisan surface is finished in **M30** (one command surface, closure commands, `Artisan.call` / `queue`, isolatable commands, signal traps, console events, signature shortcuts / arrays / descriptions, stub publishing, missing built-ins) and the scheduler in **M31** (full frequency + hook vocabulary, `schedule:list` / `schedule:test`). What M9 delivered: `Command` base + discovery (`app/console/commands`, `almasix.console.commands`); `smith list` / `make:command` / `inspire`; schedule DSL (`every_minute` / `hourly` / `daily` / cron) + `schedule:run` / `schedule:work` + filesystem mutex; console exceptions report through M8 Handler; **`smith loupe`** REPL (IPython preferred → ptpython → Rich fallback); **Almasix Prompts** (`almasix.console.prompts` — Laravel Prompts-shaped `text`/`select`/`confirm`/`spin`/`progress` + Command `ask`/`choice`/`secret`/`anticipate`); **`dump()` / `dd()`** (`almasix.debug` — Rich CLI + HTML/JSON HTTP dump pages); progress `progress:hello` / `progress:prompts` + `/dd` · `/api/dd` + `routes/console.py`; smoke + docs.

### M10 — Filesystem (`almasix.filesystem`)

FlySystem-shaped **Storage** façade — app code never talks to raw `pathlib` for “disk” operations on the happy path.

- `Storage.disk("local")` / `Storage.put` / `get` / `exists` / `delete` / `copy` / `move` / `url` / `temporary_url` (where driver supports)
- Drivers: **local** (required), **S3-compatible** (optional extra), memory (tests)
- Config: `config/filesystems.py` — default disk, roots under `storage/app`, public disk + symlink story (`python smith storage:link`)
- Stream / large-file friendly APIs; visibility (`public` / `private`)
- Integrate with existing `Request` uploads (`UploadedFile` → `Storage`)
- Provider + `storage()` helper; smoke against local disk

**Depends on:** M2 request files (done). Natural prerequisite for queue failed-job payloads and **M12** mail attachments.

**Status (M10):** Ladder exhausted — `Storage` / `storage()` / disks (`local`, `public`, `memory`, S3 via `almasix[s3]`); real `read_stream` / `write_stream` on local; visibility (+ chmod best-effort); `config/filesystems.py`; `storage:link`; UploadedFile `store` / `store_as` + `put_file` / `put_file_async`; **`temporary_url` raises on local/memory** (S3-only, Laravel-honest); provider; progress + docs + tests.

### M11 — Queues + job workers (`almasix.queue`)

- `Job` base: `handle()`, `dispatch()`, delay, tries, backoff, timeout
- `ShouldQueue` vs sync dispatch; `dispatch_sync` escape hatch
- Queue connection drivers: **database** (after M5) and/or **Redis** (**M16** driver); **sync** driver for tests/dev default
- `python smith queue:work` / `queue:listen` / `queue:retry` / `queue:failed`
- Failed jobs table/store + `failed()` hook on Job; failures report through the **M8** handler
- Middleware / job pipeline (rate limit, unique jobs — subset, exhaust what you claim)
- Horizon-class dashboard is **out of scope**; process supervision is docs (systemd / Docker)
- Living example: dispatch from a controller or command; worker processes the job

**Depends on:** M5 for database queue; M8 for failure reporting; M9 for `queue:*` commands; M10 nice-to-have for job artifacts.

**Unblocks:** queued mailables (M12) and queued notifications (M13).

**Status (M11):** Ladder exhausted — `Job` / `ShouldQueue` / `dispatch` / `dispatch_sync`; **`timeout` enforced** via `asyncio.wait_for`; sync + database drivers; `queue:work` / `listen` / `failed` / `retry`; middleware + unique id; living demo `progress:demo` / `ProgressDigestJob`; tests + Queues docs.

### M12 — Mail (`almasix.mail`)

**Parity target:** Laravel’s [Mail](https://laravel.com/docs/mail) documented surface — `Mailable`, `Mail` façade, transports, Markdown mailables. A thin “SMTP wrapper” exit is **not** allowed.

**In scope (framework core):**

| Ladder rung | Contract |
| --- | --- |
| Config | `config/mail.py` — default mailer, from address, transport settings |
| Mailable | Class-based messages: `envelope` / `content` / `attachments` (Laravel 9+ shape) or exhaust an equivalent fluent API |
| Mailer | `Mail.to(...).send(Mailable)` / `cc` / `bcc` / `send` / `queue` (queue when M11 exists; sync always) |
| Transports | **log** + **array** (tests/dev) + **SMTP** (production baseline); optional extras later (SES, Mailgun, …) as drivers behind the same API |
| Markdown mail | Prism/Markdown templates under `resources/views/mail` (or agreed path); themeable components |
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

**Depends on:** M6 Prism for Markdown/HTML mail views; M10 for attachment disks (soft — path attachments can ship earlier); M11 for `ShouldQueue` mailables (sync send ships without waiting on workers).

**Gate:** ladder exhausted, Mail docs published, array/log drivers green in CI, SMTP documented, coverage ≥ 98% on `almasix.mail` (aim 100%).

**Status (M12):** Ladder exhausted — `Mailable` (`envelope` / `content` / `attachments`); `ShouldQueue` honored on `send()` via serializable `SendQueuedMailable`; `Mail.to(…).send/queue`; log + array + SMTP; Markdown themes (`mail.themes.default` + builtin fallback) + `<x-mail.*>` components; Storage/path/bytes attachments; `MailAssertions`; living `WelcomeMail` via `progress:demo`; tests + Mail docs.

### M13 — Notifications (`almasix.notifications`)

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

**Gate:** ladder exhausted, Notifications docs published, mail + database channels tested, password-reset outbound no longer pluggable-only theater, coverage ≥ 98% on `almasix.notifications` (aim 100%).

**Status (M13):** Ladder exhausted — `Notifiable` / `Notification` / channels (mail/database/log/array); `ShouldQueue` via serializable `SendQueuedNotification` (no double-send); `MustVerifyEmail` + **signed** verification URLs + **`verified` middleware** + progress `/email/verify*` routes; `ResetPasswordNotification` as password-broker default; Authentication + Passwords docs updated; living `progress:demo` notify path; progress `User` is Notifiable; tests + Notifications docs.

### M14 — Helpers + Strings (`almasix.support`)

Laravel [Helpers](https://laravel.com/docs/helpers) + [Strings](https://laravel.com/docs/strings) parity on top of the shipped Support `Collection`.

- Global / module helpers mirroring Laravel’s helper catalog that Almasix does not already own (`abort_if`, `blank`, `filled`, `data_get` / `data_set`, `value`, `tap`, `with_`, `optional`, `retry`, `throw_if`, …) — exhaust what you claim; skip PHP-only relics
- `Str` / `Stringable` fluent string API (`almasix.support.Str`) — `of`, `camel`, `snake`, `slug`, `limit`, `contains`, `replace_*`, `uuid`, … Laravel Strings surface
- Docs: Starlight **Helpers** + **Strings**; Collections page stays the collection-only entry
- Living example / tests for the helper surface used by scaffolded apps

**Depends on:** Support Collections (done). Natural early Digging Deeper milestone — does not require M10–M13.

**Gate:** claimed helper + `Str` surface exhausted, docs published, coverage ≥ 98% on new modules.

**Status (M14):** Ladder shipped — `Arr`, `Number`, `data_*` / misc helpers (`blank`, `tap`, `optional`, `retry`, `abort_if`, path helpers, …); `Str` / `Stringable` / `str_()`; Starlight Helpers + Strings; progress `progress:helpers`; tests + smoke.

**Correction (2026-09-08 audit):** "exhausted" was wrong — the ladder reaches every category, but no category is closed. Against the Laravel pages: `Str` has 80 of 87 methods, `Arr` 42 of 57, `Number` 17 of 20, and the fluent `Stringable` only 27 of 117, because it hand-writes its methods instead of delegating the whole `Str` surface. Of Laravel's ~65 global helpers, 37 exist somewhere in the package and 28 do not — some fairly (`broadcast`, `policy`, `context`, `fake` await their features) and some not (`request`, `response`, `session`, `cookie`, `logger`, `report`, `resolve`, `app`, `validator`, `old`, `back`, `bcrypt`, `method_field`, `csrf_field` all wrap surfaces that already ship). The URL family (`route`, `to_route`, `action`, `to_action`, `uri`, `secure_url`, `secure_asset`) belongs with named routes in **M33**. Docs are short the same way collections are: Laravel spends 3,787 lines on Helpers and 4,042 on Strings, a section per method; Almasix spends 154 and 180 on grouped tables. **M50** closes both.

**Closed (2026-09-08, M50):** `Str` 91, `Arr` 59, `Number` 20, and `Stringable` 134 by delegating the static surface rather than hand-writing it — and immutable now, as Laravel's is. The global helpers that wrap shipped surfaces exist; `broadcast`, `context`, and `fake` remain honestly absent, and the URL family is still **M33**'s. The pages are 2,980 and 3,260 lines, 377 sections, every example run before it was published.

### M15 — Cache (`almasix.cache`)

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

### M16 — Redis (`almasix.redis` + drivers)

Laravel [Redis](https://laravel.com/docs/redis) connection manager and first-party drivers for session, cache, and queues.

- Redis connection / cluster config (`config/database.py` redis connections or `config/redis.py`)
- Drivers: **session** (M7 session stack), **cache** (M15), **queue** (M11) — opt-in via config; file/cookie/database remain defaults for local
- `Redis` façade for app-level get/set/pubsub primitives used by those drivers
- Docs: Starlight **Redis**; update Session / Cache / Queues pages for the Redis driver

**Depends on:** M7 session, M11 queues, M15 cache. Optional `almasix[redis]` extra.

**Gate:** at least one driver path proven end-to-end (cache or session); docs honest about extras; coverage ≥ 98% on Redis package.

**Status (M16):** Ladder exhausted — `Redis` / `redis()` façade; `config/redis.py`; `almasix[redis]` extra; Redis drivers for **cache** (tags + locks), **session**, and **queue**; Worker generalized beyond database; Starlight Redis; progress `progress:redis`; tests via FakeRedis (no server required in CI).

**Status (M17):** Ladder exhausted — `Crypt` / helpers; JSON-safe `encrypt`/`decrypt` (no pickle); `encrypt_string`/`decrypt_string`; `APP_PREVIOUS_KEYS` rotation; shared cipher with M7 cookie encrypt; `smith key:generate`; Starlight Encryption; progress `progress:encryption`.

### M18 — Events (`almasix.events`)

**Status (M18):** Ladder exhausted — `Event` / `event()` / `listen()`; dispatcher with wildcards + subscribers; queued listeners via `ShouldQueue` + `CallQueuedListener`; `ShouldBroadcast` (whole feature in M26); `make:event` / `make:listener` / `event:list`; fakes; Starlight Events; progress `progress:events`.

### M19 — Authorization (`almasix.auth` Gates / Policies)

Laravel [Authorization](https://laravel.com/docs/authorization) — Gates and Policies (deferred from M7).

- `Gate::define` / `allows` / `denies` / `authorize` / `any` / `none`
- Policy classes + `make:policy`; auto-discovery; `Authorizable` on user
- Controller/`FormRequest` integration (`authorize` resource abilities)
- Prism `@can` / `@cannot` when views need them
- Docs: Starlight **Authorization** (Security sidebar)

**Depends on:** M7 auth (done); M6 for `@can` directives.

**Gate:** Gates + Policies exhausted, docs published, progress demo of a policy, coverage ≥ 98%.

**Status (M19):** Ladder exhausted — `Gate` / `gate()` / `authorize()`; policies + `Policy` / `HandlesAuthorization` / `AuthorizationResponse` (`deny_as_not_found` → 404); `before`/`after`; guest-safe signatures; `Authorizable` on `AuthenticatableMixin`; controller `authorize` / `authorizes_resource`; FormRequest bool or response; `can` middleware + `Route.can()`; Prism `@can` / `@cannot` / `@canany` / `@cannotany`; `smith make:policy`; Starlight Authorization; progress `progress:authorization`.

### M20 — HTTP Client

Laravel [HTTP Client](https://laravel.com/docs/http-client) — outbound fluent HTTP for apps and package code.

- `Http.get/post/…`, fluent headers/auth/timeout, JSON helpers, retry, pool
- Fake / sequence assertions for tests
- Async-friendly under ASGI (httpx or equivalent behind the façade)
- Docs: Starlight **HTTP Client**

**Depends on:** nothing hard; natural after core HTTP stack is boring.

**Gate:** façade + fakes green in CI, docs published, coverage ≥ 98%.

**Status (M20):** Ladder exhausted against every section of Laravel's HTTP Client page — `Http` façade mirroring `PendingRequest` (headers + `replace_headers`, `with_token` / basic / digest auth, RFC 6570 URL parameters, query parameters, cookies, timeouts, `as_json` / `as_form` / `as_multipart` / `body_format`, `with_body(content, content_type)`, `attach`, `sink`, `base_url`, request/response middleware, `before_sending`, `when` / `unless`, `truncate_exceptions_at`, `dump` / `dd`); `Response` (json / object / collect / status predicates / `throw*` / dict protocol); Laravel-shaped `retry` (max attempts, callable or list delays, `when` receiving a throwable plus the live request it may reconfigure, `throw`); `Http.pool` (named + indexed, `concurrency`, per-request customization, failures as values); `Http.batch` (`before` / `progress` / `then` / `catch` / `finally_`, `concurrency`, `defer`, inspection, `BatchInProgressException`); `Http.macro` / `flush_macros`; `RequestSending` / `ResponseReceived` / `ConnectionFailed` events; async verbs `aget` … `aoptions` on `httpx.AsyncClient`; fakes — URL maps with real fall-through for un-faked URLs, `Http.sequence` / `fake_sequence` (raising when drained, `when_empty` / `dont_fail_when_empty`), single-response + callable + exception stubs, `Http.failed_connection` / `failed_request`, `prevent_stray_requests` + `allow_stray_requests(patterns)`, `recorded()` request/response pairs and the `assert_sent*` / `assert_sequences_are_empty` family; `ClientServiceProvider`; Starlight HTTP Client; progress `progress:http`.

**Deliberate deviations (M20):** `RecordedRequest` exposes `url` / `method` / `headers` / `body` / `data` as attributes rather than PHP-style accessor methods; `Batch.finally_` carries a trailing underscore because `finally` is a Python keyword; `Batch.defer()` runs on a background thread (Almasix has no post-response deferral hook yet) and adds `wait()`; async verbs (`aget` …) have no Laravel counterpart. Guzzle-specific surface (`withMiddleware` on PSR-7 objects, `withOptions` keys) maps onto httpx equivalents.

### M21 — Processes

Laravel [Processes](https://laravel.com/docs/processes) — first-class subprocess DX.

- `Process::run` / `start` / `pool` / `concurrently`; timeouts; input/output; fake for tests
- Docs: Starlight **Processes**

**Depends on:** console/testing helpers nice-to-have; otherwise independent.

**Gate:** claimed surface exhausted, fakes work, docs published.

**Status (M21):** Ladder exhausted against every section of Laravel's Processes page — `Process.run` for shell strings and argument lists; `ProcessResult` (`successful` / `failed` / `exit_code` / `output` / `error_output` / `see_in_output` / `see_in_error_output` / `throw` / `throw_if` / `throw_unless`); options (`path`, `input`, `env` merged into the inherited environment, `timeout` defaulting to 60s, `idle_timeout`, `forever`, `quietly`, `tty`, `options`, `when` / `unless`); real-time output callbacks; `ProcessTimedOutException` carrying the partial result; `Process.start` → `InvokedProcess` (`id`, `running`, `output` / `error_output`, `latest_output` / `latest_error_output`, `signal`, `stop`, `wait(callback)`); `Process.pool` / `concurrently` with `as_()` naming, results keyed by name and position, `running()` as a Collection, pool-wide `signal` / `stop`, keyed start callbacks; `Process.pipe` for lists and callables; fakes — command maps with real fall-through, `Process.result`, `Process.describe` lifecycles, `Process.sequence`, `prevent_stray_processes`, `recorded()` and the `assert_ran*` family; `ProcessServiceProvider`; Starlight Processes; progress `progress:process`.

**Deliberate deviations (M21):** fluent calls copy the pending process instead of mutating it, matching Almasix's HTTP client rather than Laravel's `PendingProcess`; `as_()` carries a trailing underscore because `as` is a Python keyword; `options()` takes `subprocess.Popen` keyword arguments where Laravel takes Symfony Process options; `described_command` is a property rather than a `command()` accessor, so it does not collide with the fluent `command()` setter; `quietly()` also silences the run callback, because Almasix captures output either way and the callback is the only thing left to silence; signals are the `signal` module's integers, with no cross-platform abstraction.

### M22 — Concurrency

Laravel [Concurrency](https://laravel.com/docs/concurrency) — run closures concurrently and collect results.

- `Concurrency::run([...])` (async tasks / process driver as appropriate under ASGI)
- Docs: Starlight **Concurrency**

**Depends on:** M21 Processes if process driver is claimed; otherwise asyncio-only driver first.

**Gate:** documented drivers work; docs published.

**Status (M22):** `Concurrency.run` taking one callable, a list, or a keyed map and returning results in the same shape and order; four drivers — `thread` (default, any callable, `max_workers`), `fork` (true parallelism, closures included, Unix), `process` (spawned interpreter, picklable tasks, honest error otherwise), `sync` (Laravel's debugging driver); a failing task raising only once the others have settled; `Concurrency.defer` returning a waitable `DeferredTasks`; `Concurrency.arun` for the ASGI path; `driver()` / `set_default_driver()` / `extend()` and named config entries that alias another driver; `config/concurrency.py` in the scaffold; `ConcurrencyServiceProvider`; Starlight Concurrency; progress `progress:concurrency`.

**Deliberate deviations (M22):** the default driver is `thread`, not Laravel's `process` — Python has real threads, they accept any closure, and the work this page is for (queries, HTTP calls, file reads) releases the GIL; `arun()` is an addition with no Laravel counterpart, for async controllers; `defer()` runs on a background thread and returns a handle, the same deviation as `Batch.defer()` in M20, because Almasix has no post-response hook yet; the `process` driver rejects unpicklable tasks with a clear error rather than serializing closures, since `SerializableClosure` has no dependency-free Python equivalent.

### M23 — API Resources + Serialization

Laravel [Eloquent API Resources](https://laravel.com/docs/eloquent-resources) + deeper [serialization](https://laravel.com/docs/eloquent-serialization) docs/DX.

- `JsonResource` / `ResourceCollection`; `to_array` / `with_` / `additional`; conditional attributes
- `make:resource`; wrap / pagination awareness
- Articulate serialization docs: `hidden` / `visible` / `appends` / `to_dict` / `to_json` / date serialization (code largely M5 — exhaust docs + any gaps)
- Docs: **API Resources** + Articulate **Serialization**

**Depends on:** M5 ORM (done); API route polarity (done).

**Gate:** Resources usable on `routes/api.py`, docs published, coverage ≥ 98%. **Met.**

**Status (M23):** `JsonResource` proxying the wrapped model, `to_dict(request)` with `make` / `collection` / `with_` / `additional` / `response`; the whole conditional family (`when`, `unless`, `merge_when`, `merge_unless`, `when_has`, `when_not_null`, `when_loaded`, `when_counted`, `when_aggregated`, `when_appended`, `when_pivot_loaded[_as]`) with callable values and defaults; recursive filtering that also resolves nested resources against the same request; `ResourceCollection` with `collects`, the `<Name>Resource` guess, and `AnonymousResourceCollection`; wrapping via `wrap` / `without_wrapping` / `wrap_with` with no double wrap; Laravel's `meta` + `links` for `Paginator` and an honest subset for `SimplePaginator`; `make_response` honoring a `to_response()` protocol so a controller can return a resource; `smith make:resource --collection`; Starlight **API Resources**; progress `progress:resources` and `GET /api/resources`.

**Deliberate deviations (M23):** the response hook is duck-typed (`to_response()`) rather than a `Responsable` interface, so anything can opt in without importing a base class; `to_dict()` replaces Laravel's `toArray()` to match the ORM's own serialization name; the `pivot` lookup compares against the ORM's `get_pivot_table()` because Almasix's `Pivot` reports a generic `table`; there is no `preserveKeys`, since paginated and list payloads are lists in both frameworks and keyed output is available by returning a dict.

### M24 — Model factories

Eloquent/Laravel Factory parity — primary consumer is **seeders**.

- `Factory` base, `definition()` / states / sequences, `make:factory`, `Model.factory()`, `create` / `make` / `count` / relationships
- Wire `DatabaseSeeder` demos to factories the Laravel way
- Docs: Database **Factories** (+ seeding page update)

**Depends on:** M5 seeders (done). Homes after Articulate is boring in real apps.

**Gate:** factory → seeder path green in progress/example, docs published, coverage ≥ 98%. **Met.**

**Status (M24):** `Factory` with `definition()`, `configure()`, and Laravel's whole immutable builder — `count`, `state` (dict, callable, async callable), `set`, `sequence` / `for_each_sequence` / `cross_join_sequence`, `trashed`, `connection`, `recycle`, `after_making` / `after_creating`, `raw`, `make` / `make_one` / `make_many`, `create` / `create_one` / `create_many` and their quiet twins, `lazy`; relationships through `has`, `has_attached` (pivot dict or callable), `for_`, the `has_<relation>` / `for_<relation>` magic methods, and factory-or-model attribute values that resolve to a key; `HasFactory` giving `Model.factory(count, state)`, resolution by `<Model>Factory` name then by `database.factories` import, with `new_factory()`, `guess_model_names_using`, `guess_factory_names_using`, and `use_namespace` as the escape hatches; a dependency-free `Fake` generator (seedable, `unique()`, Laravel camelCase spellings, `Fake.resolve_using` to swap in Faker); `smith make:factory [--model]` and `make:model -f`; Starlight **Factories** + a factory section on **Seeding**; the progress app's `DemoSeeder` now builds every row through a factory, and `progress:factories` demonstrates the surface end to end.

**Deliberate deviations (M24):** `make()` and `create()` are coroutines, because every write in Almasix is; `for_` and `has_attached` keep Python spellings (`for` is a keyword); factories fill past the mass assignment guard with `force_fill`, since Almasix models are guarded by default where Laravel's skeleton is not; fake data ships in-framework with a smaller provider list rather than depending on Faker, and `Fake.resolve_using` hands the whole job to the real thing; a created parent's relations are left unloaded, because this ORM has no lazy loading to fall back on.

**Shipped alongside (ORM):** per-row connections (`Model.set_connection` / `get_connection_name` / `instance_query`, plus `Model.on`), which `Factory.connection()` needs; `force_delete` now ignores global scopes, so an already-trashed row really is deletable; `attach` accepts a `Collection`.

### M25 — Articulate NoSQL / document stores

Bake **document stores into Articulate core** under the multi-store contract (see ORM decision above) — first driver **MongoDB**, same `almasix.orm` DX where semantics match.

- Connection store kinds in `config/database.py`; Mongo connection + `almasix[mongo]` extra (Motor/pymongo behind the driver — never in app signatures)
- Document `Model` path: collection naming, `_id` / key inference, casts, accessors/mutators, dirty tracking, soft deletes (where meaningful), model events/observers
- Query builder subset the driver can honor (`where` family, ordering, limit, aggregates that Mongo supports); honest errors for SQL-only APIs
- Relationships: references + embeds (document-native); do **not** fake SQL pivots/joins
- Schema story: collection indexes / setup commands — **not** SQL Blueprint theater mapped onto BSON
- Factories (M24) and seeders work against document models once M25 lands (or soft-depend: document factory support in this milestone)
- Living example: Progress (or dedicated demo) reading/writing a Mongo-backed model alongside SQL
- Docs: Database **NoSQL** / Articulate document-store pages; update Getting Started to show store kinds

**Depends on:** M5 SQL Articulate (done). Prefer after **M24** factories so seed/factory demos can cover both stores; may start design seams earlier without claiming exhaust.

**Gate:** Mongo driver exhausted end-to-end (config → model → query → tests → docs); SQL regressions still green; coverage ≥ 98% on new driver code (aim 100%). Other NoSQL engines are follow-on drivers under the same abstraction — not claimed unless exhausted here. **Met.**

**Status (M25):** `almasix.orm.documents` — a store-agnostic `Query` / `Condition` / `Order` shape, a `DocumentStore` contract, and two drivers: `MongoStore` (Motor behind `almasix[mongodb]`, with the whole operator set translated to Mongo filters, `distinct`, `$inc`, index information, and `raw_aggregate` for native pipelines) and `MemoryStore` (in-process, same semantics, unique-index enforcement — the document answer to `:memory:` SQLite); `DocumentBuilder` spelling the SQL builder's surface for what a collection can answer (the `where` family, dotted paths, ordering, windows, `select` / `distinct`, scopes, `when` / `unless` / `tap`, chunking, `lazy`, both paginators, `insert` / `update` / `upsert` / `increment` / `delete` / `truncate`) plus four document-native filters (`where_regex`, `where_exists_field`, `where_all`, `where_size`) and `where_raw` taking either an engine filter or a predicate; `UnsupportedQueryError` naming the alternative for every SQL-only call rather than pretending; `Document` reusing all of `Model` (casts, accessors, events, observers, soft deletes, factories, serialization) with `_id` keys, collection naming, and declared `indexes`; `EmbeddedDocument` with `embeds_one` / `embeds_many`, write-back on `save()`, and in-memory filtering; references — including document → SQL — through the existing relations and eager loader, with a document-native `with_count`; `DatabaseManager.store()` / `is_document()` telling stores and databases apart and refusing the wrong one; `smith make:document [--factory|--embed]`, `documents:index [--pretend]`, `documents:show`; Starlight **Documents (NoSQL)** + a document section on Database Getting Started; the progress app's `Activity` document with `GET /api/documents` and `progress:documents`.

**Deliberate deviations (M25):** Laravel ships no NoSQL, so parity here is measured against `mongodb/laravel-mongodb` — the model behaves like every other model, spelled Almasix's way. Transactions stay SQL-only, because Mongo needs a replica set and pretending otherwise would be a lie in the one place it hurts; `_id` is handed back as the store's own value rather than wrapped in an ObjectId type applications must then know about; embeds save through their parent, since an embedded document has no collection of its own; the `memory` driver is a first-class configured store rather than a test double, so the same code path runs in CI and on a laptop with no Mongo.

### M26 — Broadcasting

Laravel [Broadcasting](https://laravel.com/docs/broadcasting) — Echo-class / websocket fan-out (deferred from M13 notification channels).

- Broadcaster drivers (log/null + one real driver — Redis pub/sub or websocket bridge); `ShouldBroadcast` events
- Channel auth; client contract documented (Echo-shaped JS lives in starter kits)
- Docs: Starlight **Broadcasting**

**Depends on:** M18 Events; M16 Redis nice-to-have for Redis broadcaster.

**Gate:** at least null/log + one real path; docs published. Horizon-class UI out of scope. **Met.**

**Status (M26):** `almasix.broadcasting` — `ShouldBroadcast` (plus `ShouldBroadcastNow` and `ShouldBroadcastAfterCommit`) with `broadcast_on` / `broadcast_as` / `broadcast_with` / `broadcast_when`, payloads reflected off the event's public attributes when it says nothing, and the `InteractsWithSockets` / `InteractsWithBroadcasting` mixins behind `to_others()` and `via()`; the `broadcast()` helper returning a `PendingBroadcast` that dispatches through the event bus on `send()`, on `await`, or when it falls out of scope; a `BroadcastManager` with five drivers — `log` and `null`, Almasix's own in-process `websocket` server, `redis` pub/sub, and `pusher` over its REST API — plus `Broadcast.extend()` for a sixth; `Channel` / `PrivateChannel` / `PresenceChannel` / `EncryptedPrivateChannel`, model channels, and payloads sealed with the application key on encrypted channels; `routes/channels.py` loaded by the provider (so console sees it too) with wildcard patterns, route-model binding from type hints, channel classes resolved from the container, per-channel guards, and presence rosters; `POST /broadcasting/auth` and `/broadcasting/user-auth` answering in Pusher's signed format; a websocket at `/broadcasting/socket` speaking a Pusher-shaped protocol (`subscribe`, `unsubscribe`, `ping`, `client-*`, member added/removed), reached through a new `Route.websocket()` and kernel support; queued broadcasts as a `BroadcastEvent` job whose payload is plain JSON; `BroadcastsEvents` / `BroadcastsEventsAfterCommit` for model writes, on the back of a new `Connection.after_commit()`; a `broadcast` notification channel; `Broadcast.fake()` with the assertion set; `smith make:channel` and `channel:list`; Starlight **Broadcasting**; the progress app's `PostPublished`, broadcasting `Comment`, `GET /api/broadcast`, and `progress:broadcast`.

**Deliberate deviations (M26):** `ShouldBroadcast` is a base class rather than an interface, and the default event name is the bare class name instead of a fully qualified path, because a JavaScript file has to type it; Almasix ships its own websocket driver where Laravel points at Reverb, Pusher, or Ably, and speaks Pusher's protocol so those stay available; a queued broadcast captures its channels and payload at dispatch, since queue payloads here are JSON rather than serialized objects; `flush_broadcasts()` exists because dispatch is synchronous while the send is not, and a test or a script needs to know the send finished; channel authorization binds models from type hints rather than PHP's reflection on parameter classes.

### M27 — Search

Laravel Scout-class full-text search for Articulate models.

- `Searchable` model mixin; sync / queue indexing; driver abstraction (collection/array for tests; Meilisearch / Typesense / similar as extras)
- `smith scout:*` (or `search:*`) commands when useful
- Docs: Starlight **Search** / Scout equivalent

**Depends on:** M5 ORM; M11 for queued syncing (optional); document models (**M25**) should be searchable under the same mixin when honest.

**Gate:** one driver path + fakes; docs published. Heavy engines stay optional extras. **Met.**

**Status (M27):** `almasix.scout` — a `Searchable` mixin that indexes on `saved`, leaves the index on `deleted`, and returns on `restored`, with `to_searchable_array` / `scout_metadata` / `should_be_searchable` / `search_index_should_be_updated` / `searchable_as` / `get_scout_key[_name]` as the whole of the model contract, plus `searchable()` / `unsearchable()` on the model, on a query, and on a `Collection`, `make_all_searchable` / `remove_all_from_search`, and `without_syncing_to_search()` as a context manager or a pair of switches; a `SearchBuilder` spelling Laravel's builder — `where`, `where_in`, `where_not_in`, `order_by` / `latest` / `oldest`, `take`, `within`, `options`, `query_using`, `when` / `unless` / `tap`, `with_trashed` / `only_trashed`, and `get` / `first` / `keys` / `raw` / `count` / `cursor` / `paginate` / `simple_paginate` and their `_raw` twins; four engines behind an `Engine` contract — `database` (SQL `LIKE`, prefix matching, and the dialect's own full text on PostgreSQL and MySQL), `collection` (filtered in Python, Laravel's driver for a laptop), `meilisearch` (its REST API over the M12 HTTP client, no SDK), and `null` — plus `Scout.extend()` for a fifth; queued indexing through `MakeSearchable` / `RemoveFromSearch` jobs carrying keys rather than models, and `after_commit` indexing on the back of `Connection.after_commit()` with `flush_search()` for tests; soft deletes indexed as `__soft_deleted` when configured; `Scout.fake()` with `assert_synced` / `assert_removed` / `assert_flushed` / `assert_nothing_synced` / `assert_searched` / `assert_search_count`; `config/scout.py` in the scaffold and a `ScoutServiceProvider`; eight commands — `scout:import`, `scout:queue-import`, `scout:flush`, `scout:index`, `scout:delete-index`, `scout:delete-all-indexes`, `scout:sync-index-settings`, and `scout:status`; Starlight **Search**; the progress app's searchable `Post`, `GET /api/search`, and `progress:search`.

**Deliberate deviations (M27):** the default driver is `database`, not `algolia` — an application that has not chosen an engine should still be able to search, and Algolia has no dependency-free client; the search phrase is `.search("phrase")` while `query_using()` shapes the SQL behind the hits, because Laravel's `query()` would collide with the ORM's own; every engine method is a coroutine, so a custom engine is written `async`; `flush_search()` exists because a commit hands its index write to the loop and returns, and a test asserting on the index has to know the write landed; Meilisearch is spoken over its REST API through `almasix.client` rather than through the official SDK, which keeps search in core with no new dependency; `scout:status` is an addition — "which engine is this application actually using" is the first question every search bug asks.

### M28 — Testing toolkit

Expand beyond the current pytest + smoke/regression baseline toward Laravel’s [Testing](https://laravel.com/docs/testing) map.

- HTTP tests: `AlmasixTestCase` / async client helpers (`get`/`post`, assert status/json/session/auth)
- Console tests: `smith` command assertions (exit code, output)
- Mocking: façade fakes (Mail, Notification, Queue, Event, Http, Process) consolidated
- Browser tests: Playwright/Selenium-class optional extra — document honestly; not required in core CI
- Docs: Starlight **Testing** (+ HTTP / Console / Mocking subpages)

**Depends on:** surfaces being faked (M11–M13, M18, M20, M21). Can grow incrementally; this milestone exhausts the documented toolkit.

**Gate:** HTTP + console helpers used by framework tests themselves; docs published. **Met.**

**Status (M28):** `almasix.testing` — a `TestCase` written for pytest, whose autouse lifecycle boots the application (through the app's own `bootstrap/app.py`, so a test drives the middleware a server would), migrates with `use_refresh_database`, wraps a test in `use_database_transactions`, and takes an `almasix_base_path` fixture when the path is a fixture's to decide, with `boot_application()` for the same outside a case; a `TestClient` driving the ASGI app in-process over `httpx.ASGITransport` — every verb and its `*_json` twin, headers, bearer and basic tokens, cookies that persist between requests, `with_session`, `acting_as`, `following_redirects`, and `from_`; a `TestResponse` with the Laravel assertion set in full — nineteen status assertions, headers, cookies, content type, downloads, `assert_see` / `assert_see_text` / `assert_see_in_order` with HTML escaping, ten JSON assertions including dotted `assert_json_path` and `*`-wildcard `assert_json_structure`, validation (`assert_valid` / `assert_invalid`), session, and view assertions reading what Prism was actually given; `artisan()` returning a `PendingCommand` with `expects_question` / `expects_confirmation` / `expects_choice` / `expects_output` / `doesnt_expect_output` / `expects_table` and `assert_exit_code` / `assert_successful` / `assert_failed` / `assert_output_contains` / `assert_asked`, answered through an `AnswerSink` the console's own prompts consult; database helpers — `assert_database_has` / `missing` / `count` / `empty`, `assert_model_exists` / `missing`, `assert_soft_deleted` / `not_soft_deleted`, `refresh_database()`, and `database_transactions()`; `fake()` / `fakeable()` / `restore_fakes()` as one door to nine fakes, three of them new (`FakeQueue`, `FakeNotifications`, `FakeDisk`); `without_middleware()` / `with_middleware()` on the back of `HttpKernel.skip_middleware()`; `travel` / `travel_to` / `freeze_time` / `frozen_time` moving the clock that `now()` and model timestamps read; `tests/` with a `conftest.py` and two example tests in the scaffold, `pytest` configured in its `pyproject.toml`, `smith make:test [--unit]`, and `smith test`; Starlight **Testing** with HTTP / Console / Database / Mocking subpages; the progress app's own suite and `progress:testing`.

**Deliberate deviations (M28):** the toolkit is pytest's, not xUnit's — a `TestCase` is a class pytest collects, `setup()` / `teardown()` are coroutines run by an autouse fixture, and nothing here replaces `assert`, because a Python suite that fought pytest would be a worse suite; `RefreshDatabase` and `DatabaseTransactions` are class attributes rather than traits, and are also plain functions, since a test that is not a `TestCase` deserves them too; there is no browser-test surface — Playwright is a better Dusk than anything this framework should ship, and the honest answer is to point at it; `TestResponse` reads the session and the rendered views out of recorders the client installs, because a response object here is `httpx`'s and knows nothing of either; `boot_application()` is an addition, since Laravel's `createApplication` has a `bootstrap/app.php` to require and Python needs a loader for the same thing.

### M29 — Package development

Laravel [Package Development](https://laravel.com/docs/packages) guidelines for first-party and community packages.

- Service provider discovery / scaffolding; `lang` / `config` / `views` publish tags
- Naming, extras, testing expectations; `almasix` namespace vs third-party prefixes
- Docs: Starlight **Package Development** (Packages / Prologue-adjacent)
- Optional: `smith make:package` stub — only if it earns its keep

**Depends on:** providers + lang namespaces (done); Prism/view publish patterns useful.

**Gate:** guidelines published and followed by at least one in-repo optional package or documented example.

### M30 — Smith Console exhaust (Artisan parity)

Laravel [Artisan Console](https://laravel.com/docs/artisan) — M9 shipped the ladder (`Command` base, discovery, prompts, REPL, scheduler seed) but did **not** exhaust the page. M30 closes it and unifies the two console surfaces.

- **One command surface:** migrate the ~28 hard-coded Typer callbacks in `almasix/smith/cli.py` to `Command` classes so signatures, events, isolation, `Artisan.call`, and test helpers apply uniformly. Typer stays the argv front door only.
- **Signature parser:** option shortcuts (`{--Q|queue=}`), input arrays (`{user*}`, `{--id=*}`), argument/option descriptions (`{user : The user ID}`) feeding `smith help`
- **Command surface:** exit-code constants (`SUCCESS` / `FAILURE` / `INVALID`), `fail()`, `arguments()` / `options()`, `question()` / `alert()` / `new_line()`, progress bars on the command (`with_progress_bar`), `choice(multiple=…)`
- **Prompting for missing input:** `PromptsForMissingInput`-class hook + `prompt_for_missing_arguments_using` (dogfoods M9 prompts)
- **Closure commands:** `Artisan.command("mail:send {user}", callback)` in `routes/console.py` with `purpose()` descriptions and container-resolved parameters
- **Programmatic execution:** `Artisan` façade — `call` (dict or string argv, array/bool values), `output`, `queue` (→ M11), plus `self.call` / `self.call_silently` between commands
- **Isolatable commands:** `--isolated` with lock id / expiry, sharing the M15 cache lock and the M9 filesystem mutex fallback
- **Signal handling:** `trap(SIGTERM, …)` (single + multiple signals), honored by long-running commands (`queue:work`, `schedule:work`, `serve`)
- **Events:** `CommandStarting` / `CommandFinished` (+ a startup event) through the M18 dispatcher
- **Stub customization:** move generator stubs out of inline f-strings into a real stub set + `smith stub:publish`; app stubs override framework stubs
- **Missing built-ins** (only where the underlying feature exists): `about`, `help`, `route:list`, `config:show`, `db:wipe`, `db:show`/`db:table`, `queue:restart` / `queue:clear` / `queue:monitor`, `env:encrypt` / `env:decrypt`, `optimize` / `optimize:clear` + `config:cache` / `view:cache` and their `:clear` pairs (cache targets may land with M31/M15 work), `vendor:publish`, and the `make:*` set for shipped features (`make:job`, `make:mail`, `make:notification`, `make:rule`, `make:cast`, `make:exception`, `make:view`, `make:class`, `make:enum`, `make:interface`, `make:observer`). Generators for unshipped features stay with their milestone (`make:test` → M28); `make:factory` (M24), `make:resource` (M23), `make:document` (M25), and `make:channel` (M26) shipped with theirs.
- **Discovery is all-or-nothing:** one command file that fails to import aborts discovery for the whole directory, and the notice only prints on `smith list` — invoking a command shows "No such command" with no hint why. Report the failing module, keep the rest, and say so on every run
- **Loupe allow-list:** Tinker-class `commands` / `dont_alias` configuration for the REPL
- Docs: rewrite Starlight **Smith Console** to the Artisan section order; document every built-in command
- Living example: progress app gains a closure command, an isolatable command, and a signal-trapping worker demo

**Depends on:** M9 (base), M11 (queueing commands), M15 cache (isolation locks), M18 (events). Console **test** helpers land with M28 and must be able to drive everything M30 adds.

**Gate:** every section of Laravel's Artisan page either implemented or listed as a deliberate deviation with a reason; one command surface (no command reachable only through Typer); `almasix.console` + `almasix.smith` at 100% coverage; docs published.

**Status (M30):** **Complete** (2026-09-08).

- **Shipped in M9's wake:** signature parser (option shortcuts `{--Q|queue=}`, argument/option arrays, `:` descriptions, argv terminator `--`); exit-code constants + `fail()`; `arguments()` / `options()` / `has_option()`; `question` / `alert` / `new_line` / `with_progress_bar` / `choice(multiple=…)`; `PromptsForMissingInput`; closure commands via `Artisan.command(...).purpose(...)` in `routes/console.py` with container-resolved parameters; `Artisan.call` / `call_silently` / `output` / `queue` / `has` / `all` and `self.call` / `self.call_silently`; `Isolatable` + `--isolated[=CODE]` on cache lock with mutex fallback; `trap()` signal handling; `ConsoleStarting` / `CommandStarting` / `CommandFinished`; `CommandNotFound` / `CommandFailed`.
- **Shipped in M30:** the ~30 Typer callbacks are `Command` classes and `cli.py` is 45 lines of front door — **84 commands, no second way in**; signature-derived `--help`; discovery that reports a broken module and keeps the rest; command aliases; `boots_application` so generators run in a bare directory; the stub tree behind `smith stub:publish`; `ServiceProvider.publishes()` + `vendor:publish`; the Loupe allow-list (`config/loupe.py`); and the built-ins — `about`, `help`, `env`, `docs`, `route:list`, `config:show`, `db:show` / `db:table` / `db:monitor` / `db:wipe`, `model:show`, `migrate:install` / `reset` / `refresh`, the `queue:*` maintenance set, `env:encrypt` / `env:decrypt`, `cache:clear` / `cache:forget`, `view:cache` / `view:clear`, `optimize` / `optimize:clear`, `storage:unlink`, and the eleven missing `make:*` generators.

**Deliberate deviations** (Laravel has these; Almasix does not, with reasons):

- **`config:cache`, `route:cache`, `event:cache`** — not implemented. Laravel caches them because PHP rebuilds config, routes, and listeners on *every request*; an Almasix process boots once and serves for its lifetime. Reading a whole config directory measures 0.51ms, so the cache would buy a fraction of one boot and cost a class of bug where an edit does not take. `optimize` prints what it does not cache, and why, so the difference is visible where a Laravel user looks for it.
- **`view:cache` verifies rather than persists** — Blade compiles to PHP files a deploy can carry; Prism compiles to Python functions held by the engine, so there is no artifact to ship. The command compiles every template, which answers what a deploy actually asks: do they all compile.
- **`db:show` has no size column** — table size means something different in every dialect, and SQLite only answers it when the interpreter ships `dbstat`. No column would mean the same thing across the five drivers.
- **`db:monitor` on SQLite and Oracle** reports the reason it cannot count sessions instead of raising (SQLite is a file; Oracle's `v$session` needs privileges a framework cannot assume). A breach exits `FAILURE` rather than dispatching Laravel's `DatabaseBusy`, which Almasix has no listener for.
- **`db:wipe --drop-views` / `--drop-types`** are declared and refused before anything is dropped: the schema layer knows tables only.
- **`model:show` does not name a policy** — finding one would mean guessing a class path and importing it, which is more than introspection should do.
- **`queue:flush` asks before deleting**, where Laravel's does not. A flushed job can never be retried, and every other destructive Almasix command asks; `--force` is the way past.
- **`docs` opens nothing while the site is unpublished** (see M39) — it names the source file and the variable to set rather than opening a dead URL.
- **`clear-compiled`, `package:discover`, `sail:*`** have no Python equivalent. `test` belongs to M28, and the `*:table` generators to M32, where the default migrations live.

**Two defects this milestone surfaced and fixed:** `almasix.smith` imported the CLI, so a command module importing anything from `almasix.smith` was discovered mid-import and its commands vanished depending on import order; and the failed-job store and database queue both asked `DB` for a connection literally named `"default"`, which no application defines.

### M31 — Task Scheduling exhaust

Laravel [Task Scheduling](https://laravel.com/docs/scheduling) — M9 shipped a 5-frequency DSL. The 2026-09-08 audit put it at **8 of the 82 methods** the Laravel page documents. It is now at **85 of the 86** methods that page names, the exception being `DB::table()->delete()`, which is not a scheduler method at all.

- ~~**Frequency vocabulary:** the whole table from `every_two_minutes` to `yearly_on`~~ **shipped (part 1)** — frequencies splice cron fields the way Laravel's do, so they combine; `last_day_of_month` asks the calendar at run time rather than writing a fixed day into the expression when the task is defined, which is right in February and right for a process that lives across a month boundary
- ~~**Sub-minute:** `every_second` … `every_thirty_seconds`, the long-running `schedule:run` loop they require, and `schedule:interrupt`~~ **shipped (parts 1–2)** — with a sub-minute task defined, `schedule:run` stays inside the minute and wakes on the seconds each task asked for; the interrupt is scoped to the minute it was sent in
- ~~**Day constraints:** `mondays` … `sundays`~~ **shipped (part 1)**
- ~~**Constraints:** `between` / `unless_between`, `when` / `skip`, `environments`, `even_in_maintenance_mode`, `timezone`~~ **shipped (part 1)** — a `between` window that ends before it starts is read as crossing midnight; `when` and `skip` also take a plain boolean
- ~~**Hooks:** `before` / `after` / `on_success` / `on_failure` and the eight-strong ping family~~ **shipped (part 1)** — a hook that declares a parameter is handed the task's output as a `Stringable`; pings go through the M20 client and never fail the task
- ~~**Execution modes:** `run_in_background`, `on_one_server`, `without_overlapping` expiry, `group`, job and shell tasks~~ **shipped (part 1)** — groups hold attributes on the schedule and replay them onto every task defined inside; a closure or job needs `name()` before `on_one_server()`, as in Laravel, since two servers would otherwise take two different locks
- ~~**Output handling:** `send_output_to` / `append_output_to`, `email_output_to` / `email_output_on_failure`~~ **shipped (part 1)** — output is captured around every task, so unlike Laravel a `call` or `job` task can send its output somewhere too
- ~~**Events:** the scheduled-task lifecycle~~ **shipped (part 1)** — `ScheduledTaskStarting`, `ScheduledTaskFinished`, `ScheduledBackgroundTaskFinished`, `ScheduledTaskSkipped` (which carries why), `ScheduledTaskFailed`
- ~~**Commands:** `schedule:list`, `schedule:test`, `schedule:work`, `schedule:interrupt`, `schedule:clear-cache`~~ **shipped (part 2)** — plus `smith down` / `smith up`, without which the maintenance-mode constraint would be unreachable
- ~~**Docs:** rewrite Starlight **Task Scheduling**~~ **shipped (part 3)** — 640 lines against the old 55, in Laravel's section order, with a smoke contract that fails if a documented method loses its mention or a command loses its registration

**Two more entry points came with it, both from the Laravel page:** `Artisan.command(...).schedule([...])` schedules a closure command with its arguments, and `Application.configure(...).with_schedule(callback)` defines the schedule in `bootstrap/app.py` instead of `routes/console.py`.

**Named deviations:** background tasks run in a worker thread rather than a detached OS process, so `schedule:run` waits for them before exiting — a thread cannot outlive its interpreter, and Python has no `schedule:finish` to hand a detached process. Commands are scheduled by name, not by class. The `L` / `W` / `#` cron extensions are not implemented. In Almasix's favour: a scheduled callback may be `async` and is awaited, which Laravel has no need for but Almasix's awaitable ORM, queue, and client do.

**Owed by a later milestone:** maintenance mode is only the scheduler's half — `smith down` writes `storage/framework/down` and the scheduler honours it, but HTTP requests are still served normally. The 503 response, the secret bypass, `--render`, and `--retry` need the HTTP middleware that belongs with **M34**.

**Depends on:** M30 (command surface), M11 (queued jobs), M15/M16 (locks), M12 (output email), M20 (pings).

**Gate met (2026-09-08):** frequency, constraint, hook, and output vocabulary exhausted against the Laravel page or the deviation named; `schedule:list` proves the registry; sub-minute tasks demonstrated end to end; docs published in the Laravel section order; 100% line and branch coverage on `almasix.console.scheduling`.

### M32 — Installer + scaffold stacks (`almasix new`)

Laravel [Installation](https://laravel.com/docs/installation) — `laravel new` is interactive; `almasix new` currently takes only a name and `--path`.

- **Interactive install** built on M9 prompts: stack, database, test runner, git init, dependency install, migrations — with `--no-interaction` and an explicit flag for every prompt so CI stays scriptable
- **Stack choice** (beyond Laravel, which is Tailwind-only): `tailwind` (default), `bootstrap`, `plain` CSS, and `none` — a zero-Node, server-rendered Prism app. Stack selection also picks the `errors:publish` bundle so error pages match the chosen CSS.
- **Database choice:** SQLite (default, with the file created) / Postgres / MySQL / MariaDB, writing the matching `.env` + `config/database.py` and offering to run migrations
- **Restructured scaffold:** replace the flat inlined `path -> content` dict in `almasix/installer/scaffold.py` with a parameterized stub tree shared with M30's `stub:publish`
- Post-create ergonomics: git init (`--git`, `--branch`), optional `uv` / `pip` install, `npm install && npm run build` when a Node stack is chosen, and next-step output that matches what was actually installed
- **The default migrations Laravel ships and Almasix does not.** A scaffolded app's `database/migrations/` is *empty*, so `users`, `jobs`, `failed_jobs`, `cache`, and `sessions` do not exist and `smith migrate` says "Nothing to migrate." Found during M30: every failed-job command met a table that nothing creates. The commands now say so instead of raising a database error at the user (`The failed_jobs table does not exist.`), but the tables themselves belong here — Laravel 11 ships them in the default migration set, and an app whose queue, cache, and auth tables are missing is not a working scaffold
- Docs: rewrite Starlight **Installation** with the prompt walkthrough and every flag

**Depends on:** M9 prompts (done), M30 stub tree. Starter kits are **M36**, not this milestone.

**Gate:** every prompt has a flag and a documented non-interactive default; each stack produces a booting app proven by smoke tests; docs published.

### M33 — Routing DX + named routes

Completes Laravel [Routing](https://laravel.com/docs/routing) and [URL Generation](https://laravel.com/docs/urls) (previously "Later"; URL Generation has been **Partial** since M3).

- Verb + shape sugar: `head`, `redirect` / `permanent_redirect`, `fallback`, `match`, `any`
- **Named routes** end to end: `name()` on routes and groups, `route()` / `RouteFacade.has`, signed URLs, and `route()` inside Prism
- Resource routing: `resource` / `api_resource`, `only` / `except`, shallow nesting, `resources` plural registration, and the `make:controller --resource` pairing
- `route:list` gains name / middleware columns (M30 ships the command)
- Docs: update Starlight **Routing** + **URL Generation**

**Depends on:** M2/M3 (done), M30 for `route:list`.

**Gate:** named routes usable from routes, controllers, redirects, and templates; resource routing exhausted; docs updated.

### M34 — Security headers + CORS

Post-M3 hardening pack, secure-by-default for the web stack.

- Header middleware (CSP with nonce support, HSTS, `X-Content-Type-Options`, referrer + permissions policy), configurable per group
- CORS middleware + `config/cors.py`, sensible API defaults
- Default web / API middleware stacks updated; scaffold ships them enabled
- Docs: Starlight **Security headers & CORS**

**Depends on:** M2 middleware (done), M7 web stack (done).

**Gate:** defaults on in the scaffold, documented opt-outs, smoke asserts the headers.

### M35 — Rate limiting

Laravel [Rate Limiting](https://laravel.com/docs/rate-limiting) — the cache-backed limiter plus the `throttle` middleware.

- `RateLimiter` façade (`attempt`, `too_many_attempts`, `remaining`, `available_in`, `clear`) on M15 cache
- `throttle` middleware with named limiters, per-user / per-IP keys, `Retry-After` + `X-RateLimit-*` headers
- Login throttling wired into M7 auth; queue/worker friendliness documented
- Docs: Starlight **Rate Limiting**

**Depends on:** M15 cache (locks/counters), M16 Redis for the production driver.

**Gate:** limiter + middleware + auth throttling shipped with fakes; docs published.

### M36 — Starter kits

Laravel [Starter Kits](https://laravel.com/docs/starter-kits) — opt-in application kits on top of the M32 scaffolder.

- **Web kit:** Prism auth UI (register / login / password reset / verify / profile) honoring the chosen M32 CSS stack
- **API kit:** JSON-polarity routes, token auth (pairs with M37), no session/CSRF middleware
- **SPA kit:** Vue / React front end over an Inertia-class bridge (server-side adapter + client package), the one stack M32 deliberately defers
- Selected by `almasix new` prompt / flag; each kit is a stub overlay, not a fork of the scaffold
- Docs: Starlight **Starter Kits** per kit

**Depends on:** M32 (scaffold stacks), M7 auth (done), M37 for API tokens, M6 Prism for the web kit.

**Gate:** each kit boots, authenticates, and is covered by smoke; kits share the scaffold stub tree.

### M37 — API tokens, OAuth, and social auth

First-party packages in Laravel: [Sanctum](https://laravel.com/docs/sanctum), [Passport](https://laravel.com/docs/passport), [Socialite](https://laravel.com/docs/socialite).

- **Sanctum-class** first: personal access tokens, ability scopes, SPA cookie auth, `auth:api` guard
- **Socialite-class** provider abstraction (OAuth2 redirect / callback / user mapping) with a couple of real providers
- **Passport-class** full OAuth2 server evaluated on demand — heavier, may stay an optional extra
- Shipped as optional extras (`almasix[tokens]`, …) following M29 package guidelines
- Docs: Starlight page per shipped package

**Depends on:** M7 auth, M19 authorization, M20 HTTP client (Socialite), M29 guidelines.

**Gate:** tokens exhausted and used by the M36 API kit; social auth proven with at least two providers; anything unshipped named explicitly.

### M38 — Deployment + production ops

Laravel [Deployment](https://laravel.com/docs/deployment) — how an Almasix app actually runs in production.

- `smith serve --workers` and the documented ASGI story (uvicorn/gunicorn workers, proxy headers, static + `public/build`)
- `optimize` / cache-warm story tied to M30's commands; health check endpoint conventions
- Env / secret handling, log shipping, migration + queue worker deployment notes, container example
- Docs: Starlight **Deployment**
- **Releasing Almasix itself** (scheduled 2026-09-08): the distribution name is settled as `almasix` per the Ecosystem growth note above. Tag `v0.x` and publish from CI with PyPI trusted publishing (`.github/workflows/publish.yml`). The README now installs with `pip install almasix` and carries the `pypi/v` + `pypi/dm` badges.

**Depends on:** M30 (optimize commands), M11 (workers), M34 (headers behind a proxy).

**Gate:** documented and reproducible for at least one container + one bare-metal path; `--workers` shipped; `pip install <distribution>` gives a working `import almasix` from PyPI.

### M39 — Docs site: versioning + Prologue

The documentation-site commitments from the Documentation decision above, promoted out of "Later".

- **Publish the site** (done 2026-09-08): `.github/workflows/docs.yml` builds `website/` and deploys to GitHub Pages on merges to `main`; pull requests build without deploying, and the repository's Pages source is set to GitHub Actions. Because the site is served from a subpath, `astro.config.mjs` sets `base: '/almasix'` and `website/src/middleware.ts` prefixes Markdown-authored links while rendering — Starlight rebases its own navigation but not author-written links, and Astro 7's default Markdown processor takes no rehype plugins. Doing it in middleware rather than after the build keeps `astro dev`, `astro preview` and the deployed site serving identical links. The README's docs badge points at the live site.
- Major-version switching (`1.x` / `2.x`) on the Starlight site
- **Prologue** sidebar group: Release Notes / Changelog, Upgrade Guide, orientation pages
- Changelogs and upgrade guides authored as docs content, not only GitHub Releases prose

**Depends on:** nothing in code; versioning wants a first tagged release (**M38**) to be meaningful, but publishing the site does not and can land first.

**Gate:** the documentation is readable at a public URL without cloning; a reader can open docs for the major they run; Prologue published and maintained per release.

### M40 — Articulate model exhaust (Eloquent parity)

Laravel [Eloquent: Getting Started](https://laravel.com/docs/eloquent), [Mutators & Casting](https://laravel.com/docs/eloquent-mutators), [Serialization](https://laravel.com/docs/eloquent-serialization), [Collections](https://laravel.com/docs/eloquent-collections). M5 shipped the ladder; these four pages are not exhausted.

- **Casting overhaul — done (1/3):** `Attribute` accessor objects (class-attribute and `@attribute` method forms, flexible callback arity, multi-column writes, `cache=True`) alongside the existing `get_x_attribute` methods; `CastsAttributes` custom casts, `CastsInboundAttributes` inbound-only casts, and `cast_using` castables; `encrypted` / `encrypted:array|object|collection` on M17 Crypt; `hashed` on M7 (idempotent — never double-hashes); `EnumCollection.of()`; `immutable_date` / `immutable_datetime` as documented aliases (Python dates are already immutable); per-attribute date formats (`date:%d/%m/%Y`) plus `date_format` and a `serialize_date` hook; query-time `with_casts` and per-instance `merge_casts`; a `casts()` method as well as the class attribute. Fixed along the way: the `timestamp` cast could not read back a value it had written.
- **Serialization — done (2/3):** `append` / `merge_appends` / `set_appends` / `without_appends` / `get_appends`; `merge_hidden` / `merge_visible`; `to_json(**options)`; appended keys now respect `visible` as well as `hidden`, and relations respect `visible` as well (both Laravel rules that were missing). Instance-scoped `make_hidden` / `make_visible` / `set_hidden` / `set_visible` and `serialize_date` landed earlier. Docs: **Serialization** page published (`articulate/serialization`) — it is no longer owed by M23.
- **Model surface — done (3/3):** `HasUuids` (time-ordered v7) and `HasUlids` key mixins with `new_unique_id` / `unique_ids` hooks, plus importable `ordered_uuid()` / `ulid()`; strictness configuration (`prevent_silently_discarding_attributes` → `DiscardedAttributeError`, `prevent_accessing_missing_attributes` → `MissingAttributeError`, `should_be_strict`); `without_timestamps` as a class-scoped block that also stops `touch()`; quiet writes (`save_quietly` / `delete_quietly` / `force_delete_quietly` / `restore_quietly`, muted **per instance** so concurrent work keeps its events) and `Model.without_events()`; `unguard` / `reguard` / `unguarded`; `SoftDeletes.without_trashed`; `Prunable` / `MassPrunable` with `pruning()` hooks and a `model:prune` command (`--model`, `--except`, `--chunk`, `--pretend`, discovery from `app/models`); real streaming `cursor()` on a new `Connection.stream`, plus `lazy` / `lazy_by_id` / `chunk_by_id` / `each_by_id` keyset walkers. **Still owed:** advanced subqueries and pending attributes on scopes — both are query-builder shaped, so they move to **M42**.
- **Collections — done (2/3):** Eloquent-specific `find` (by key, model, or callback), `fresh` (optionally eager-loading, dropping deleted rows), `to_query`, plus `contains` / `only` / `except_` / `diff` / `intersect` / `unique` overridden to key off primary keys rather than collection indexes; `make_hidden` / `make_visible` / `set_hidden` / `set_visible` / `append` across every model; custom collection classes via `collection_class` + `new_collection`
- Docs — done: **Mutators & Casts** and **Serialization** pages published (`articulate/casts`, `articulate/serialization`); Collections page extended with the model-keyed methods, `fresh` / `to_query`, and custom collections; `articulate/index` deepened with UUID/ULID keys, strictness, unguarding, quiet writes, pruning, and chunking; Soft Deletes & Events page gained event muting

**Depends on:** M5 (base), M17 encryption (encrypted casts), M7 hashing. Factories stay **M24**; API Resources stay **M23**.

**Gate met:** the four Eloquent pages are implemented or carry a named deviation (immutable dates are aliases because Python dates are immutable; `cursor()` cannot eager-load because it holds one result set open); `almasix.orm` at 100% statements and branches; docs published; living example (`examples/progress`) demonstrates appends and pruning; smoke suite covers the surface.

**Moved to M42:** advanced subqueries (`select_sub` / `add_select` / `order_by_sub`) and pending attributes on scopes, which belong with the query-builder exhaust.

### M41 — Relationship exhaust

Laravel [Eloquent: Relationships](https://laravel.com/docs/eloquent-relationships) — the largest page in the Laravel docs (87 sections). All ten relation types exist; their DX does not.

- ~~`latest_of_many` / `oldest_of_many` / `of_many` / `one()`; `chaperone()`; `with_default()` default models~~ **shipped (part 1)** — one-of-many picks one row per parent with a correlated subquery, so eager loads stay one query; defaults cover `belongs_to` / `has_one` / `morph_one`; chaperone covers the has-many and morph-many pairs
- ~~Aggregate eager loads: `with_sum` / `with_avg` / `with_min` / `with_max` / `with_exists`, and the lazy `load_count` / `load_sum` / `load_aggregate` family~~ **shipped (part 3)** — one query per aggregate, `as` aliases, constraining callbacks, and the deferred family on both `Model` and `Collection`
- ~~Existence querying: `or_has`, `or_where_has`, `or_where_doesnt_have`, `where_relation` / `or_where_relation`, `with_where_has`, and the morph variants (`has_morph`, `where_has_morph`, `where_doesnt_have_morph`)~~ **shipped (part 2)** — plus dotted nesting (`has("posts.comments")`) and `MorphTo.existence_query_for`, which the morph variants needed
- ~~Pivots: `with_timestamps()`, `as()` accessor naming, custom `Pivot` model classes via `using()`, `where_pivot_in` / `where_pivot_null`, `order_by_pivot`, `sync_without_detaching`, and a real `updated` result from `sync`~~ **shipped (part 4)** — plus a real `pivot` accessor on results (`Pivot` / `MorphPivot` models that save and delete through their relation) and per-id attach attributes
- ~~Morph maps (Laravel's `enforceMorphMap`) so `morph_to` stops requiring an explicit per-relation types dict~~ **shipped (part 4)**
- ~~`touches` — updating parent timestamps on child writes~~ **shipped (part 4)** — with `without_touching` / `without_touching_on`
- ~~Relation write helpers: `create_quietly`, `find_or_new`, `update_or_create`, `make` / `make_many`~~ **shipped (part 4)** — plus `first_or_new`
- ~~Docs: rewrite `articulate/relationships` to the Laravel section order~~ **shipped (part 5)** — sections now follow the Laravel page, and the N+1 deviation is documented where eager loading is explained
- ~~The last page sections the rewrite exposed: `push()` recursive saves, `where_belongs_to` / `or_where_belongs_to`, dynamic relations (`resolve_relation_using`), and `load_morph` / `load_morph_count` for per-type loading behind a `morph_to`~~ **shipped (part 5)** — `with_` default eager loads already existed and are now documented

**Named deviations:** scoped relationships (`withAttributes`) move to M42 with the subquery work; automatic eager loading (`automaticallyEagerLoadRelationships`) has no counterpart because Almasix refuses to lazy-load by default.

**Depends on:** M40 (casting/serialization land first so pivot casts behave).

**Gate:** page exhausted or deviations named; N+1 protection story documented against Laravel's `preventLazyLoading` (Almasix inverts the default deliberately); docs published.

### M42 — Query builder + database layer exhaust

Laravel [Database: Getting Started](https://laravel.com/docs/database) and [Query Builder](https://laravel.com/docs/queries).

- ~~**Query builder:** scoped relationships (`with_attributes`, inherited from M41); unions (`union` / `union_all`); pessimistic locking (`lock_for_update` / `shared_lock`); JSON where clauses; `where_exists` / subquery wheres; `where_not`; `where_any` / `where_all` / `where_none`; `where_time` and the date-helper family; full-text wheres; join subqueries and closure join clauses; `order_by_raw` / `group_by_raw` / `having_between`; `insert_or_ignore` / `insert_using`; `update_or_insert`; JSON column updates; `increment_each` / `decrement_each`; `truncate`; `lazy` / `lazy_by_id` / `chunk_by_id`; debugging (`dd` / `dump` / `dump_raw_sql`); reusable query components~~ **shipped (parts 1–3)** — plus the pieces the page implies: `select_sub` / `order_by_sub`, lateral joins, `from_sub`, `sole`, `implode`, `pipe`, `where_like` with portable case sensitivity, and `to_sql` / `to_raw_sql` split the way Laravel splits them. Dialect-specific SQL (JSON containment, full text, vectors) lives in `almasix.orm.grammar`, one compiler per engine, and an engine that cannot do the work raises rather than compiling something that means something else
- ~~**Database layer:** read / write connections with the `sticky` option; query event listening (`DB.listen`) and cumulative query-time monitoring; `DB.insert` / `update` / `delete` / `unprepared` / `scalar` / `pretend`; manual transactions (`begin` / `commit` / `rollback`), deadlock retries (`transaction(cb, attempts)`), and `after_commit`~~ **shipped (part 4)** — plus pooled connections with a `direct` twin, which schema work and the introspection commands use without being asked
- ~~**Commands:** `db:show`, `db:table`, `db:monitor`, `db:wipe`, and a `db` CLI shell (these are the database half of M30's built-in catalogue)~~ **shipped (part 4)** — `db` hands you the engine's own client rather than reimplementing a SQL shell
- ~~Docs: rewrite `database/index` and `database/queries` to the Laravel section order~~ **shipped (part 5)**

**Named deviations:** SQLite has no row locks, so a lock clause is dropped rather than faked; full-text and vector clauses raise `UnsupportedByDialectError` on engines without them; `right_join` compiles as the left join that returns the same rows, which works on every engine including SQLite before 3.39.

**Depends on:** M5, M30 (command surface for the `db:*` commands), M16 Redis nice-to-have for monitoring output.

**Gate met:** both pages exhausted or deviations named; docs published; `almasix.orm.builder`, `almasix.orm.connection`, `almasix.orm.facade`, `almasix.orm.grammar`, and the `db` command at 100% statements and branches; `smith progress:queries` demonstrates the surface.

### M43 — Schema, migrations, and pagination exhaust

Laravel [Migrations](https://laravel.com/docs/migrations) (113 sections) and [Pagination](https://laravel.com/docs/pagination).

- ~~**Column catalogue:** the ~25 missing types (`char`, `tiny_integer` … `medium_integer`, `long_text` / `medium_text` / `tiny_text`, `binary`, `enum`, `set`, `year`, `time`, the `*_tz` variants, `ip_address`, `mac_address`, `ulid`, `uuid_morphs` / `ulid_morphs` / `nullable_morphs`, `remember_token`, spatial types, `vector`)~~ **shipped (part 1)** — the blueprint moved out of `schema.py` into `almasix.orm.blueprint`, and each type maps to the engine's own spelling (`TINYINT` on MySQL, `JSONB` and native `UUID` on PostgreSQL, `INTEGER` keys on SQLite because that is the only width it counts up); `vector`, `geometry`, and `geography` join the M42 grammar
- ~~**Modifiers:** `unsigned`, `comment`, `use_current` / `use_current_on_update`, `charset` / `collation`, `virtual_as` / `stored_as` / `generated_as`, `invisible`, `auto_increment`~~ **shipped (part 1)** — plus `first`, `start_from`, and `always`; `default()` became a **server** default, as Laravel's is, so a row written by anything else gets it too
- ~~**Alteration:** `change()`, `Schema.rename`, `drop_index` / `drop_unique` / `drop_primary` / `drop_foreign` / `drop_constrained_foreign_id`, `rename_index`, foreign-key constraint toggling, and schema inspection~~ **shipped (part 1)** — `change()` restates the whole column, which is Laravel's rule because MySQL and Oracle enforce it; `Schema` gained `create_if_not_exists`, `drop_all_tables`, `has_columns`, `column_type`, `get_indexes`, `get_foreign_keys`, `get_views`, `when_table_has_column` / `when_table_doesnt_have_column`, and `without_foreign_key_constraints`. DDL now runs through the connection rather than its own engine, so it joins the surrounding transaction and `DB.pretend` can print it
- ~~**Commands and flags:** `migrate:reset`, `migrate:refresh`, `migrate:install`, plus `--pretend`, `--step`, `--path`, `--database`, `--force`; schema squashing (`schema:dump`)~~ **shipped (part 2)** — `--step` now counts migrations as Laravel's does, `--path` takes several directories, `--graceful` and `--schema-path` landed with them, and the production guard only asks in production. The migrator gained per-migration transactions, `connection` and `within_transaction` and `should_run`, `MigrationStarted` / `MigrationEnded` / `NoPendingMigrations`, timings, batch-annotated status, and FK-safe `fresh()`
- ~~**Pagination:** cursor pagination; URL-aware paginators; rendered link views in Prism for both the Tailwind and Bootstrap stacks~~ **shipped (part 3)** — `cursor_paginate` compares the ordered columns lexicographically, so several `order_by` clauses page correctly and a write mid-read does not shift the window; the three paginators share a base that knows its path, query string, page name, and fragment; `on_each_side` elides a long run; the four views ship with the framework, behind the application's own view path so an app can replace them
- ~~Docs: rewrite `database/migrations` and `database/pagination`~~ **shipped (part 4)**

**Named deviations:** SQLite cannot change a column in place, drop a foreign key or a primary key, or rename an index — each raises rather than pretending; its Python driver commits DDL as it runs, so a migration's schema changes are not rolled back there (its data is); `schema:dump` reads the schema back through the inspector instead of shelling out to `mysqldump` / `pg_dump`, so it needs no client binary and reads the same on every engine.

**Depends on:** M5, M6 Prism (pagination views), M30 (commands), M32 (stack-aware link views).

**Gate met:** both pages exhausted or deviations named; column alteration compiled for MySQL, PostgreSQL, SQL Server, and Oracle and refused honestly on SQLite; `almasix.orm.blueprint`, `almasix.orm.schema`, `almasix.orm.migration`, and `almasix.orm.pagination` at 100% statements and branches; docs published; `smith progress:schema` demonstrates the surface.

### M44 — Multi-engine database CI

Today the suite executes against **SQLite only**; PostgreSQL, MySQL/MariaDB, SQL Server, and Oracle are covered by URL construction and offline DDL string compilation. Dialect-native paths (including `upsert`) are therefore unverified.

- CI services for PostgreSQL and MySQL/MariaDB; the ORM suite runs against each
- A dialect conformance suite: schema DDL, upserts, JSON wheres, locking, transactions / savepoints, and pagination on every engine claimed
- Document engine support honestly per feature (a support matrix), including what SQLite cannot do
- SQL Server / Oracle stay best-effort unless a real service is added

**Depends on:** M42 / M43 (the features under test); ideally lands alongside them rather than after.

**Gate:** green CI on at least PostgreSQL + MySQL in addition to SQLite; the support matrix published and honest.

## IDE and editor tooling (M45–M48)

Laravel's editor story is no longer a community afterthought: there is an **official language server** ([`laravel/lsp`](https://github.com/laravel/lsp)) driving the **official VS Code extension**, **Laravel Idea** is now bundled free with PhpStorm, `laravel-ide-helper` fills in what PHP's type system cannot express, and **Laravel Boost** hands AI agents a project-aware MCP server. A developer opening a Laravel project gets completion for routes, views, config keys, translation keys, Eloquent columns, validation rules, and Blade components — plus a warning when a view does not exist.

Almasix should reach the same bar, and Prism templates specifically deserve the treatment Blade gets. Python starts ahead in one way (real type hints instead of generated docblocks) and behind in another (nothing knows what `.prism.html` is).

**Sequencing:** this track lands **after** the parity milestones it describes. Tooling that completes half a framework teaches the wrong shape, and every milestone from M30 onwards changes the very vocabulary the language server would index — command signatures, route names, cast names, relation names. Target it once M40–M44 close and the router / installer work (M32–M33) settles.

### M45 — Prism language support

The baseline every editor needs before anything smarter is possible: something that knows `.prism.html` is a language.

- **TextMate grammar** for `.prism.html`: HTML host language, `{{ }}` / `{!! !!}` expression islands, the full directive vocabulary (`@if` / `@elseif` / `@else` / `@unless` / `@isset` / `@empty` / `@for` / `@foreach` / `@forelse` / `@while`, `@extends` / `@section` / `@yield` / `@show` / `@parent`, `@include` / `@each`, `@component` / `@slot` / `@props` / `@aware`, `@push` / `@prepend` / `@stack` / `@once`, `@auth` / `@guest` / `@can` / `@canany` / `@cannot` / `@error`, `@csrf` / `@asset` / `@lang` / `@choice`, `@cache`, `@dump` / `@dd`, and `@python` / `@endpython` blocks highlighted as embedded Python)
- **Tree-sitter grammar** for the editors that use it (Zed, Neovim, Helix) and for GitHub **Linguist** registration, so `.prism.html` stops rendering as plain text in diffs and on the docs site
- Snippets for every directive and for `<x-component>` / `<x-slot>` tags, with Emmet working inside markup
- Editor behavior rules: comment toggling (`{{-- --}}`), auto-closing directive pairs, indentation inside directives, folding on directive and tag pairs, brace matching for `{{ }}`
- **Formatter** — `smith prism:format` plus a library entry point, so the same implementation serves the CLI, pre-commit hooks, and every editor's format-on-save. Blade's ecosystem needed a third-party npm formatter for this; Almasix should ship one and keep it in Python so no Node toolchain is required. Options mirror `blade-formatter` where they make sense (indent size, attribute wrapping, line length) and it must be idempotent and directive-aware, never reindenting inside `@python` blocks

**Depends on:** M6 Prism (the directive vocabulary must be stable; adding directives after the grammar ships means grammar churn).

**Gate:** grammar covers every shipped directive with a fixture per construct; formatter idempotent on the whole `examples/` and `website/` template corpus; grammars published and consumable outside VS Code (Linguist PR opened).

### M46 — Almasix Language Server (`almasix-lsp`)

One LSP server, so every editor benefits from one implementation instead of each plugin reimplementing framework knowledge. Python-hosted (`pygls`) and shipped as part of `almasix[dev]` so it is present in the same virtualenv as the app it introspects.

- **Completion** for the string-keyed surfaces where a type checker cannot help: view names in `view()` / `@include` / `@extends`, route names in `route()` / `redirect().route()`, config keys in `config()`, translation keys in `__()` / `trans()` / `@lang`, disk names in `Storage.disk()`, queue and connection names, cache stores, gate / policy abilities in `can()` / `@can`, middleware names and aliases in route definitions, relation names in `with_()` / `load()` / `has()`, model columns in `where()` / `order_by()` / `select()`, cast names in `casts`, and component names in `<x-…>` tags
- **Diagnostics**: unknown view, route, config key, translation key, disk, middleware, ability, relation, or column — the checks that make a typo a squiggle instead of a 500 at runtime. Plus Prism-specific ones: unclosed directive, `@section` without `@extends`, unknown component, missing required `@props`
- **Hover** carrying the docs: directive signatures, facade methods, and model column types, sourced from the Starlight site so documentation and tooling cannot disagree
- **Document links and go-to-definition**: `view("posts.index")` jumps to the template, `@include` / `@extends` / `<x-…>` jump to the included file, `route("posts.show")` jumps to the route definition, `config("mail.default")` jumps to the config file, a relation jumps to its declaration
- **Code actions**: create the missing view, create the missing config key, generate a migration for a column that does not exist, extract a partial from a selection, convert `@include` to a component
- **Index and invalidation**: build the symbol index by booting the application once (as `smith` does) and watching `routes/`, `config/`, `lang/`, `resources/views/`, and `app/models/` — never by regex-scraping source, which is how community tooling drifts from reality

**Depends on:** M45 (grammar), M30 (a single console surface to enumerate commands), M33 (named routes must exist before completing them), M40 (model metadata: casts, appends, relations).

**Gate:** the server answers every completion, diagnostic, hover, link, and code action above against `examples/progress`; a conformance test suite drives it over LSP itself rather than through internal APIs; cold index under a second on the living example.

### M47 — Editor integrations and type stubs

The packaging layer — what a developer actually installs — plus the typing work that makes Almasix's *own* API complete under a type checker.

- **VS Code extension**: bundles the grammar, snippets, and LSP client; view / route / config completion; run Smith commands from the palette; a `.prism.html` preview of resolved template inheritance
- **JetBrains plugin (PyCharm)**: the Laravel Idea equivalent — Prism file type with directive completion, the same string-key completions, Smith run configurations, and `make:*` generators wired into the New… menu
- **Generic LSP recipes** for Neovim, Zed, Helix, and Sublime, kept in the docs and tested in CI so they cannot rot
- **`smith ide:stubs`** — generate `.pyi` stubs for the surfaces Python's type system cannot infer: model columns (from migrations and the live schema), facade proxies, config keys as literal types, and route names as a literal union. This is the honest analogue of `laravel-ide-helper`: needed for the dynamic edges, not for the whole framework
- **`smith ide:install`** — detect the editor(s) in a project and write their configuration, the way `boost:install` does, so setup is one command rather than a documentation page
- **Type-checker plugin** (mypy, and pyright where its API allows): `Model.query()` returning a builder generic in the model, `Attribute` descriptors typing as their accessor's return type, cast-aware attribute types, relation descriptors resolving to the related model or a collection of it
- **Debugger configuration**: `debugpy` launch configs for `smith serve`, `smith queue:work`, and the test suite

**Depends on:** M45, M46. `ide:stubs` also depends on M43 (schema inspection) to read columns from a live database rather than only from migration files.

**Gate:** a fresh `almasix new` project gets working completion in VS Code and PyCharm with no manual configuration; stubs verified by a type-check test that would fail if the dynamic surface drifted; recipes for the other editors exercised in CI.

### M48 — AI agent support (MCP server + guidelines)

Adjacent to the IDE work rather than part of it, but it is half of what "editor support" means now: Laravel Boost is an MCP server plus AI guidelines plus a documentation API, and it is why agents write idiomatic Laravel rather than plausible-looking Laravel.

- **MCP server** (`smith mcp` / `almasix-mcp`) exposing the same introspection the language server indexes: application info and installed packages, database schema, read-only queries, route list, Smith command list and execution, config reads, log and exception reads, and a Loupe tool for evaluating code in application context
- **Docs search tool** over the Starlight site's content, version-aware, so an agent cites the docs for the version in the project instead of remembering an older API
- **Agent guidelines** — composable, versioned instruction files teaching Almasix's conventions and the places it deliberately diverges from Laravel (no silent lazy loading, `await` on every read, `strftime` date formats), published for the common agent formats
- **`smith mcp:install`** to detect editors and agents and write their configuration

**Depends on:** M46 (the index is the same one; build it once and serve both), M39 (versioned docs for version-aware search).

**Gate:** every tool answers correctly against `examples/progress`; guidelines reviewed against the deviation list in this plan; setup is one command for at least the MCP-capable editors Almasix documents.

## Support and reference-page exhaust (M49–M50)

Scheduled on 2026-09-08 after an audit of Laravel's Collections, Helpers, and Strings pages. These are reference pages, and Laravel documents them a particular way: **one section per method**, each with a sentence of explanation and a runnable example. Almasix documents them as grouped tables, which is browsable but not answerable — a reader who wants to know what `sliding` does has nowhere to look. Matching the format is most of the work; the code gaps are the smaller half.

**Docs standard for reference pages:** every public method gets its own heading, a one-line description, and an example with its result. Grouped tables may stay as a navigational index at the top, not as the documentation itself.

### M49 — Support Collections exhaust

Laravel [Collections](https://laravel.com/docs/collections) — 155 methods on the Method Listing plus the Lazy Collections section.

- ~~**Missing methods:** `dd`, `dump`, `lazy` (`average` turned out to be a pre-existing alias of `avg`, so the audit's count of 149 was one generous)~~ **shipped (part 1)**
- ~~**`LazyCollection`** — construction from an iterable or generator, the chainable surface, and the lazy-only `take_until_timeout`, `tap_each`, `throttle`, `remember`, `with_heartbeat`~~ **shipped (part 2)** — plus `AsyncLazyCollection`, since reading a row is awaited; `Model.cursor()` / `lazy()` / `lazy_by_id()` now return one, which is the streaming consumer this was deferred for
- ~~**Higher-order messages** — `collection.each.method()`, `collection.map.name`, and the rest of Laravel's proxied set~~ **shipped (part 1)** — all 24, with the callable-or-value decision made by inspecting the items, since Python cannot tell a property read from a method call at the call site
- ~~**Docs:** rewrite `collections` to a section per method (155 sections), plus Keys, Creating Collections, Extending Collections, Higher Order Messages, and Lazy Collections~~ **shipped (part 3)** — 2,800 lines against the old 140, and a smoke contract that fails if a public method loses its section or a section names a method that does not exist

**Named deviation:** operations needing every item at once (sorting, grouping) are absent from lazy collections rather than faked; `collect()` materialises an eager collection.

**Depends on:** nothing — the code gaps are small and self-contained. Sequence the docs rewrite alongside, since it is the larger share.

**Gate:** Method Listing exhausted or deviations named; lazy collections demonstrated against a real streaming read (`Model.cursor`); every method has its own documented section with an example; coverage stays 100% on `almasix.support.collection`.

### M50 — Helpers, `Str`, and `Stringable` exhaust

Laravel [Helpers](https://laravel.com/docs/helpers) + [Strings](https://laravel.com/docs/strings).

- ~~**`Str` (80/87):** `doesnt_end_with`, `doesnt_start_with`, `initials`, `is_match`, `match`, `match_all`, `ucwords`~~ **shipped (part 1)** — 91 methods now
- ~~**`Stringable` (27/117):** the fluent wrapper hand-writes a subset~~ **shipped (part 1)** — the hand-written proxy list is gone; `Stringable` delegates the whole `Str` surface generically, binding the subject wherever it sits in the signature, so a new `Str` method is fluent the day it lands. The fluent-only methods came with it: `new_line`, `strip_tags`, `split`, `test`, `to_base` / `from_base`, `hash`, `encrypt` / `decrypt`, and the `when_*` conditional family. It was also **mutating in place** — a real parity bug, since Laravel's is immutable; every method now returns a new instance
- ~~**`Arr` (42/57):** typed getters, `every`, `some`, `sole`, `partition`, `push`, `select`, `from`, `has_all`, `only_values`, `except_values`~~ **shipped (part 1)** — 59 methods now; Laravel's `from` is `from_`, because `from` is a Python keyword
- ~~**`Number` (17/20):** `parse_int`, `parse_float`, `spell_ordinal`~~ **shipped (part 1)**
- ~~**Global helpers:** the wrappers over surfaces that already ship~~ **shipped (part 2)** — `app`, `resolve`, `request`, `response`, `back`, `session`, `old`, `cookie`, `logger`, `info`, `report`, `bcrypt`, `csrf_field`, `method_field`, `validator`, `policy`. Several needed the plumbing under them first: a request `ContextVar` set by the kernel, a `ResponseFactory` and a `Redirect` that can flash input and errors, a cookie jar, and a global application accessor. `broadcast`, `context`, and `fake` stay honestly absent; the URL family still belongs to **M33**
- ~~**Docs:** rewrite `strings` and `helpers` to a section per method~~ **shipped (part 3)** — 3,260 and 2,980 lines against the old 180 and 154, 377 sections in Laravel's grouping, with the same smoke contract collections got. Laravel's Other Utilities (Benchmarking, Dates, Deferred Functions, Lottery, Pipeline, Sleep, Timebox) are named as deferred rather than left unmentioned
- ~~**Parity gaps the rewrite exposed**~~ **shipped (part 4)** — writing an example per method found five behaviours that quietly differed: `data_get` ignored `*` wildcards, `data_set` replaced a list with a dict keyed by the index as a string, `Arr.to_css_styles` did not read Laravel's switched-style shape, the pad family used only the first character of the pad string, and `Str.char_at` refused a negative index

**Depends on:** M33 for the URL helper family only; everything else is standalone.

**Gate met (2026-09-08):** both pages exhausted or deviations named; `Stringable` delegates every `Str` method, with a test proving the fluent and static forms agree; every method has its own documented section with a verified example.

### Docs track (may land anytime)

Not milestones — outstanding pages for code that already shipped:

- Localization Starlight page (M4 code done)
- Articulate **Mutators & Casts** how-to (M5 code done)
- Full `@vite` / hot-file Prism directive on top of `asset()` (M6 partial)

### Later (still deferred)

Everything that had a foreseeable shape has been promoted to **M30–M50** above. What remains is deferred because it is genuinely open-ended, not because it is unplanned:

- Additional NoSQL engines beyond Mongo (Cosmos API, Dynamo-shaped, …) — same M25 store abstraction; exhaust per driver when demanded, so there is no honest milestone count
- Full Prism advanced parity — an ongoing **M6 track** by design, not a one-shot milestone
- Notification inbox SPA / marketing drip — outside framework core; belongs to an application, not Almasix
- Passport-class full OAuth2 server — scoped inside **M37**, but may stay an optional extra rather than ship

Promoted in this pass: console exhaust (**M30**), scheduler exhaust (**M31**), interactive installer + stacks (**M32**), router DX and named routes (**M33**), security headers + CORS (**M34**), rate limiting (**M35**), starter kits (**M36**), tokens / OAuth / social auth (**M37**), deployment (**M38**), docs versioning + Prologue (**M39**), plus the docs track above.

Scheduled on 2026-09-08: the support and reference-page exhaust track (**M49–M50**) — Collections, then Helpers / `Str` / `Stringable`, code and per-method docs together. Also scheduled the same day: the IDE and editor tooling track (**M45–M48**) — Prism language support, the Almasix language server, editor integrations and type stubs, and AI agent support. It is written down with gates rather than left as a wish, but deliberately sequenced last: tooling indexes the framework's vocabulary, and that vocabulary is still moving until the parity milestones close.

Also scheduled on 2026-09-08, out of the README pass: publishing the documentation site to GitHub Pages (**M39**) and releasing Almasix to PyPI under a distribution name that is actually available (**M38**, with the naming constraint recorded under Ecosystem growth). Both are gaps the README could not honestly paper over — no docs URL, no PyPI badges — so they are milestones now rather than README footnotes.

And scheduled on 2026-09-08 during M30: the **lint gate (M51)**, which turned out to be a gate on paper only — CI does not run `make lint`, and `make lint` does not pass. Fixing it properly means choosing a rule set and correcting 932 findings, which is its own milestone rather than a detour inside a parity one. The README's lint claims came out in the meantime.

## Project hygiene (M51)

### M51 — Lint and format gate

Scheduled on 2026-09-08, during M30. `make lint` is described as one of the gates and **CI has never run it**: the workflow runs smoke, tests, and regression only. `[tool.ruff]` sets `line-length` and `target-version` but selects no rules, and the dev extra pins `ruff>=0.8.0` — so the rule set is whatever the installed ruff defaults to. With 0.16.5, `ruff check src tests` reports 932 findings on `main` (243 unused-noqa, 194 redefined-while-unused, 99 blind-except, 57 unsorted-imports, 57 unused-import, 51 naive `datetime` calls, and a long tail). The README's lint badge and gate row were therefore claims nothing enforced; both are removed until this milestone lands.

- **Pin ruff** to an exact version in the dev extra, so the rule set cannot change under the project the way it did here
- **Select rules explicitly** in `[tool.ruff.lint]` instead of inheriting a moving default. `E4,E7,E9,F` is the floor that already passes; `I`, `UP`, `B`, `DTZ`, `RUF`, `SIM` are the candidates, each judged by what fixing it costs and what it protects. Different selections for `src/` and `tests/` are legitimate
- **Fix the fallout, or ignore per rule with a reason.** The 243 unused-`noqa` findings are the argument: a suppression with no reason outlives the problem it silenced
- **Add the CI job** — `ruff check` and `ruff format --check` across the same Python versions as the test matrix
- **Restore the README** lint badge and the `make lint` row in the gate table, once the job exists to back them

**Depends on:** nothing. Best run between milestones, since fixing findings touches files across every package.

**Gate:** `make lint` green on a pinned ruff with an explicit selection; a CI job enforcing it on every push; the README's claims matching what CI does.

## Quality bar for “solid core”

- Type hints + tests per subpackage boundary
- Canonical `examples/api` updated every core milestone
- Docs per milestone: mental model + engine mapping in the Starlight site [`website/`](../website/) (write the page when the feature ships; `PLAN.md` stays the contract)
- Stable `almasix.*` imports; no Starlette/FastAPI types in happy-path app code
- Prism: golden fixtures + render benchmarks with regression guards
- **Coverage ≥ 98%** on `almasix` (CI fail-under on full suite; smoke runs without coverage). **Aim for 100%** always; milestone packages should hit 100% when practical (`make test-cov-prism` for M6).
- Milestone smoke + regression contracts (see [`SMOKE.md`](SMOKE.md)); `make smoke` / `make regression` / `make test-cov`

## Next implementation focus

**M20 HTTP Client gate met** — `Http` façade + fakes + retry + pool + batch + macros + events, exhausted against the Laravel page.

**M40 Articulate model exhaust gate met** — casting overhaul, serialization controls, Eloquent collections, UUID/ULID keys, strictness, quiet writes, pruning, and cursor/chunk iteration.

**M41 Relationship exhaust gate met** — one-of-many, default models, chaperone, the existence-query family including morph variants, aggregates and their deferred twins, pivot models with `using` / `as_` / timestamps / filtering, morph maps, `touches`, and the relation write helpers. All five parts have shipped: one-of-many and default models, existence queries, aggregates, pivots and morph maps and `touches`, and the docs rewrite that closed the page with `push`, `where_belongs_to`, dynamic relations, and `load_morph`. The two sections Almasix does not implement are named in the docs.

**M42 Query builder + database exhaust gate met** — the where families down to JSON paths and date helpers, joins through closures and subqueries and laterals, unions, pessimistic locking, the write family (`insert_or_ignore`, `insert_using`, `update_or_insert`, `increment_each`, `truncate`, JSON column updates), `sole` / `implode` / `pipe` / `with_attributes`, and the debugging pair. Underneath: read/write connections with `sticky`, `DB.listen` and a cumulative query-time budget, pretend mode, manual transactions with deadlock retries and `after_commit`, pooled connections with a direct twin, and `db`, which opens the engine's own client. What each engine spells differently lives in one grammar module, and an engine that cannot do the work says so.

**Now: M30 parts 2–3.** M9 shipped the console ladder but not the Artisan page, and the two command surfaces (Typer callbacks in `almasix/smith/cli.py` vs `Command` classes in `almasix/console/`) must converge before console test helpers (M28) or later `make:*` generators can be built once and work everywhere. **Then: M32**, the interactive installer, which shares M30's stub tree.

**M21 Processes gate met** — `Process.run` / `start` / `pool` / `concurrently` / `pipe`, both timeout flavours, real-time output callbacks, signals and stops, and the whole fake and assertion surface, exhausted against the Laravel page.

**M22 Concurrency gate met** — `run` / `defer` / `arun` over four drivers, with the task shape (single, list, keyed map) preserved into the results.

**M23 API Resources gate met** — `JsonResource` and `ResourceCollection` with the whole conditional family, wrapping, pagination `meta` / `links`, `make:resource`, and controllers that return a resource straight from a route.

**M24 Model factories gate met** — the Laravel builder in full (states, sequences, `has` / `for_` / `has_attached` / `recycle`, hooks, quiet writes), `make:factory`, and a `DemoSeeder` that builds every row through a factory.

**M25 Articulate NoSQL gate met** — a store abstraction with two drivers (MongoDB through Motor, and an in-process store with the same semantics), `Document` models that keep every Model behaviour, embedded documents, references that cross into SQL, declared indexes with `documents:index` / `documents:show`, and a builder that refuses SQL-only calls by name instead of pretending.

**M26 Broadcasting gate met** — `ShouldBroadcast` events with the whole channel family, five drivers (`log`, `null`, Almasix's own websocket server, Redis pub/sub, Pusher), `routes/channels.py` authorization with model binding and presence rosters, the signed `/broadcasting/auth` endpoints, model broadcasting on the back of `after_commit`, a `broadcast` notification channel, and `Broadcast.fake()`.

**M27 Search gate met** — a `Searchable` mixin that keeps the index in step with every write, the Scout builder in full, four engines (`database`, `collection`, `meilisearch`, `null`) behind a contract anyone can extend, queued and after-commit indexing, soft deletes, eight `scout:*` commands, and `Scout.fake()`.

**M28 Testing toolkit gate met** — a pytest-shaped `TestCase` that boots the application through its own `bootstrap/app.py`, an in-process client over the real middleware stack, the Laravel response assertion set in full, console commands that answer their own prompts, database helpers and two ways to keep a database clean, one door to nine fakes, a clock a test can move, `tests/` in the scaffold with `make:test` and `smith test`, and four Starlight pages.

**Milestone M29** (Package development) keeps its place in the roadmap and is unblocked; **M30–M39** were promoted out of "Later" and are now scheduled with gates.

**M45–M48 (IDE and editor tooling) come after the parity work, by design.** Laravel's editor story — official LSP, bundled Laravel Idea, `ide-helper`, Boost — is the bar, and Prism deserves what Blade gets. But a language server indexes route names, view names, config keys, model columns, and command signatures, and M30–M44 are still changing all five. Building the index first would mean rebuilding it.

**M40–M44 (Articulate + Database exhaust) outrank M33–M39 in priority.** The 2026-09-08 audit found the ORM and database surface materially short of Laravel's Database and Eloquent sections, and every application touches it — so the ORM track should be sequenced ahead of routing sugar, starter kits, and deployment docs, whatever their numbers say.

**M50 Helpers, `Str`, and `Stringable` exhaust gate met** — `Stringable` delegates the whole static surface instead of hand-writing a quarter of it, and is immutable like Laravel's; the `Arr`, `Number`, and `Str` gaps are closed; the global helpers that wrap shipped surfaces exist; and both pages document a method at a time with every example verified by running it. Writing those examples is what found the five behaviour gaps in part 4 — the argument for the format, not just the coverage.

**M49 Support Collections exhaust gate met** — the Method Listing is closed, higher order messages answer both forms, lazy collections stream over sync and async sources and back the ORM's `cursor` / `lazy` reads, and the page documents all 155 methods a section at a time with a smoke contract keeping it that way.

**M31 Task Scheduling exhaust gate met** — the 2026-09-08 audit's last open item. The scheduler went from 8 documented methods to 85 of 86: the whole frequency table, sub-minute tasks with a `schedule:run` that stays inside the minute, day and time and environment constraints, hooks and pings, output to a file or an inbox, groups, one-server claims, background tasks, the five lifecycle events, and six new commands. The page is 640 lines against the old 55.

**Docs (anytime):** see the Docs track above — Localization page (M4 code done); `@vite` directive (M6 partial). The Mutators & Casts how-to shipped with M40.
