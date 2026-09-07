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
| S1 | `avalon version` | Exit 0, `Avalon 0.1.0` |
| S2 | `avalon new <app>` | Tree with `grail`, `bootstrap/app.py`, controllers |
| S3 | Invalid name / non-empty dir | Non-zero exit |
| S4 | `GET /` on generated ASGI | `200` + Welcome JSON |
| S5 | Grail `version` | Exit 0 |
| S6 | `serve` without bootstrap | Exit 1 |
| S7 | `serve` with scaffold | Calls Uvicorn `bootstrap.app:asgi` |

### Manual (once per M0 cut)

```bash
avalon new smoke_blog --path /tmp
cd /tmp/smoke_blog
pip install -e /path/to/avalon && pip install -e .
python grail serve
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
avalon new kernel_blog --path /tmp
cd /tmp/kernel_blog
pip install -e /path/to/avalon && pip install -e .
python -c "from avalon.framework import Application; a=Application('.').bootstrap(); print(a.config.get('app.name'), a.is_booted)"
python grail serve
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
| H2 | Scaffolded app `GET /` | 200 **HTML** (`text/html`) via Avalon router/controllers |
| H3 | Groups + middleware | Nested prefixes concatenate; middleware accumulates outer→inner |
| H4 | `HttpException` (API) | JSON `{message, status}`, **with route middleware headers applied** |
| H5 | `Request` bag | `all`/`input`/`query`/`post`/`only`/`except_`/`route`; body wins over query |
| H6 | Controller capture | `Request` + route params + container type hints |
| H7 | Route polarity | `web.py` → HTML; `api.py` → JSON (Content-Type asserts) |
| H8 | Middleware groups | `web` / `api` in `config/http.py`; group name expands to its members |

### Manual (once per M2 cut)

From `examples/progress` after `python grail serve` (see that app’s README for the full checklist):

```bash
BASE=http://127.0.0.1:3000
curl -si "$BASE/" | head -n 20                   # text/html
curl -si "$BASE/progress" | head -n 20           # text/html
curl -si "$BASE/api/health" | head -n 20         # application/json + X-Avalon-Demo
curl -s "$BASE/api/items/42?q=hello" -H "Authorization: Bearer secret" | python -m json.tool
curl -s -X POST "$BASE/api/bag?q=1" -H "Content-Type: application/json" -d '{"name":"bag","q":"body"}' | python -m json.tool
curl -s "$BASE/api/di" | python -m json.tool
curl -s -X POST "$BASE/api/items" -H "Content-Type: application/json" -d '{"name":"avalon"}' | python -m json.tool
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
| V4 | Message wording | `required` / `min` / `max` / `boolean` / `array` use Avalon’s default copy; `attributes()` + `messages()` override |
| V5 | `authorize()` false | 403 `{message: "This action is unauthorized.", status}` |
| V6 | `url()` / `asset()` / `redirect()` | Every link carries `APP_BASE_PATH`; absolute URLs pass through untouched |
| V7 | Generated app under a subpath | Welcome page emits `/apps/x/api/health`, never `/api/health` |

### Manual (once per M3 cut)

From `examples/progress` after `python grail serve`:

```bash
BASE=http://127.0.0.1:3000
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"avalon","count":"3","flag":"true"}' | python -m json.tool   # coerced types
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -d '{"name":"a","count":0,"tags":"nope"}' | python -m json.tool          # 422 messages
curl -s -X POST "$BASE/api/items" -H 'Content-Type: application/json' \
  -H 'X-Demo-Forbid: 1' -d '{"name":"avalon"}' | python -m json.tool       # 403 authorize()

# Subpath links: set APP_BASE_PATH=/apps/progress in .env, restart, then
# open http://127.0.0.1:3000/apps/progress/ (site root redirects there).
# Generated links and the ASGI mount share the same prefix.
curl -s -L "$BASE/" | grep -o 'href="[^"]*"'    # every link prefixed with /apps/progress
curl -si "$BASE/apps/progress/api/health" | head -n 15
```

With `APP_BASE_PATH` set, `grail serve` mounts the app under that prefix and redirects `/` → `{base}/`.

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
python grail lang:publish
python grail make:lang fr
python grail lang:missing --locale fr
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
python grail make:model Post -m
python grail make:migration create_widgets_table
python grail make:migration add_slug_to_posts_table
python grail make:seeder UserSeeder
python grail migrate --seed
python grail db:seed
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

## M6 — Caliburn

Automated:

```bash
pytest -q tests/smoke/test_m6_smoke.py
pytest -q tests/test_m6_*.py
```

### M6 exit criteria

- [x] Caliburn full surface + progress Caliburn-first
- [x] Coverage 100% on `avalon.caliburn`; suite ≥ 98%
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
- [x] Caliburn `@csrf` / `@auth` / `@guest` wired via AuthServiceProvider
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
- [x] Error catalog `lang/en/errors.py`; Caliburn-off HTML fallback
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
grail progress:hello Avalon
grail list
grail schedule:run
grail fiddle   # aliases: tinker, repl — interactive; Ctrl-D to exit
```

### M9 exit criteria

- [x] `Command` base + discovery; `grail list` / `make:command` / `inspire`
- [x] Avalon Prompts (`text`/`select`/`confirm`/`spin`/`progress` + ask/choice)
- [x] `dump()` / `dd()` (Rich CLI + web HTML / api JSON; `/dd` · `/api/dd`)
- [x] Schedule DSL + `schedule:run` / `schedule:work` + filesystem mutex
- [x] Console exceptions report through M8 Handler
- [x] `grail fiddle` REPL (aliases: `tinker`, `repl`; IPython → ptpython → Rich fallback)
- [x] Progress `progress:hello` / `progress:prompts` + `routes/console.py`; smoke
- [x] Coverage ≥ 98% (`avalon.console` 100%)
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

- [x] `Redis` façade + `config/redis.py` + `avalon[redis]`
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

## Out of scope until later milestones

- Digging Deeper: events, authorization, HTTP client, processes, concurrency, API resources, factories, **Articulate NoSQL (M25)**, broadcasting, search, testing toolkit, package guidelines (M18–M29)
- Localization + Mutators/Casts **docs** (code already shipped M4/M5)
- Additional NoSQL engines beyond Mongo, and other Later extras — see [`PLAN.md`](PLAN.md)
