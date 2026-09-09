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

## 0.4.0

- **Deployment** — production guide for ASGI apps: `smith serve --workers`,
  reverse proxies, env/secrets, migrations and queue workers, container sketch
  (`examples/deploy/`)
- **Health probe** — `GET /up` registered by default (`Application.configure(…).with_health`)
- **Docs journey** — Prologue (introduction, release notes, upgrade, versions);
  Basics teaching order; beginner-first openings; no milestone IDs in user docs
- **Version switcher** — latest major (`0.x`) by default; `main` opt-in; banner when
  not on latest
- **Lint gate** — pinned Ruff check + format in CI (`make lint`)
- **Multi-engine database CI** — conformance on SQLite, PostgreSQL, and MySQL
- **Document stores** — Articulate Mongo / memory docs under Database and Articulate
- Also on this line since 0.3.0: installer stacks, named routing, security headers /
  CORS, rate limiting (M32–M35)

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
