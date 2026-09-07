# Avalon

Python web framework with Adonis-class DX, built on FastAPI/Starlette — inspired by Laravel’s application shape.

| Piece | Name |
| --- | --- |
| Framework | Avalon (`avalon`) |
| Create apps | `avalon new` |
| In-app CLI | **Grail** — `grail …` (or `python grail …` via the root script) |
| View engine | Caliburn (`avalon.caliburn`) — templates use `.cal.html` |
| ORM | Articulate (`avalon.orm`) |

## Canonical plan

**[`docs/PLAN.md`](docs/PLAN.md)** is the binding architecture and milestone document. Follow it strictly unless the plan is deliberately revised.

**[`website/`](website/)** — published documentation for application developers (Astro Starlight). Run `make docs`.

**[`docs/SMOKE.md`](docs/SMOKE.md)** — smoke + regression gates. Coverage **≥ 98%** on the full suite (`make test-cov`); aim for **100%**.

## Status

**Status:** M0–M19 closed (through Authorization). Living example: [`examples/progress`](examples/progress). Next: **M20 — HTTP Client**.

## Quick start (dev)

```bash
cd /path/to/avalon
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
avalon version
grail version          # same as: python grail version
pytest
```

Prefer `grail …` when Avalon is installed in the active environment. Use `python grail …` to run the repo/app root `grail` script explicitly.

## Create an application

```bash
avalon new blog
cd blog
python -m venv .venv && source .venv/bin/activate
pip install -e /path/to/avalon   # or pip install avalon once published
pip install -e .
grail serve
```

## Package layout

```text
src/avalon/
  framework/    # Application, container, boot
  config/       # env + config repository
  providers/    # service providers
  http/         # kernel, request, response, middleware
  routing/      # Route DSL → FastAPI bridge
  validation/   # FormRequest
  translation/  # __(), trans_choice(), Number, SetLocale
  installer/    # avalon new …
  grail/        # grail … / python grail …
  orm/          # Articulate — Model, query builder, migrations
  caliburn/     # Caliburn views
  auth/         # guards, providers, Hash
  console/      # Grail commands, prompts, schedule, fiddle
  filesystem/   # Storage
  queue/        # jobs / workers
  mail/         # Mailable
  notifications/
  support/      # Collections, helpers
  cache/        # Cache façade
grail           # root script → same CLI as `grail`
```

## License

MIT
