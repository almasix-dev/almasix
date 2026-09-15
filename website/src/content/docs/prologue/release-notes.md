---
title: Release Notes
description: What changed in each Almasix release — for people building apps, not the framework roadmap.
---

Almasix versions follow [SemVer](https://semver.org/). While the project is on
**0.x**, minor bumps may include breaking changes; those are called out below.
Install a specific version of the application dependency with
`pip install almasix==X.Y.Z` (inside the project venv). Refresh the global
installer with `pipx install almasix==X.Y.Z` or `uv tool install almasix==X.Y.Z`.

For how to move between releases, see the [Upgrade Guide](/prologue/upgrade/).
For how these docs relate to package versions, see
[Documentation Versions](/prologue/versions/).

## 0.9.3

- **Starter-kit TOTP QR codes** — two-factor setup shows a scannable SVG QR
  (via `qrcode`) instead of a raw `otpauth://` URI; URI remains under
  “Can't scan?”
- **Editor packages** — docs and `smith ide:install` point at the split
  [`almasix-vscode`](https://github.com/almasix-dev/almasix-vscode) and
  [`almasix-idea`](https://github.com/almasix-dev/almasix-idea) repos; Open
  VSX install path for Cursor / VSCodium; Prism `@section('name', 'value')`
  noted in LSP hover

Published on [PyPI](https://pypi.org/project/almasix/0.9.3/) after the `v0.9.3`
GitHub Release.

## 0.9.2

- **`make:model` companions** — `-c` / `--controller`, `-r` / `--resource`,
  `-s` / `--seed`, `--policy`, `-R` / `--requests`, `--api`, and `-a` / `--all`
  (plus the existing `-m` / `-f`) generate the matching classes in one shot
- **Clustered short options** — `-mc`, `-mr`, `-mfsc`, and the like expand the
  Laravel / GNU way instead of treating the rest as a value for the first flag
- **Typed migration blueprints** — stubs and docs use `table: Blueprint` so
  editors autocomplete column helpers; `BlueprintCallback` is exported for
  explicit bindings
- **`ide:index`** — model metadata also records `guarded` and `hidden`

Published on [PyPI](https://pypi.org/project/almasix/0.9.2/) after the `v0.9.2`
GitHub Release.

## 0.9.1

- **`ide:index` depth** — `config_locations` (key → file/line), `env_options`
  (driver/store/connection suggestions), and relation method lines for IDE
  navigation
- **Env intelligence** — two-way completion: keys from config/`env()` into
  `.env`, and value options for keys like `QUEUE_CONNECTION` / `SESSION_DRIVER`
  (LSP + index dump)
- **Config go-to** — `config("app.env")` resolves to the `"env"` line in
  `config/app.py`

Published on [PyPI](https://pypi.org/project/almasix/0.9.1/) after the `v0.9.1`
GitHub Release.

## 0.9.0

- **`smith ide:index`** — JSON app symbol index (routes, views, config, gates,
  validation rules, relations, components, Smith commands, and related
  surfaces) for native IDE tooling
- **Almasix Idea architecture** — JetBrains uses the index dump (no LSP4IJ);
  VS Code continues on `almasix-lsp`. Docs: [Editor setup](/editor-setup/)
- **Global installer** — `pipx` / `uv tool` documented for installing the
  `almasix` project generator outside PEP 668-managed system Pythons

Published on [PyPI](https://pypi.org/project/almasix/0.9.0/) after the `v0.9.0`
GitHub Release.

## 0.8.1

- **Compared to other frameworks** — Prologue page covering Django, FastAPI,
  Flask, Litestar, and Masonite (when to pick each, candid feature map)
- **Editor setup** — JetBrains troubleshooting for `almasixLsp (pid=null)`,
  including Windows IDE + WSL projects (plugin 0.1.13+)
- **README downloads badge** — shields.io pepy total downloads (avoids
  pypistats rate-limit noise)

Published on [PyPI](https://pypi.org/project/almasix/0.8.1/) after the `v0.8.1`
GitHub Release.

## 0.8.0

- **Mail + Notifications exhaust** — Laravel 13 doc parity for the
  framework-shaped surface: Notification façade (send / on-demand / locale /
  fake), `MailMessage`, custom channel classes, mail & notification events,
  failover / round-robin mailers, ESP HTTP drivers (Mailgun, Postmark, Resend,
  SES, Cloudflare) plus sendmail, Slack + Vonage channels, and `config/services.py`
- **Localization docs** — Starlight Localization page for catalogs, plurals,
  locale middleware, and Number helpers
- **Mail / Notifications docs** — writing mailables and notification messages
  covered at Laravel TOC depth (envelope, Markdown themes, `MailMessage`,
  Vonage / Slack builders)

Published on [PyPI](https://pypi.org/project/almasix/0.8.0/) after the `v0.8.0`
GitHub Release.

## 0.7.0

- **Validation exhaust** — `request.validate({...})` accepts pipe-string rules and
  `Rule.*` helpers alongside FormRequest / Pydantic schemas; all available rules
  ship with docs and a maintainer catalog
- **Inspired by Laravel** — Prologue credits Laravel’s design tradition with a
  link to [laravel.com](https://laravel.com/); feature pages stay Almasix-first
- **Validation docs** — teaching page covers inline validation, soft checks,
  custom rules, and every available rule without framework-comparison digressions

## 0.6.2

- **CSRF / Inertia** — web responses mint a readable `XSRF-TOKEN` cookie;
  `X-XSRF-TOKEN` decrypts when `EncryptCookies` wrapped the value (fixes Vue/React
  kit register **419**)
- **Starter kit auth** — Web and Vue scaffolds migrate cleanly; CSRF minting
  unblocks register; register → email verify → logout → login works out of the
  box
- **Docs rewrite** — user-facing docs assume Python + web only; every code fence
  names a file path; Basics / Database / Articulate / Digging Deeper rewritten
  for first-time Almasix developers

## 0.6.1

- **Extract** — Conduit and Inertia ship as first-party packages
  ([`almasix-conduit`](https://pypi.org/project/almasix-conduit/),
  [`almasix-inertia`](https://pypi.org/project/almasix-inertia/)); install via
  `almasix[conduit]` / `almasix[inertia]`
- Web kits declare `almasix[conduit]`; SPA kits declare `almasix[inertia]`
- Conduit loads through PackageManifest discovery (no longer wired in Foundation)

## 0.6.0

- **Conduit** — Livewire-class reactive components (`almasix.conduit`),
  including signed update routes and a full parity matrix in the docs
- **Inertia** — first-party adapter with lazy / defer / once /
  merge props, asset versioning, and Starlight docs
- **Starter kits** — `almasix new --kit` overlays for Forge **web** (Conduit +
  Prism), **api** (Signet), and **react** / **vue** / **svelte** (Inertia), with
  Tailwind 4 by default plus Bootstrap / none for web
- **Auth polish** — `password.confirm` redirects to the named `password.confirm`
  route (fixes Two Factor settings 404 on Jetstream-style paths)

Published on [PyPI](https://pypi.org/project/almasix/0.6.0/) after the `v0.6.0`
GitHub Release.

## 0.5.1

- **Brand refresh** — glassy blue diamond accents on the Almasix mark and wordmark;
  light/dark logo variants for the docs header and landing hero
- **Docs UX** — two landing CTAs (Get started / Read the docs); GitHub star count
  in the header; single-button theme cycle (dark → light → auto) instead of a
  dropdown

Published on [PyPI](https://pypi.org/project/almasix/0.5.1/) after the `v0.5.1`
GitHub Release.

## 0.5.0

- **Breaking: `Artisan` → `Smith`** — console façade is `Smith.call` /
  `Smith.command` / `Smith.queue`; testing helper is `smith()` /
  `TestCase.smith()`. (PHP Laravel's CLI was named Artisan.) No deprecated
  alias — see the [Upgrade Guide](/prologue/upgrade/)
- **Installer UX** — MongoDB as a documents option; live step logs; rich UI kit
  (layouts, auth, dashboard, stack error pages); default `npm install && npm
  run build` for Vite stacks when Node is available
- **Console polish** — One Dark Pro styled output; schedule worker timestamps
  and task output; `inspire` / `list` / `route:list` / `about` colors
- **Logging** — `Log` façade (`Log.info`, `Log.success`, …); docs warn against
  importing stdlib `logging` for app messages
- **Prism** — view data is not overwritten by URL helpers named the same
  (`action` / `form_action` fix for auth forms)

Published on [PyPI](https://pypi.org/project/almasix/0.5.0/) after the `v0.5.0`
GitHub Release.

## 0.4.0

- **Deployment** — production guide for ASGI apps: `smith serve --workers`,
  reverse proxies, env/secrets, migrations and queue workers, container sketch
  (`examples/deploy/`)
- **Health probe** — `GET /up` registered by default (`Application.configure(…).with_health`)
- **Docs journey** — Prologue (introduction, release notes, upgrade, versions);
  Basics teaching order; beginner-first openings
- **Version switcher** — latest major (`0.x`) by default; `main` opt-in; banner when
  not on latest
- **Lint gate** — pinned Ruff check + format in CI (`make lint`)
- **Multi-engine database CI** — conformance on SQLite, PostgreSQL, and MySQL
- **Document stores** — Articulate Mongo / memory docs under Database and Articulate
- Also on this line since 0.3.0: installer stacks, named routing, security headers /
  CORS, and rate limiting

Published on [PyPI](https://pypi.org/project/almasix/0.4.0/) after the `v0.4.0`
GitHub Release.

## 0.3.0

- Published on [PyPI](https://pypi.org/project/almasix/0.3.0/) and TestPyPI
- Trusted Publishing via GitHub Actions (OIDC) — no long-lived PyPI tokens in the repo
- Console exhaust, installer stacks, named routing, security headers/CORS, and rate limiting

## 0.2.0

- Earlier PyPI release on the 0.2 line — see the
  [GitHub release](https://github.com/almasix-dev/almasix/releases/tag/v0.2.0)

## 0.1.0

- First tagged public release — see the
  [GitHub release](https://github.com/almasix-dev/almasix/releases/tag/v0.1.0)
