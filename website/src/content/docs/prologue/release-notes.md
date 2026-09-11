---
title: Release Notes
description: What changed in each Almasix release — for people building apps, not the framework roadmap.
---

Almasix versions follow [SemVer](https://semver.org/). While the project is on
**0.x**, minor bumps may include breaking changes; those are called out below.
Install a specific version with `pip install almasix==X.Y.Z`.

For how to move between releases, see the [Upgrade Guide](/prologue/upgrade/).
For how these docs relate to package versions, see
[Documentation Versions](/prologue/versions/).

## 0.6.2

- **CSRF / Inertia** — web responses mint a readable `XSRF-TOKEN` cookie;
  `X-XSRF-TOKEN` decrypts when `EncryptCookies` wrapped the value (fixes Vue/React
  kit register **419**)
- **Starter kit auth** — Web and Vue scaffolds migrate cleanly; CSRF minting
  unblocks register; register → email verify → logout → login works out of the
  box
- **Docs rewrite** — user-facing docs assume Python + web only (no Laravel
  required); every code fence names a file path; Basics / Database / Articulate /
  Digging Deeper rewritten for first-time Almasix developers

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
