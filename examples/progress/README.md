# Progress — Avalon living example

Progress is created with the **official installer**, then demos are layered with **`grail make:*`**.
If something is missing here that a fresh scaffold has, that is a scaffold gap — fix the installer, then re-align Progress.

Canonical plan: [`../../docs/PLAN.md`](../../docs/PLAN.md) · docs: [`../../website/`](../../website/) (`make docs`) · structure: [`structure`](../../website/src/content/docs/structure.md) · middleware: [`middleware`](../../website/src/content/docs/middleware.md)

## Recreate from scratch

```bash
cd /path/to/avalon
rm -rf examples/progress
avalon new progress --path examples
cd examples/progress
pip install -e ../.. && pip install -e .

# Generators (same as any app)
grail make:middleware DemoTagMiddleware
grail make:request StoreItemRequest
grail make:controller DemoController
grail make:controller ProgressController
grail make:controller LocaleController
grail make:controller OrmTourController
grail make:controller PostController
grail make:controller UserController
grail make:model User
grail make:model Post
grail make:model Role
grail make:model Comment
grail make:migration create_demo_tables
grail make:seeder DemoSeeder
grail make:lang sw

# Then wire routes, bootstrap middleware, demo bodies, migration `up`/`down`,
# and DatabaseSeeder.call([DemoSeeder]) (this tree already has those filled in).
```

## Run (from monorepo)

```bash
cd /path/to/avalon
source .venv/bin/activate
pip install -e .
cd examples/progress
pip install -e .
grail migrate --seed
grail serve
```

SQLite file: `database/database.sqlite` (gitignored). Same layout as `avalon new`.

Open http://127.0.0.1:3000 (or the port `grail serve` prints). With `APP_BASE_PATH=/avalon`, use http://127.0.0.1:3000/avalon/.

## M2 manual checklist

`routes/web.py` renders HTML; `routes/api.py` returns JSON. The `api` middleware group carries
`demo.tag`, so every `/api/*` response (errors included) gets `X-Avalon-Demo`; web pages do not.

```bash
BASE=http://127.0.0.1:3000

# Browser pages (expect text/html, no X-Avalon-Demo)
curl -si "$BASE/" | head -n 20
curl -si "$BASE/progress" | head -n 20

# Stateless API + middleware group header (expect application/json + X-Avalon-Demo)
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
  -d '{"name":"avalon","flag":true,"count":2}' | python -m json.tool
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
  -d '{"name":"avalon","count":"3","flag":"true"}' | python -m json.tool

# 422 with Avalon validation messages; attributes() renames count -> "item count"
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"a","count":0,"tags":"nope"}' | python -m json.tool

# authorize() returning False -> 403
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -H 'X-Demo-Forbid: 1' -d '{"name":"avalon"}' | python -m json.tool

# Set APP_BASE_PATH=/avalon in .env and restart: open http://127.0.0.1:3000/avalon/
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
  -d '{"email":"ada@avalon.dev","name":"Ada Lovelace"}' | python -m json.tool
curl -s "$BASE/api/posts/1/comments" | python -m json.tool
```

## What this proves today

| Milestone | Visible here |
| --- | --- |
| **M0** | `avalon new` + `grail serve` |
| **M1** | `Application.configure().create()`, `config()`, providers, `.env` |
| **M2** | Route DSL, groups, middleware (bootstrap fluent), verbs, Request bag, DI, HttpException |
| **M3** | `StoreItemRequest`, 422/403, `url()` + ASGI mount for `APP_BASE_PATH` |
| **M4** | `/api/locale` in `en` / `sw`; `grail lang:*` |
| **M5** | `database/migrations` + `/api/orm` tour — migrate/seed, relations, soft deletes, upsert |
| **M6** | Caliburn views — layouts, components, showcase, `view()` |
| **M7** | Session + CSRF, `/login`, Hash, `/api/me` bearer auth |
| **M8** | Handler + `/boom` · `/api/explode`, `errors:publish`, logging |
| **M9** | `progress:hello`, `progress:prompts`, `routes/console.py`, `grail schedule:run`, `grail fiddle` (aliases: `tinker`, `repl`) |
| **M10** | `Storage` / `storage:link`, `config/filesystems.py` |
| **M11–M13** | `grail progress:demo` — queue job, WelcomeMail, reset/verify notifications |
| **M14** | `grail progress:helpers` — Arr / Str / Number |
| **M15** | `grail progress:cache` — Cache façade, remember, locks |
| **M16** | `grail progress:redis` — Redis façade / cache store (skips if Redis down) |
| **M17** | `grail progress:encryption` — Crypt.encrypt / decrypt + tamper fail |
| **M18–M29** | Roadmap on `/progress`; see `docs/PLAN.md` |

## Growing with Avalon

M0–M17 are closed. Next is **M18 — Events**. The board lists the full **M0–M29** roadmap.
## CLI

```bash
grail version
grail list
grail progress:hello Avalon
grail progress:prompts
grail progress:demo
grail progress:helpers
grail progress:cache
grail progress:redis
grail progress:encryption
grail key:generate
grail storage:link
grail schedule:run
grail fiddle          # aliases: tinker, repl
grail queue:work
grail migrate
grail serve
```

Prefer `grail …` with the venv active. Use `python grail …` only when you want to invoke the root `grail` script explicitly.

Create more apps with `avalon new` — not with Grail.
