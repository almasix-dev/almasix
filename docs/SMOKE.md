# Smoke & Regression

> Binding architecture: [`PLAN.md`](PLAN.md).  
> Coverage gate: **≥ 98%** on the **full** suite (CI `test` job); always aim for **100%**.  
> Complete the milestone smoke gate before advancing.

## Commands

| Command | What it does |
| --- | --- |
| `make smoke` / `pytest -q tests/smoke` | Smoke gate only — **no coverage** (clean exit) |
| `make regression` / `pytest -q -m regression` | Smoke + locked public contracts |
| `make test` / `pytest -q` | Full unit + smoke (no coverage) |
| `make test-cov` | Full suite with **coverage fail-under 98%** (aim 100%) |

```bash
pip install -e ".[dev]"
make smoke
make regression
make test-cov
```

## Anti-regression measures

1. **Smoke suite** (`@pytest.mark.smoke`) — end-to-end developer path for M0/M1  
2. **Contract suite** (`tests/regression/`, `@pytest.mark.regression`) — locks public exports, bootstrap lifecycle, scaffold files, IoC autowire, `.env` override  
3. **CI jobs (all required conceptually):**
   - `Smoke (regression gate)` — `pytest tests/smoke`
   - `Regression contracts` — `pytest -m regression`
   - `Unit + coverage ≥98%` — full suite with `pytest-cov` (aim 100%)
4. **Do not remove or weaken** a regression test to green CI — fix the product or consciously revise [`PLAN.md`](PLAN.md) + this doc

Markers are declared in `pyproject.toml` under `[tool.pytest.ini_options]`.

---

## M0 — Skeleton

Automated: `tests/smoke/test_m0_smoke.py`

| ID | Check | Expected |
| --- | --- | --- |
| S1 | `almasix version` | Exit 0, `Almasix 0.3.0` |
| S2 | `almasix new <app>` | Tree with `smith`, `bootstrap/app.py`, controllers |
| S3 | Invalid name / non-empty dir | Non-zero exit |
| S4 | `GET /` on generated ASGI | `200` + Welcome JSON |
| S5 | Smith `version` | Exit 0 |
| S6 | `serve` without bootstrap | Exit 1 |
| S7 | `serve` with scaffold | Calls Uvicorn `bootstrap.app:asgi` |

### Manual (once per M0 cut)

```bash
almasix new smoke_blog --path /tmp
cd /tmp/smoke_blog
pip install -e /path/to/almasix && pip install -e .
python smith serve
curl -s http://127.0.0.1:3000/
rm -rf /tmp/smoke_blog
```

(`serve` starts at **3000** and tries the next free port through **3099** if needed.)

---

## M1 — Application kernel

Automated: `tests/smoke/test_m1_smoke.py` + `tests/regression/test_m1_contracts.py`

| ID | Check | Expected |
| --- | --- | --- |
| K1 | Scaffold + `Application(...).bootstrap()` | `is_booted`, `config("app.name")` |
| K2 | Import `bootstrap.app` | Kernel bootstrapped; `GET /` includes config `app` name |
| R1 | Public exports | `Application`, `Container`, `config`, `env`, providers stable |
| R2 | Bootstrap idempotent | Double `bootstrap()` safe |
| R3 | Scaffold contract | `.env`, providers, `Application(...).bootstrap()` in bootstrap |
| R4 | Container autowire | Constructor injection + `ResolutionError` |
| R5 | `.env` override | App `.env` overrides stale process env |

### Manual (once per M1 cut)

```bash
almasix new kernel_blog --path /tmp
cd /tmp/kernel_blog
pip install -e /path/to/almasix && pip install -e .
python -c "from almasix.framework import Application; a=Application('.').bootstrap(); print(a.config.get('app.name'), a.is_booted)"
python smith serve
curl -s http://127.0.0.1:3000/
```

### M1 exit criteria

- [x] `make smoke` green
- [x] `make regression` green
- [x] `make test-cov` green (coverage ≥ 95%)
- [ ] Manual M1 checks once locally
- [x] M2 routing unlocked after M1 merge

---

## M2 — HTTP + routing

Automated: `tests/smoke/test_m2_smoke.py` + `tests/regression/test_m2_contracts.py` + `tests/test_m2_http.py` + `tests/test_m2_polarity.py`

| ID | Check | Expected |
| --- | --- | --- |
| H1 | Scaffold `routes/web.py` | Uses `Route.get`; bootstrap has `application.asgi`, no `fastapi` import |
| H2 | Scaffolded app `GET /` | 200 **HTML** (`text/html`) via Almasix router/controllers |
| H3 | Groups + middleware | Nested prefixes concatenate; middleware accumulates outer→inner |
| H4 | `HttpException` (API) | JSON `{message, status}`, **with route middleware headers applied** |
| H5 | `Request` bag | `all`/`input`/`query`/`post`/`only`/`except_`/`route`; body wins over query |
| H6 | Controller capture | `Request` + route params + container type hints |
| H7 | Route polarity | `web.py` → HTML; `api.py` → JSON (Content-Type asserts) |
| H8 | Middleware groups | `web` / `api` in `config/http.py`; group name expands to its members |

### Manual (once per M2 cut)

From `examples/progress` after `python smith serve` (see that app’s README for the full checklist):

```bash
BASE=http://127.0.0.1:3000
curl -si "$BASE/" | head -n 20                   # text/html
curl -si "$BASE/progress" | head -n 20           # text/html
curl -si "$BASE/api/health" | head -n 20         # application/json + X-Almasix-Demo
curl -s "$BASE/api/items/42?q=hello" -H "Authorization: Bearer secret" | python -m json.tool
curl -s -X POST "$BASE/api/bag?q=1" -H "Content-Type: application/json" -d '{"name":"bag","q":"body"}' | python -m json.tool
curl -s "$BASE/api/di" | python -m json.tool
curl -s -X POST "$BASE/api/items" -H "Content-Type: application/json" -d '{"name":"almasix"}' | python -m json.tool
curl -s -X POST "$BASE/api/items" -H "Content-Type: application/json" -d '{}'   # 422 JSON
curl -s "$BASE/api/boom"                         # 418 JSON {message,status}
```

### M2 exit criteria

- [x] `make smoke` green
- [x] `make regression` green
- [x] `make test-cov` green (coverage ≥ 95% — 96.85% at M2 close)
- [x] Manual curls above once locally
- [x] No M3 work until this gate passes

---

## M3 — Validation + DX

Automated: `tests/smoke/test_m3_smoke.py` + `tests/regression/test_m3_contracts.py` + `tests/test_m3_validation.py` + `tests/test_m3_make.py` + `tests/test_m3_urls.py`

| ID | Check | Expected |
| --- | --- | --- |
| V1 | `make:controller/middleware/provider/request` | Files land in Python snake_case dirs (`app/http/controllers/…`), importable (`__init__.py` created), `--force` + duplicate guard |
| V2 | FormRequest injection | Validation runs before the action; the action never sees invalid input |
| V3 | Failure envelope | 422 `{message: "The given data was invalid.", status, errors}` — the locked M2 shape |
| V4 | Message wording | `required` / `min` / `max` / `boolean` / `array` use Almasix’s default copy; `attributes()` + `messages()` override |
| V5 | `authorize()` false | 403 `{message: "This action is unauthorized.", status}` |
| V6 | `url()` / `asset()` / `redirect()` | Every link carries `APP_BASE_PATH`; absolute URLs pass through untouched |
| V7 | Generated app under a subpath | Welcome page emits `/apps/x/api/health`, never `/api/health` |

### Manual (once per M3 cut)

From `examples/progress` after `python smith serve`:

```bash
BASE=http://127.0.0.1:3000
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"almasix","count":"3","flag":"true"}' | python -m json.tool   # coerced types
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"a","count":0,"tags":"nope"}' | python -m json.tool          # 422 messages
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -H 'X-Demo-Forbid: 1' -d '{"name":"almasix"}' | python -m json.tool       # 403 authorize()

# Subpath links: set APP_BASE_PATH=/apps/progress in .env, restart, then
# open http://127.0.0.1:3000/apps/progress/ (site root redirects there).
# Generated links and the ASGI mount share the same prefix.
curl -s -L "$BASE/" | grep -o 'href="[^"]*"'    # every link prefixed with /apps/progress
curl -si "$BASE/apps/progress/api/health" | head -n 15
```

With `APP_BASE_PATH` set, `smith serve` mounts the app under that prefix and redirects `/` → `{base}/`.

### M3 exit criteria

- [x] `make smoke` green
- [x] `make regression` green
- [x] `make test-cov` green (coverage ≥ 95% — 96.93% at M3 close)
- [x] Manual curls above once locally
- [x] No M4 work until this gate passes

---

## M4 — Localization

Automated:

```bash
pytest -q tests/smoke/test_m4_smoke.py tests/regression/test_m4_contracts.py
pytest -q tests/test_m4_translation.py tests/test_m4_number.py tests/test_m4_lang_cli.py
```

Manual (from `examples/progress`):

```bash
curl -sH 'Accept-Language: en' 'http://127.0.0.1:3000/api/locale?count=2'
curl -sH 'Accept-Language: sw' 'http://127.0.0.1:3000/api/locale?count=1&name=Ada'
python smith lang:publish
python smith make:lang fr
python smith lang:missing --locale fr
```

### M4 exit criteria

- [x] Dual-locale `/api/locale` (Accept-Language + plurals + Number)
- [x] Validation `en` wording byte-identical through translator
- [x] `lang:publish` / `make:lang` / `lang:missing`
- [x] Scaffold ships `lang/en/` + `APP_LOCALE` + SetLocale in web/api groups
- [x] Coverage ≥ 95%
- [x] No M5 work until this gate passes

---

## M5 — ORM

Automated:

```bash
pytest -q tests/test_m5_where.py tests/test_m5_orm.py tests/test_m5_migrations.py tests/test_m5_seeders.py
pytest -q tests/smoke/test_m5_smoke.py tests/regression/test_m5_contracts.py
```

Manual (from `examples/progress`):

```bash
curl -s http://127.0.0.1:3000/api/orm | python -m json.tool
curl -s http://127.0.0.1:3000/api/posts
curl -s http://127.0.0.1:3000/api/users
python smith make:model Post -m
python smith make:migration create_widgets_table
python smith make:migration add_slug_to_posts_table
python smith make:seeder UserSeeder
python smith migrate --seed
python smith db:seed
```

### M5 exit criteria

- [x] Canonical `where("col", "=", val)` plus two-arg `=` shortcut
- [x] Models, relations, eager loading, soft deletes, events
- [x] Schema + `migrate` / `migrate:rollback` round-trip
- [x] Seeders: `Seeder` call API, `db:seed`, `migrate --seed`, scaffold `DatabaseSeeder`
- [x] Living example `/api/orm` + posts/users demos (`with_("author")`, soft deletes, pivot, morphs, upsert)
- [x] Coverage ≥ 95%
- [x] Feature docs in [`website/…/articulate/`](../website/src/content/docs/articulate/) + [`database/`](../website/src/content/docs/database/) (`make docs`)
- [x] No M6 work until this gate passes

---

## M6 — Prism

Automated:

```bash
pytest -q tests/smoke/test_m6_smoke.py
pytest -q tests/test_m6_*.py
```

### M6 exit criteria

- [x] Prism full surface + progress Prism-first
- [x] Coverage 100% on `almasix.prism`; suite ≥ 98%
- [x] No M7 work until this gate passes

---

## M7 — Auth + session

Automated:

```bash
pytest -q tests/smoke/test_m7_smoke.py tests/test_m7_session_auth.py tests/test_m7_coverage_fill.py
make test-cov
```

Manual (from `examples/progress`):

```bash
# Browser: open /, Sign in, submit form (CSRF), Sign out
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3000/api/me
curl -sH 'Authorization: Bearer demo' http://127.0.0.1:3000/api/me
```

### M7 exit criteria

- [x] Cookie session + EncryptCookies + VerifyCsrfToken on `web`
- [x] Session + token guards: `attempt` / `login` / `logout` / remember-me Set-Cookie / rehash-on-login
- [x] `auth` / `auth:guard` / `guest` / `password.confirm` / `auth.basic` / `auth.start`
- [x] `Hash` (bcrypt + optional argon2id); `Password` broker; auth events; `Request.user()`
- [x] Prism `@csrf` / `@auth` / `@guest` wired via AuthServiceProvider
- [x] Progress login demo + Authentication / Hashing / Passwords / Session / CSRF docs
- [x] Coverage ≥ 98%
- [x] No M8 work until this gate passes (gate now met — M8 unblocked)

---

## M8 — Error handling + logging

- [x] `Handler` report/render + app override; polarity HTML vs JSON (no `Accept` flip)
- [x] `APP_DEBUG` web debug page gated; api debug widens `message` only
- [x] Status mapping (`ModelNotFoundError` → 404, …) + `ServiceUnavailableHttpException`
- [x] Unmatched routes: path polarity (`/api/*` JSON, else HTML 404)
- [x] `errors:publish` + default/tailwind/bootstrap bundles (CDN-free); production error views
- [x] `config/logging.py` + `log()` / `with_()` context; `report()` writes through channels
- [x] Error catalog `lang/en/errors.py`; Prism-off HTML fallback
- [x] Progress `/boom` (HTML) + `/api/explode` (JSON); Error Handling / Logging docs
- [x] Smoke `tests/smoke/test_m8_smoke.py`; coverage ≥ 98% (exceptions + log aim 100%)
- [x] No M9 work until this gate passes

---

## M9 — Console + scheduler

Automated:

```bash
pytest -q tests/smoke/test_m9_smoke.py tests/test_m9_*.py
make test-cov
```

Manual (from `examples/progress`):

```bash
smith progress:hello Almasix
smith list
smith schedule:run
smith loupe   # aliases: tinker, repl — interactive; Ctrl-D to exit
```

### M9 exit criteria

- [x] `Command` base + discovery; `smith list` / `make:command` / `inspire`
- [x] Almasix Prompts (`text`/`select`/`confirm`/`spin`/`progress` + ask/choice)
- [x] `dump()` / `dd()` (Rich CLI + web HTML / api JSON; `/dd` · `/api/dd`)
- [x] Schedule DSL + `schedule:run` / `schedule:work` + filesystem mutex
- [x] Console exceptions report through M8 Handler
- [x] `smith loupe` REPL (aliases: `tinker`, `repl`; IPython → ptpython → Rich fallback)
- [x] Progress `progress:hello` / `progress:prompts` + `routes/console.py`; smoke
- [x] Coverage ≥ 98% (`almasix.console` 100%)
- [x] No M10 work until this gate passes

---

## M10 — Filesystem

```bash
pytest -q tests/test_m10_filesystem.py tests/smoke/test_m10_smoke.py
```

### M10 exit criteria

- [x] `Storage` / `storage()` / local + public + memory (+ S3 optional)
- [x] `config/filesystems.py` + `storage:link`
- [x] UploadedFile → `put_file` / `put_file_async`
- [x] Docs + smoke; no M11 until green

---

## M11 — Queues

```bash
pytest -q tests/test_m11_queue.py tests/smoke/test_m11_smoke.py
```

### M11 exit criteria

- [x] `Job` / `ShouldQueue` / `dispatch` / sync + database drivers
- [x] `queue:work` / `listen` / `failed` / `retry` + failed jobs
- [x] Docs + smoke; no M12 until green

---

## M12 — Mail

```bash
pytest -q tests/test_m12_*.py tests/smoke/test_m12_smoke.py
```

### M12 exit criteria

- [x] `Mailable` + `Mail` façade; log / array / SMTP
- [x] Attachments + assertions; Markdown/view content
- [x] Docs + smoke; no M13 until green

---

## M13 — Notifications

```bash
pytest -q tests/test_m13_notifications.py tests/smoke/test_m13_smoke.py
```

### M13 exit criteria

- [x] `Notifiable` + mail/database/log/array channels
- [x] `MustVerifyEmail` + password-reset notification delivery
- [x] Docs + smoke; no M14 until green

---

## M14 — Helpers + Strings

```bash
pytest -q tests/test_m14_*.py tests/smoke/test_m14_smoke.py
```

### M14 exit criteria

- [x] `Arr` + misc helpers (`data_*`, `blank`, `tap`, `retry`, …)
- [x] `Str` / `Stringable` + `Number`
- [x] Docs + smoke; no M15 until green

---

## M15 — Cache

```bash
pytest -q tests/test_m15_*.py tests/smoke/test_m15_smoke.py
```

### M15 exit criteria

- [x] `Cache` façade + array / file / database stores
- [x] Atomic `add` + store-native locks; tags array-only
- [x] Docs + smoke; no M16 until green

---

## M16 — Redis

```bash
pytest -q tests/test_m16_*.py tests/smoke/test_m16_smoke.py
```

### M16 exit criteria

- [x] `Redis` façade + `config/redis.py` + `almasix[redis]`
- [x] Cache / session / queue Redis drivers (FakeRedis in CI)
- [x] Docs + smoke; no M17 until green

---

## M17 — Encryption

```bash
pytest -q tests/test_m17_*.py tests/smoke/test_m17_smoke.py
```

### M17 exit criteria

- [x] `Crypt` façade + JSON-safe encrypt (no pickle) + `encrypt_string`
- [x] `APP_PREVIOUS_KEYS` rotation; shared cipher with cookie encrypt
- [x] Docs + smoke; no M18 until green

---

## M18 — Events

```bash
pytest -q tests/test_m18_*.py tests/smoke/test_m18_smoke.py
```

### M18 exit criteria

- [x] `Event` façade + listen / dispatch / subscribe / wildcards
- [x] Queued listeners (`ShouldQueue`) + `ShouldBroadcast` stub
- [x] Docs + smoke; no M19 until green

---

## M19 — Authorization

```bash
pytest -q tests/test_m19_*.py tests/smoke/test_m19_smoke.py
```

### M19 exit criteria

- [x] `Gate` façade + Policies + `Authorizable` / `authorize`
- [x] Prism `@can` / `@cannot` + `can` middleware + `make:policy`
- [x] Docs + smoke; no M20 until green

---

## M20 — HTTP Client

```bash
pytest -q tests/test_m20_*.py tests/smoke/test_m20_smoke.py
```

### M20 exit criteria

- [x] `Http` façade + `PendingRequest` fluency (headers, auth, timeouts, bodies, attachments, RFC 6570 URL parameters)
- [x] `Response` helpers (JSON / collect / status predicates / throw policies + body truncation)
- [x] Retry (callable / list delays, throwable `when` with a reconfigurable request), `Http.pool` (concurrency + per-request options), `Http.batch`
- [x] Fakes: URL maps with real fall-through, sequences that raise when drained, stray prevention + allowlist, `recorded()` pairs + `assert_sent*`
- [x] `Http.macro`, `RequestSending` / `ResponseReceived` / `ConnectionFailed` events
- [x] Async verbs (`aget` … `aoptions`) over `httpx.AsyncClient`
- [x] Docs + smoke; no M21 until green

---

## M21 — Processes

```bash
pytest -q tests/test_m21_*.py tests/smoke/test_m21_smoke.py
```

### M21 exit criteria

- [x] `Process.run` for string (shell) and list (no shell) commands; `ProcessResult` with `successful` / `failed` / `exit_code` / `output` / `error_output` / `see_in_output` / `see_in_error_output`
- [x] `throw` / `throw_if` / `throw_unless` raising `ProcessFailedException`, which carries and proxies its result
- [x] Options: `path`, `input`, `env` (merged into the inherited environment), `timeout` (60s default), `idle_timeout`, `forever`, `quietly`, `tty`, `options`, `when` / `unless`
- [x] Real-time output callbacks receiving `("out" | "err", chunk)`; `ProcessTimedOutException` carries the partial result
- [x] `Process.start` → `InvokedProcess` with `id`, `running`, `output` / `latest_output` pairs, `signal`, `stop` (terminate then kill), `wait(callback)`
- [x] `Process.pool` / `concurrently` with `as_()` naming, results keyed by name *and* position, `running()` as a Collection, pool-wide `signal` / `stop`, keyed start callbacks
- [x] `Process.pipe` for lists and callables, feeding output into input and short-circuiting on failure
- [x] Fakes: command maps with real fall-through, `Process.result`, `Process.describe` lifecycles (`iterations` / `runs_for` / `replace_output`), `Process.sequence` raising when drained, `prevent_stray_processes`
- [x] `recorded()` pairs and the `assert_ran` / `assert_didnt_run` / `assert_ran_times` / `assert_nothing_ran` / `assert_sequences_are_empty` family
- [x] Living example: `smith progress:process`; the board marks M21 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.process`

---

## M22 — Concurrency

```bash
pytest -q tests/test_m22_*.py tests/smoke/test_m22_smoke.py
```

### M22 exit criteria

- [x] `Concurrency.run` accepting one callable, a list, or a keyed map, returning results in the same shape and the task order
- [x] Four drivers — `thread` (default), `fork`, `process`, `sync` — each resolved from `config/concurrency.py`, with `driver()`, `set_default_driver()`, `extend()`, and named entries that alias another driver
- [x] A failing task raises only once every other task has settled; a child that dies without answering is reported rather than hanging
- [x] The `process` driver rejects unpicklable tasks with an error that names the alternatives
- [x] `Concurrency.defer` returning a waitable `DeferredTasks`; `Concurrency.arun` for coroutines under ASGI
- [x] `config/concurrency.py` in the scaffold; living example `smith progress:concurrency`; the board marks M22 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.concurrency`

---

## M23 — API Resources + Serialization

```bash
pytest -q tests/test_m23_*.py tests/smoke/test_m23_smoke.py
```

### M23 exit criteria

- [x] `JsonResource` proxying attributes to the wrapped model, `to_dict(request)`, `make`, `collection`, `with_`, `additional`, `response`
- [x] The conditional family — `when` / `unless` (callable values and defaults), `merge_when` / `merge_unless`, `when_has`, `when_not_null`, `when_loaded`, `when_counted`, `when_aggregated`, `when_appended`, `when_pivot_loaded` / `when_pivot_loaded_as`
- [x] Missing values disappear and merges splice at every level, including inside nested resources, which resolve with the same request
- [x] `ResourceCollection` with `collects`, the `<Name>Resource` guess, `AnonymousResourceCollection` from `Resource.collection(...)`, `Collection` and paginator inputs
- [x] Wrapping: the `wrap` key, `without_wrapping`, `wrap_with`, no double wrapping when the payload already owns the key
- [x] Paginated collections add Laravel's `meta` (`current_page`, `per_page`, `from`, `to`, `last_page`, `total`) and `links`, with `SimplePaginator` degrading honestly
- [x] Controllers may return a resource directly — `make_response` honors the `to_response()` protocol; dates, decimals, and UUIDs render
- [x] `smith make:resource` with `--collection`; living example `smith progress:resources` and `GET /api/resources`; the board marks M23 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.http.resources`

---

## M24 — Model factories

```bash
pytest -q tests/test_m24_*.py tests/smoke/test_m24_smoke.py
```

### M24 exit criteria

- [x] `Factory` with `definition()`, `configure()`, and an immutable builder: `count`, `state`, `set`, `trashed`, `connection`, `recycle`, `after_making` / `after_creating`
- [x] States as dicts, callables (attributes, and attributes + parent), and coroutines; attributes passed to `make` / `create` apply last
- [x] `sequence`, `for_each_sequence` (the sequence sets the count), `cross_join_sequence`, and sequence steps that read their own `index`
- [x] `raw`, `make` / `make_one` / `make_many`, `create` / `create_one` / `create_many`, the `*_quietly` twins, and `lazy`
- [x] `has` (has-many, has-one, morph-many, belongs-to-many), `has_attached` with a pivot dict or callable, `for_` (belongs-to and morph-to), and the `has_<relation>` / `for_<relation>` magic methods
- [x] A batch shares one `for_()` parent; `recycle` reuses existing models rather than creating more; factory and model attribute values resolve to keys
- [x] `HasFactory` → `Model.factory(count, state)`; resolution by `<Model>Factory`, then by importing `database.factories.<model>_factory`; `new_factory`, `guess_model_names_using`, `guess_factory_names_using`, `use_namespace`
- [x] A seedable, dependency-free `Fake` with `unique()`, Laravel's camelCase spellings, and `Fake.resolve_using` to swap in Faker
- [x] `smith make:factory [--model]`, `make:model -f`, and `HasFactory` in the model stub
- [x] The example `DemoSeeder` builds every row through a factory; living example `smith progress:factories`; the board marks M24 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.orm.factories`

---

## M25 — Articulate NoSQL / document stores

```bash
pytest -q tests/test_m25_*.py tests/smoke/test_m25_smoke.py
```

### M25 exit criteria

- [x] A store-agnostic query shape (`Query` / `Condition` / `Order`) and a `DocumentStore` contract every driver satisfies
- [x] `MongoStore` over Motor (`almasix[mongodb]`): every operator translated to a Mongo filter, `and` / `or` precedence, sorts, windows, projections, `distinct`, `$inc`, index information, `raw_aggregate`
- [x] `MemoryStore` with the same semantics in-process — unique indexes, dotted paths, `None`-safe sorting — so tests and demos need no server
- [x] `DocumentBuilder`: the `where` family, dotted fields, ordering, windows, `select` / `distinct`, scopes, `when` / `unless` / `tap`, chunking, `lazy`, both paginators, `insert` / `update` / `upsert` / `increment` / `delete` / `truncate`
- [x] Document-native filters — `where_regex`, `where_exists_field`, `where_all`, `where_size` — and `where_raw` taking an engine filter or a predicate
- [x] SQL-only calls raise `UnsupportedQueryError` naming the alternative (`join`, `group_by`, `having`, `where_column`, `union`, raw SQL)
- [x] `Document` keeps every `Model` behaviour — casts, accessors, events, observers, soft deletes, serialization, factories — with `_id` keys, collection naming, and per-instance connections
- [x] `EmbeddedDocument` with `embeds_one` / `embeds_many`, write-back through the parent, in-memory filtering, and declared fields
- [x] References load across stores, including document → SQL, with eager loading and a document-native `with_count`
- [x] `DatabaseManager.store()` / `is_document()` / `document_connection_names()`; asking for a store as a connection (or the reverse) is refused by name
- [x] `smith make:document [--factory|--embed]`, `documents:index [--pretend]`, `documents:show`; indexes declared on the model
- [x] Living example: `Activity` on a document store, `smith progress:documents`, `GET /api/documents`; the board marks M25 complete
- [x] Docs + smoke; SQL regressions green; 100% line and branch coverage on `almasix.orm.documents`

---

## M26 — Broadcasting

```bash
pytest -q tests/test_m26_*.py tests/smoke/test_m26_smoke.py
```

### M26 exit criteria

- [x] `ShouldBroadcast`, `ShouldBroadcastNow`, `ShouldBroadcastAfterCommit`; `broadcast_on`, `broadcast_as`, `broadcast_with`, `broadcast_when`, and a payload reflected off the event when it declares none
- [x] `Channel`, `PrivateChannel`, `PresenceChannel`, `EncryptedPrivateChannel` — names from strings, models, and channel objects, prefixed once
- [x] `broadcast()` returning a `PendingBroadcast` that sends on `send()`, on `await`, or when it falls out of scope; `to_others()` excludes the caller's socket; `via()` picks the connection
- [x] Drivers: `log` and `null`, an in-process `websocket` server, `redis` pub/sub, `pusher` over its signed REST API (chunking long channel lists), and `Broadcast.extend()` for a sixth
- [x] `routes/channels.py` loaded by the provider so console and HTTP see the same channels; wildcard patterns, route-model binding from type hints, channel classes from the container, per-channel guards
- [x] Presence channels return a member array; a refusal is a refusal (`False` / `None`) and answers 403
- [x] `POST /broadcasting/auth` and `/broadcasting/user-auth` reply in Pusher's signed format; encrypted channels seal the payload with the application key
- [x] `Route.websocket()` and kernel support; `/broadcasting/socket` speaks `subscribe`, `unsubscribe`, `ping`, `client-*`, and member added / removed
- [x] Queued broadcasts travel as a `BroadcastEvent` job with a JSON payload; `ShouldBroadcastNow` skips the queue; `ShouldBroadcastAfterCommit` waits for `Connection.after_commit()`
- [x] `BroadcastsEvents` / `BroadcastsEventsAfterCommit` on models — created, updated, trashed, restored, deleted — and the `broadcast` notification channel
- [x] `Broadcast.fake()` with `assert_broadcast`, `assert_broadcast_on`, `assert_nothing_broadcast`, and the recorded frames
- [x] `smith make:channel`, `channel:list`, and `config/broadcasting.py` + `routes/channels.py` in the scaffold
- [x] Living example: `PostPublished`, a broadcasting `Comment`, `smith progress:broadcast`, `GET /api/broadcast`; the board marks M26 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.broadcasting`

---

## M27 — Search

```bash
pytest -q tests/test_m27_*.py tests/smoke/test_m27_smoke.py
```

### M27 exit criteria

- [x] `Searchable` indexes on `saved`, removes on `deleted`, returns on `restored`; `should_be_searchable()` takes a row out and `search_index_should_be_updated()` skips a write that changes nothing indexed
- [x] The model contract: `to_searchable_array`, `scout_metadata`, `searchable_as` (with the configured prefix), `get_scout_key` / `get_scout_key_name`, `searchable_using`
- [x] `searchable()` / `unsearchable()` on a model, on a query, and on a `Collection`; `make_all_searchable` / `remove_all_from_search`; `make_all_searchable_using` to shape the import query
- [x] `without_syncing_to_search()` as a context manager, and `disable_search_syncing()` / `enable_search_syncing()` as switches — a pause covers saves, deletes, and restores alike
- [x] The builder: `where`, `where_in`, `where_not_in`, `order_by` / `latest` / `oldest`, `take`, `within`, `options`, `query_using`, `when` / `unless` / `tap`, `get` / `first` / `keys` / `raw` / `count` / `cursor`, `paginate` / `simple_paginate` and their `_raw` twins
- [x] Engines: `database` (`LIKE`, prefix matching, and the dialect's own full text on PostgreSQL and MySQL), `collection` (filtered in Python), `meilisearch` (its REST API over the HTTP client), `null`; `Scout.extend()` registers a fifth and an unknown driver names the alternatives
- [x] Queued indexing through `MakeSearchable` / `RemoveFromSearch` carrying keys, not models; without a queue configured the write still happens
- [x] `after_commit` indexing on the back of `Connection.after_commit()`, with `flush_search()` for a test that is about to assert on the index
- [x] Soft deletes: trashed rows leave the index by default, or stay flagged `__soft_deleted` when configured, and `with_trashed()` / `only_trashed()` find them
- [x] `Scout.fake()` with `assert_synced`, `assert_removed`, `assert_flushed`, `assert_nothing_synced`, `assert_searched`, `assert_search_count`
- [x] Eight commands — `scout:import`, `scout:queue-import`, `scout:flush`, `scout:index`, `scout:delete-index`, `scout:delete-all-indexes`, `scout:sync-index-settings`, `scout:status` — and `config/scout.py` in the scaffold
- [x] Living example: a searchable `Post`, `smith progress:search`, `GET /api/search`; the board marks M27 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.scout`

---

## M28 — Testing toolkit

```bash
pytest -q tests/test_m28_testing.py tests/smoke/test_m28_smoke.py
```

### M28 exit criteria

- [x] `TestCase` is a class pytest collects: an autouse lifecycle runs `setup()` / `teardown()` coroutines, `create_application()` runs the app's own `bootstrap/app.py` when there is one, and an `almasix_base_path` fixture decides the path when a fixture must
- [x] `use_refresh_database` migrates a fresh database per test; `use_database_transactions` rolls each test back; both also exist as plain functions
- [x] `TestClient` drives the ASGI app in-process over the real middleware stack — every verb and its `*_json` twin, form bodies, raw bodies, uploads, query params
- [x] Headers, bearer and basic tokens, cookies that persist between requests, `with_session`, `acting_as` on any guard, `following_redirects`, `from_`
- [x] Status assertions: `assert_ok` through `assert_server_error`, `assert_no_content` (status *and* an empty body), `assert_redirect` / `assert_location` / `assert_redirect_contains`; a failure quotes the body
- [x] Headers, cookies, content type, and downloads; `assert_see` / `assert_see_text` / `assert_see_in_order` with HTML escaping, `assert_content`, `assert_streamed_content`
- [x] JSON: `assert_json` (loose and strict), `assert_exact_json`, dotted `assert_json_path` with a value or a callback, `assert_json_missing_path`, fragments, counts, `*`-wildcard `assert_json_structure`, array / object shape
- [x] Validation (`assert_valid` / `assert_invalid` by key, keys, or key → message), session assertions, and view assertions reading what Prism was given
- [x] `artisan()` — `expects_question` / `expects_confirmation` / `expects_choice` / `expects_output` / `doesnt_expect_output` / `expects_table`, `assert_exit_code` / `assert_successful` / `assert_failed` / `assert_output_contains` / `assert_asked` / `assert_nothing_asked`; an unanswered question takes the command's default
- [x] Database: `assert_database_has` / `missing` / `count` / `empty` (by table or model), `assert_model_exists` / `missing`, `assert_soft_deleted` / `not_soft_deleted`; a failure prints the rows the table holds
- [x] `fake()` / `fakeable()` / `restore_fakes()` reach mail, queue, notification, storage, event, http, process, broadcast, and scout; `FakeQueue`, `FakeNotifications`, and `FakeDisk` are new here
- [x] `without_middleware()` / `with_middleware()` by alias, by class, or all of it, on the back of `HttpKernel.skip_middleware()`
- [x] `travel` / `travel_to` / `freeze_time` / `frozen_time` / `travel_back` move the clock `now()` and model timestamps read, and put it back
- [x] `tests/` with a `conftest.py` and two example tests in the scaffold, `pytest` configured in its `pyproject.toml`, `smith make:test [--unit]`, and `smith test`
- [x] Living example: the progress app's own suite runs green under `smith test`, `smith progress:testing` demonstrates the toolkit; the board marks M28 complete
- [x] Docs + smoke; 100% line and branch coverage on `almasix.testing`

---

## M30 — Smith Console exhaust

```bash
pytest -q tests/test_m30_*.py tests/smoke/test_m30_smoke.py
```

### M30 exit criteria

- [x] Laravel signature grammar (optional / default / array arguments, option shortcuts, arrays, descriptions)
- [x] `Command` I/O surface, `fail`, `trap`, `with_progress_bar`, `Isolatable`, `PromptsForMissingInput`
- [x] `Artisan` façade — `call`, `output`, `queue`, closure commands with container injection
- [x] Console events (`ConsoleStarting`, `CommandStarting`, `CommandFinished`) + `--isolated` locking
- [x] One surface: the ~30 Typer callbacks are `Command` classes, `cli.py` declares none of its own, and what the front door offers is exactly what the kernel knows
- [x] Discovery survives a broken command module, names it on every run rather than only on `list`, and reports a module discovered mid-import instead of dropping its commands
- [x] `--help` is rendered from the signature — usage line, arguments, options, defaults, shortcuts, and aliases
- [x] Generators run in a bare directory (`boots_application = False`); commands that need an application boot before `handle()`
- [x] Stub tree: every generator renders a `.stub`, `smith stub:publish` copies them into `stubs/`, and a published stub wins
- [x] `ServiceProvider.publishes()` + `smith vendor:publish` by provider, by tag, with `--force` / `--existing`; the framework declares `almasix-stubs` and `almasix-lang`
- [x] Loupe allow-list: `config/loupe.py` `commands` / `alias` / `dont_alias`, with commands as callables in the shell
- [x] The built-in catalogue — 102 commands (84 at M30, plus what later milestones brought), including `about`, `help`, `env`, `docs`, `route:list`, `config:show`, `db:show` / `db:table` / `db:monitor` / `db:wipe`, `model:show`, `migrate:install` / `reset` / `refresh`, the `queue:*` maintenance set, `env:encrypt` / `env:decrypt`, `cache:*`, `view:*`, `optimize`, `storage:unlink`, and the eleven `make:*` generators
- [x] `console` rewritten in Laravel's Artisan section order with a generated command reference; the smoke contract fails if a section moves, a command is missing a row, or a description drifts from the command's own
- [x] Living example: `smith progress:console` reports the one surface, the stub count, and the publish tags; the board marks M30 complete
- [x] Deliberate deviations recorded in `docs/PLAN.md` with reasons — `config:cache` / `route:cache` / `event:cache` measured and declined, `view:cache` verifying rather than persisting, `db:show` without a size column, `db:wipe` refusing `--drop-views`
- [x] 100% line and branch coverage on `almasix.console` and `almasix.smith`, the interactive prompt layer included: `tests/test_m9_prompts_driven.py` types into a real terminal over a pipe (arrows, space, Ctrl-C, corrections) instead of taking the non-interactive branch, and fails rather than hangs when a prompt is left waiting

---

## M40 — Articulate model exhaust

```bash
pytest -q tests/test_m40_*.py tests/smoke/test_m40_smoke.py
```

### M40 exit criteria

- [x] Casting: `Attribute` objects, custom / inbound casts, castables, `encrypted*`, `hashed`, enum collections, date formats, `with_casts` / `merge_casts`
- [x] Serialization: `append` family, `merge_hidden` / `merge_visible`, `to_json(**options)`, `visible` honored by appends and relations
- [x] Collections: `find` / `fresh` / `to_query`, model-keyed `only` / `except_` / `diff` / `intersect` / `unique` / `contains`, custom `collection_class`
- [x] Model surface: `HasUuids` / `HasUlids`, strictness switches, `unguarded`, `without_timestamps`, quiet writes, `without_events`
- [x] Pruning: `Prunable` / `MassPrunable` + `smith model:prune` (`--model`, `--except`, `--chunk`, `--pretend`)
- [x] Walking large sets: streaming `cursor()`, `lazy` / `lazy_by_id`, `chunk_by_id` / `each_by_id`
- [x] Living example demonstrates appends + pruning; docs published; `almasix.orm` at 100%

---

## M41 — Relationship exhaust

```bash
pytest -q tests/test_m41_*.py tests/smoke/test_m41_smoke.py
```

### M41 exit criteria

- [x] Has one of many: `of_many` / `latest_of_many` / `oldest_of_many` / `one()`, aggregate mappings, constraining callbacks, morph support, one row per parent on eager loads
- [x] Default models: `with_default()` on `belongs_to` / `has_one` / `morph_one`, with mapping, callable, and empty forms, applied to eager loads
- [x] Chaperone: `chaperone()` hydrates the inverse relation on `has_many` / `has_one` / `morph_many` / `morph_one` children
- [x] Existence querying: `or_has` / `or_doesnt_have` / `or_where_has` / `or_where_doesnt_have`, dotted nesting, `where_relation` / `or_where_relation`, `with_where_has`, and the eight morph variants plus `where_morph_relation`
- [x] Aggregates: `with_count` / `with_sum` / `with_avg` / `with_min` / `with_max` / `with_exists` / `with_aggregate` with `as` aliases and callbacks; `load_count` / `load_sum` / `load_avg` / `load_min` / `load_max` / `load_exists` / `load_aggregate` on `Model` and `Collection`
- [x] Pivots: `pivot` accessor with `as_` renaming, `using` custom `Pivot` models, `with_timestamps`, `where_pivot_in` / `not_in` / `null` / `not_null` / `between`, `order_by_pivot`, per-id attach attributes, `sync` `updated` results, `sync_without_detaching`
- [x] Morph maps: `morph_map` / `enforce_morph_map`, `morph_to` without an explicit types dict, null types resolving to `None`
- [x] Touching: `touches`, `without_touching`, `without_touching_on`
- [x] Relation write helpers: `make` / `make_many` / `create_quietly` / `first_or_new` / `find_or_new` / `update_or_create`
- [x] Whole-graph writes: `push()` saves loaded relations depth-first, stops on a cancelled save, and survives chaperoned cycles
- [x] Parent queries: `where_belongs_to` / `or_where_belongs_to` with a guessed or named relation, one parent or many
- [x] Dynamic relations: `resolve_relation_using` relations query, eager-load, and still refuse to lazy-load
- [x] Morph loading: `load_morph` / `load_morph_count` take a relation list per target class on both `Model` and `Collection`
- [x] `articulate/relationships` rewritten in Laravel section order, with the N+1 deviation documented and the two unimplemented sections (`withAttributes`, `automaticallyEagerLoadRelationships`) named
- [x] Living example: `/api/orm` relationship tour (pivot objects, `latest_of_many`, `with_default`, `chaperone`, aggregates, existence queries); milestone board covers M0–M50 with `partial` statuses

---

## M42 — Query builder + database layer exhaust

```bash
pytest -q tests/test_m42_*.py tests/smoke/test_m42_smoke.py
cd examples/progress && python smith progress:queries
```

### M42 exit criteria

- [x] Where clauses: `where_not`, `where_any` / `where_all` / `where_none`, `where_in` with a subquery, `where_integer_in_raw`, `where_null_safe_equals`, `where_between_columns` / `where_value_between`, `where_column`, `where_like` with portable case sensitivity, and the `or_` twin of each
- [x] Date helpers: `where_date` / `where_month` / `where_day` / `where_year` / `where_time`, and `where_past` / `where_future` / `where_now_or_*` / `where_today` / `where_before_today` / `where_after_today` / `where_today_or_*`
- [x] JSON: reading with Laravel's arrow syntax, `where_json_contains` / `doesnt_contain`, `where_json_contains_key`, `where_json_length`, and updating a path without disturbing the rest of the document
- [x] Existence and subqueries: `where_exists` / `where_not_exists`, a subquery on either side of a comparison, `select_sub` / `add_select_sub` / `order_by_sub`, and correlation against the outer table
- [x] Engine-specific clauses in one grammar module: full text (MySQL/MariaDB `MATCH … AGAINST`, PostgreSQL `to_tsvector`), vector distance (pgvector `<=>`, MariaDB `VEC_DISTANCE_COSINE`), JSON containment three ways; an engine without the operation raises `UnsupportedByDialectError`
- [x] Joins: closure join clauses with `on` / `or_on` and the where family, `join_sub` / `left_join_sub` / `right_join_sub` / `cross_join_sub`, `join_lateral` / `left_join_lateral`, `from_sub`; `right_join` compiles as the equivalent left join
- [x] Unions, ordering and paging applied to the combined result, pessimistic locking (`lock_for_update` / `shared_lock` / `lock`), `order_by_raw` / `group_by_raw` / `having_raw` / `having_between`, `reorder_desc`
- [x] Writes: `insert_or_ignore`, `insert_using`, `update_or_insert`, `increment_each` / `decrement_each`, `truncate` with the counter reset, `delete(key)`
- [x] Reads and components: `sole` (with `MultipleRecordsFoundError`), `implode`, `average`, `pipe`, `tap`, `with_attributes` seeding what a scoped query creates
- [x] Debugging: `to_sql` leaves placeholders, `to_raw_sql` writes values in, `get_bindings`, `dump` / `dump_raw_sql` / `dd` / `dd_raw_sql`
- [x] Database layer: read/write connections with `sticky`, `DB.select` / `select_one` / `scalar` / `insert` / `update` / `delete` / `statement` / `unprepared`, `DB.listen`, `when_querying_for_longer_than` with `total_query_duration`, `DB.pretend`
- [x] Transactions: the block form, the callable form with deadlock retries, manual `begin_transaction` / `commit` / `rollback` with SAVEPOINT nesting, `transaction_level`, and `after_commit` (which runs now outside a transaction and is discarded on rollback)
- [x] Pooled connections: a `direct` block is used by schema work, `db:show` / `db:table` / `db:monitor`, and `db`
- [x] `db` opens the engine's own client (`sqlite3`, `mysql`, `psql`, `sqlcmd`), takes `--read` / `--write` / `--pooled`, and says which client it looked for when one is missing
- [x] `database/index` and `database/queries` rewritten in the Laravel section order
- [x] Living example: `smith progress:queries`; the board marks M42 complete
- [x] 100% line and branch coverage on `almasix.orm.builder`, `almasix.orm.connection`, `almasix.orm.facade`, `almasix.orm.grammar`, and `almasix.console.commands.db`

---

## M43 — Schema, migrations, and pagination exhaust

```bash
pytest -q tests/test_m43_*.py tests/smoke/test_m43_smoke.py
cd examples/progress && python smith progress:schema
```

### M43 exit criteria

- [x] The column catalogue: every width of integer and its `unsigned_` twin, `char` / the four text sizes, `double` / `real` / `unsigned_decimal`, `enum` and `set`, `json` / `jsonb`, the date family with its `*_tz` variants, `year` / `time`, `binary`, `uuid` / `ulid` / `ip_address` / `mac_address` / `remember_token`, the four `*morphs` pairs, `foreign_uuid` / `foreign_ulid` / `foreign_id_for`, `vector` / `geometry` / `geography`, and `raw_column`
- [x] Each type lands in the engine's own words: `TINYINT` on MySQL, `JSONB` and native `UUID` on PostgreSQL, a check constraint where `enum` has no type, `INTEGER` keys on SQLite because that is the only width it counts up
- [x] Modifiers: `unsigned`, `comment`, `charset` / `collation`, `first` / `after` / `before`, `invisible`, `use_current` / `use_current_on_update`, `virtual_as` / `stored_as`, `generated_as` / `always`, `auto_increment` / `start_from`; `default()` writes a **server** default, so a row inserted by anything else gets it
- [x] `change()` restates a column, compiled for MySQL (`MODIFY`), PostgreSQL (a statement per part), SQL Server, and Oracle; SQLite raises rather than pretending
- [x] Dropping: `drop_index` / `drop_unique` / `drop_primary` / `drop_foreign` / `drop_constrained_foreign_id`, `rename_index`, and the convenience pairs `drop_morphs` / `drop_timestamps` / `drop_soft_deletes` / `drop_remember_token`
- [x] `Schema` gained `rename`, `create_if_not_exists`, `drop_all_tables` (with foreign keys off, so order does not matter), `has_columns`, `has_index` by column list, `column_type`, `get_indexes`, `get_foreign_keys`, `get_views`, `when_table_has_column` / `when_table_doesnt_have_column`, `disable` / `enable_foreign_key_constraints`, and `without_foreign_key_constraints`
- [x] DDL runs through the connection rather than its own engine, so it joins the surrounding transaction and `DB.pretend` prints it
- [x] Migrations: per-migration transactions where the engine rolls DDL back, `connection` and `within_transaction` and `should_run` on the base class, `MigrationStarted` / `MigrationEnded` / `NoPendingMigrations` on the event bus, millisecond timings, several migration directories, and quoting that works on MySQL
- [x] Squashing: `schema:dump` writes `database/schema/{connection}-schema.sql` (read back through the inspector, so no client binary is needed), `--prune` removes what it stands in for, and `migrate --schema-path` replays it on an empty database
- [x] Command flags: `migrate` takes `--step` / `--pretend` / `--path` (several) / `--database` / `--force` / `--graceful` / `--schema-path`; `migrate:rollback` takes `--step` (counting migrations, as Laravel does) / `--batch` / `--pretend`; `migrate:fresh` takes `--step`; `migrate:status` shows batches and filters with `--pending`
- [x] The production guard asks only in production for `migrate` / `migrate:rollback` / `migrate:fresh`, and always for `migrate:reset` / `migrate:refresh`
- [x] Pagination: `paginate` reads the page from the request and will take a total it already has, `simple_paginate` skips the count, and `cursor_paginate` compares the ordered columns lexicographically — several `order_by` clauses page correctly, and a write mid-read does not shift the window
- [x] Paginators know their URL: `url`, `first` / `last` / `next` / `previous_page_url`, `get_url_range`, `appends`, `with_query_string`, `with_path`, `fragment`, `through`, `on_each_side`, and Laravel's JSON shape from `to_dict`
- [x] `links()` renders through Prism; the Tailwind and Bootstrap 5 views ship with the framework, behind the application's view path so an app can replace them
- [x] `database/migrations` and `database/pagination` rewritten in the Laravel section order
- [x] Living example: `smith progress:schema`; the board marks M43 complete, and M5 with it
- [x] 100% line and branch coverage on `almasix.orm.blueprint`, `almasix.orm.schema`, `almasix.orm.migration`, and `almasix.orm.pagination`

---

## M49 — Support Collections exhaust

```bash
pytest -q tests/test_m49_*.py tests/smoke/test_m49_smoke.py
```

### M49 exit criteria

- [x] Method Listing closed: `average`, `dd`, `dump`, and `lazy` were the remaining gaps
- [x] Higher order messages: the 24 documented methods answer both forms — a callable member is invoked, anything else is read, including mapping keys and model attributes; filtering methods use the member as a predicate
- [x] An empty collection answers either form rather than deciding which one crashes
- [x] `LazyCollection` over an iterable or generator function, with the whole chainable surface and `remember()` for a second pass
- [x] `AsyncLazyCollection` over an async source with awaited terminals, returned by `Model.cursor()` / `lazy()` / `lazy_by_id()`; `async for` over them unchanged
- [x] Lazy-only methods: `take_until_timeout` (seconds or a datetime), `tap_each`, `throttle`, `with_heartbeat`; pauses honoured through later operations and in the pipeline tail
- [x] Named deviation: operations needing every item (sorting, grouping) are absent from lazy collections; `collect()` materialises
- [x] `collections` documented as a section per method, alphabetically, plus Keys / Creating / Extending / Higher order messages / Lazy collections. The smoke contract fails if a public method loses its section or a section names a method that does not exist
- [x] 100% line and branch coverage on `almasix.support.collection` and `almasix.support.lazy`


---

## M50 — Helpers, `Str`, and `Stringable` exhaust

```bash
pytest -q tests/test_m50_*.py tests/smoke/test_m50_smoke.py
```

### M50 exit criteria

- [x] `Str` closed: `doesnt_start_with`, `doesnt_end_with`, `initials`, `match`, `match_all`, `is_match`, `ucwords`, each with a camelCase alias
- [x] `Stringable` delegates the whole `Str` surface generically — the subject binds wherever it sits in the signature, string results come back wrapped, and a parameterised test proves the fluent and static forms agree
- [x] `Stringable` is immutable: every method returns a new instance, and it is hashable to match its equality
- [x] Fluent-only methods: `new_line`, `strip_tags`, `split`, `test`, `to_base` / `from_base`, `hash`, `encrypt` / `decrypt`, and the `when_*` conditional family
- [x] `Arr` closed: typed reads (`array`, `boolean`, `integer`, `float`, `string`), `from_`, `has_all`, `every`, `some`, `sole`, `partition`, `push`, `select`, `only_values`, `except_values`
- [x] `Number` closed: `spell_ordinal`, `parse_int`, `parse_float`
- [x] Global helpers over surfaces that already ship: `app`, `resolve`, `request`, `response`, `back`, `session`, `old`, `cookie`, `logger`, `info`, `report`, `bcrypt`, `csrf_field`, `method_field`, `validator`, `policy` — with the request `ContextVar`, response factory, redirect flashing, and cookie jar under them
- [x] Parity gaps the docs rewrite exposed are fixed: `data_get` wildcards, `data_set` writing into lists, `Arr.to_css_styles` reading Laravel's switched-style shape, the pad family repeating the pad string, `Str.char_at` counting back from the end
- [x] `helpers` and `strings` documented a section per method (377), alphabetical within each group, in Laravel's grouping; the smoke contract fails if a public method loses its section or a section names a method that does not exist
- [x] Living example: `smith progress:collections` (higher order messages, a lazy pipeline reading 12 of a million) and `smith progress:helpers` extended with the M50 surface; the board marks M49 and M50 complete with proof naming both commands
- [x] Deviations named where Python differs: Pydantic rules for `validator`, `from_` for `from`, keyword-only flags, and the utilities Almasix has not built (Benchmarking, Dates, Deferred Functions, Lottery, Pipeline, Sleep, Timebox)

---

## M31 — Task Scheduling exhaust

```bash
pytest -q tests/test_m31_*.py tests/smoke/test_m31_smoke.py
```

### M31 exit criteria

- [x] The frequency table closed: every method from `every_second` to `yearly_on`, in snake_case with Laravel's camelCase spelling as an alias; frequencies splice cron fields so they combine
- [x] `last_day_of_month` reads the calendar at run time, so it is right in February and right across a month boundary
- [x] Sub-minute tasks: `every_second` … `every_thirty_seconds`; `schedule:run` stays inside the minute and wakes on each task's seconds; `schedule:interrupt` stops it, scoped to the minute it was sent in
- [x] Constraints: `weekdays` / `weekends` / the seven named days / `days` / `days_of_month`, `between` and `unless_between` (including windows crossing midnight), `when` / `skip` taking a callable or a boolean, `environments`, `timezone`
- [x] Locks: `without_overlapping(minutes)` over the cache with a filesystem fallback, `on_one_server` claiming per minute, `name()` required before a closure or job may claim, `use_cache` choosing the store, `schedule:clear-cache` releasing what a stuck task left
- [x] `run_in_background` runs tasks simultaneously in a worker thread — the deviation named, since a thread cannot outlive its interpreter
- [x] Maintenance mode: `smith down` / `smith up` and `even_in_maintenance_mode`; the HTTP half named as owed by M34
- [x] Groups hold attributes on the schedule and replay them onto every task defined inside, nesting included
- [x] Hooks in Laravel's order, a hook taking a parameter handed the output as a `Stringable`, and the eight-method ping family over the M20 client
- [x] Output to a file (replacing or appending) and to an inbox (always or only on failure), captured around every kind of task
- [x] Tasks from a callback (sync or `async`), a Smith command, a queued job with its queue and connection, and a shell line; plus `Artisan.command(...).schedule([...])` and `Application.configure(...).with_schedule(...)`
- [x] The five lifecycle events on the event bus, with `ScheduledTaskSkipped` carrying why
- [x] Commands: `schedule:run` / `work` / `list` / `test` / `interrupt` / `clear-cache`, and loading `routes/console.py` twice no longer schedules everything twice
- [x] `scheduling` rewritten to 640 lines in Laravel's section order; the smoke contract fails if a documented method loses its mention, a section disappears, or a command loses its registration
- [x] Living example: `smith progress:schedule` (combining frequencies, a calendar-aware month end, a tick showing hooks, a skip reason, and shell output) and `smith schedule:list` over the app's own schedule; the board marks M31 complete with proof naming both
- [x] 100% line and branch coverage on `almasix.console.scheduling`

---

## Out of scope until later milestones

- Digging Deeper: package guidelines (M29) — processes, concurrency, API resources, factories, Articulate NoSQL, broadcasting, search, and the testing toolkit have shipped (M21–M28)
- Promoted out of "Later" and now scheduled: console exhaust (M30), scheduler exhaust (M31), interactive installer + stacks (M32), router DX / named routes (M33), security headers + CORS (M34), rate limiting (M35), starter kits (M36), tokens / OAuth / social auth (M37), deployment (M38), docs versioning + Prologue (M39)
- IDE and editor tooling (M45–M48): Prism grammars + formatter, `almasix-lsp`, VS Code / PyCharm integrations + `ide:stubs`, MCP server — sequenced after the parity milestones, since the language server indexes vocabulary those milestones are still changing
- Localization + Mutators/Casts **docs** (code already shipped M4/M5)
- Additional NoSQL engines beyond Mongo, and other Later extras — see [`PLAN.md`](PLAN.md)
