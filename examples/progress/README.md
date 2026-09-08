# Progress — Almasix living example

Progress is created with the **official installer**, then demos are layered with **`smith make:*`**.
If something is missing here that a fresh scaffold has, that is a scaffold gap — fix the installer, then re-align Progress.

Canonical plan: [`../../docs/PLAN.md`](../../docs/PLAN.md) · docs: [`../../website/`](../../website/) (`make docs`) · structure: [`structure`](../../website/src/content/docs/structure.md) · middleware: [`middleware`](../../website/src/content/docs/middleware.md)

## Recreate from scratch

```bash
cd /path/to/almasix
rm -rf examples/progress
almasix new progress --path examples
cd examples/progress
pip install -e ../.. && pip install -e .

# Generators (same as any app)
smith make:middleware DemoTagMiddleware
smith make:request StoreItemRequest
smith make:controller DemoController
smith make:controller ProgressController
smith make:controller LocaleController
smith make:controller OrmTourController
smith make:controller PostController
smith make:controller UserController
smith make:model User
smith make:model Post
smith make:model Role
smith make:model Comment
smith make:migration create_demo_tables
smith make:seeder DemoSeeder
smith make:lang sw

# Then wire routes, bootstrap middleware, demo bodies, migration `up`/`down`,
# and DatabaseSeeder.call([DemoSeeder]) (this tree already has those filled in).
```

## Run (from monorepo)

```bash
cd /path/to/almasix
source .venv/bin/activate
pip install -e .
cd examples/progress
pip install -e .
smith migrate --seed
smith serve
```

SQLite file: `database/database.sqlite` (gitignored). Same layout as `almasix new`.

Open http://127.0.0.1:3000 (or the port `smith serve` prints). With `APP_BASE_PATH=/almasix`, use http://127.0.0.1:3000/almasix/.

## M2 manual checklist

`routes/web.py` renders HTML; `routes/api.py` returns JSON. The `api` middleware group carries
`demo.tag`, so every `/api/*` response (errors included) gets `X-Almasix-Demo`; web pages do not.

```bash
BASE=http://127.0.0.1:3000

# Browser pages (expect text/html, no X-Almasix-Demo)
curl -si "$BASE/" | head -n 20
curl -si "$BASE/progress" | head -n 20

# Stateless API + middleware group header (expect application/json + X-Almasix-Demo)
curl -si "$BASE/api/health" | head -n 20
curl -s "$BASE/api/progress" | python -m json.tool

# Path params, query, bearer, only()
curl -s "$BASE/api/items/42?q=hello" -H "Authorization: Bearer secret" | python -m json.tool

# Request bag (all/query/post — body wins on key clashes)
curl -s -X POST "$BASE/api/bag?q=1" -H "Content-Type: application/json" \
  -d '{"name":"bag","q":"body"}' | python -m json.tool

# Container DI into controller action
curl -s "$BASE/api/di" | python -m json.tool

# Verbs
curl -s -X POST "$BASE/api/items" -H "Content-Type: application/json" \
  -d '{"name":"almasix","flag":true,"count":2}' | python -m json.tool
curl -s -X PUT "$BASE/api/items/42" | python -m json.tool
curl -s -X PATCH "$BASE/api/items/42" | python -m json.tool
curl -s -X DELETE "$BASE/api/items/42" | python -m json.tool
curl -s -X OPTIONS "$BASE/api/probe" | python -m json.tool

# Validation-shaped HttpException (422)
curl -s -X POST "$BASE/api/items" -H "Content-Type: application/json" -d '{}' | python -m json.tool

# HttpException JSON shape — note middleware headers still apply
curl -si "$BASE/api/boom" | head -n 20
curl -si "$BASE/api/explode" | head -n 20
curl -si "$BASE/boom" | head -n 20
curl -si "$BASE/dd" | head -n 20
curl -s "$BASE/api/dd" | python -m json.tool
curl -s "$BASE/api/missing" | python -m json.tool

# match()
curl -s "$BASE/api/echo/7?q=api" | python -m json.tool
```

## M3 checklist — validation + URLs

`POST /api/items` is backed by `StoreItemRequest`, so validation runs before the controller.

```bash
# Types coerced from strings; defaults filled in
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"almasix","count":"3","flag":"true"}' | python -m json.tool

# 422 with Almasix validation messages; attributes() renames count -> "item count"
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"a","count":0,"tags":"nope"}' | python -m json.tool

# authorize() returning False -> 403
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -H 'X-Demo-Forbid: 1' -d '{"name":"almasix"}' | python -m json.tool

# Set APP_BASE_PATH=/almasix in .env and restart: open http://127.0.0.1:3000/almasix/
# (site root redirects there). Links and the ASGI mount share the same prefix.
```

## M4 checklist — locale

```bash
curl -s "$BASE/api/locale" -H 'Accept-Language: en' | python -m json.tool
curl -s "$BASE/api/locale?count=1&name=Ada" -H 'Accept-Language: sw' | python -m json.tool
```

## M5 checklist — ORM

```bash
curl -s "$BASE/api/orm" | python -m json.tool
curl -s "$BASE/api/posts" | python -m json.tool
curl -s "$BASE/api/posts/pages?page=1&per_page=1" | python -m json.tool
curl -s "$BASE/api/posts/trashed" | python -m json.tool
curl -s "$BASE/api/users" | python -m json.tool
curl -s "$BASE/api/users/1/posts" | python -m json.tool
curl -s -X POST "$BASE/api/users/upsert" -H 'Content-Type: application/json' \
  -d '{"email":"ada@almasix.dev","name":"Ada Lovelace"}' | python -m json.tool
curl -s "$BASE/api/posts/1/comments" | python -m json.tool
```

## What this proves today

| Milestone | Visible here |
| --- | --- |
| **M0** | `almasix new` + `smith serve` |
| **M1** | `Application.configure().create()`, `config()`, providers, `.env` |
| **M2** | Route DSL, groups, middleware (bootstrap fluent), verbs, Request bag, DI, HttpException |
| **M3** | `StoreItemRequest`, 422/403, `url()` + ASGI mount for `APP_BASE_PATH` |
| **M4** | `/api/locale` in `en` / `sw`; `smith lang:*` |
| **M5** | `database/migrations` + `/api/orm` tour — migrate/seed, relations, soft deletes, upsert |
| **M6** | Prism views — layouts, components, showcase, `view()` |
| **M7** | Session + CSRF, `/login`, Hash, `/api/me` bearer auth |
| **M8** | Handler + `/boom` · `/api/explode`, `errors:publish`, logging |
| **M9** | `progress:hello`, `progress:prompts`, `routes/console.py`, `smith schedule:run`, `smith loupe` (aliases: `tinker`, `repl`) |
| **M10** | `Storage` / `storage:link`, `config/filesystems.py` |
| **M11–M13** | `smith progress:demo` — queue job, WelcomeMail, reset/verify notifications |
| **M14** | `smith progress:helpers` — Arr / Str / Number |
| **M15** | `smith progress:cache` — Cache façade, remember, locks |
| **M16** | `smith progress:redis` — Redis façade / cache store (skips if Redis down) |
| **M17** | `smith progress:encryption` — Crypt.encrypt / decrypt + tamper fail |
| **M18** | `smith progress:events` — Event.listen / dispatch / until |
| **M19** | `smith progress:authorization` — Gate / Policy / authorize |
| **M20** | `smith progress:http` — `Http` façade, fakes, retry, pool |
| **M21** | `smith progress:process` — `Process` run / start / pool / pipe, timeouts, fakes |
| **M22** | `smith progress:concurrency` — `Concurrency.run` / `defer` / `arun`, four drivers |
| **M23** | `smith progress:resources` + `GET /api/resources` — `JsonResource`, conditionals, wrapping, pagination meta |
| **M24** | `smith progress:factories` — factories, states, sequences, `has` / `for_`; `DemoSeeder` seeds through them |
| **M30** | `smith progress:console` / `progress:import` — signatures, `Artisan.call`, `--isolated`; `smith list` shows all 86 commands |
| **M31** | `smith progress:schedule` — frequencies, constraints, hooks, a tick; `smith schedule:list` / `test` / `interrupt` |
| **M40** | `User.display_name` accessor + `appends`, `Prunable` `Post`, `smith model:prune` |
| **M41** | `/api/orm` relationship tour — pivot objects, `latest_of_many`, `with_default`, `chaperone`, aggregates |
| **M49** | `smith progress:collections` — higher order messages, lazy streaming |
| **M50** | `smith progress:helpers` — fluent `Stringable`, `Arr` / `Number` gaps, global helpers |
| **M25–M48** | Roadmap on `/progress`; see `docs/PLAN.md` |

## Growing with Almasix

M0–M24, M30, M31, M40, M41, M49, and M50 are closed; **M5** is partly done.
Next is **M25 — Articulate NoSQL**. The board on `/progress`
lists the full **M0–M51** roadmap with a status and proof for each milestone.
## CLI

```bash
smith version
smith list
smith progress:hello Almasix
smith progress:prompts
smith progress:demo
smith progress:helpers
smith progress:collections
smith progress:cache
smith progress:redis
smith progress:encryption
smith progress:events
smith progress:authorization
smith progress:http
smith progress:process
smith progress:concurrency
smith progress:resources
smith progress:factories
smith key:generate
smith storage:link
smith progress:schedule
smith schedule:run
smith schedule:list
smith schedule:test --name progress:hello
smith loupe          # aliases: tinker, repl
smith queue:work
smith migrate
smith serve
```

The rest of the surface, all of it a `Command` class:

```bash
smith about                   # environment and drivers
smith db:show --counts        # tables and their row counts
smith db:table posts          # columns, indexes, foreign keys
smith model:show Post         # attributes, relationships, events
smith route:list              # every route this app answers
smith migrate:refresh --seed  # reset, re-migrate, then seed
smith queue:monitor default   # queue sizes, exits 1 when busy
smith stub:publish            # take over what make:* generates
smith vendor:publish          # copy in what a package offers
smith optimize                # and what Almasix deliberately does not cache
```

Prefer `smith …` with the venv active. Use `python smith …` only when you want to invoke the root `smith` script explicitly.

Create more apps with `almasix new` — not with Smith.
