---
title: Starter Kits
description: Production-ready Web (Conduit), API (Signet), and SPA (Inertia) overlays for almasix new — Forge design, full auth depth.
---

## Introduction

Starter kits are **overlays** on the application scaffolder. Pick one when you run
`almasix new` (or pass `--kit`) and the installer layers production auth,
settings, teams, and a shared **Forge** design language on top of the blank app.

```bash
almasix new myapp --kit web --stack tailwind
almasix new myapi --kit api
almasix new myspa --kit react   # or vue | svelte
almasix stacks                  # lists kits + stacks + databases
```

Progress proof: `smith progress:kits` (scaffolds every kit, then soaks Web + Vue
register → email verify → logout → login).

## Kits

| Kit | Flag | Stack | Surface |
| --- | --- | --- | --- |
| None | `--kit none` (default) | any | Blank scaffold only |
| **Web** | `--kit web` | Tailwind 4 / Bootstrap / none | Prism + Conduit |
| **API** | `--kit api` | forced `none` | Signet PAT JSON |
| **SPA** | `--kit react\|vue\|svelte` | forced Tailwind | Official `@inertiajs/*` |

## Forge design

Same language across Web and SPA:

- **Landing** — brand-first, full-bleed hero (Outfit + JetBrains Mono, same as Progress), chartreuse CTA, teal brand `#0d9488`. No cards in the first viewport.
- **Authenticated chrome** — quiet sidebar (Dashboard, Notifications, Settings, Teams), theme toggle, light **and** dark (`class="dark"` + `localStorage`).
- **CSS stacks** — Web kit honors Tailwind / Bootstrap / none; SPA kits always ship Vite + Tailwind 4.

## Auth depth

Kits aim at Jetstream-class depth (not a thin login form):

- Register / login / logout
- Password forgot + reset
- Email verification + password confirmation
- Profile (name/email), password change, delete account, profile photo
- Two-factor authentication (stdlib TOTP + recovery codes)
- Teams (create, switch, invite, settings)
- Notifications **shell** (inbox UI ready for database notifications)
- Settings / appearance (theme)

**API kit:** personal access tokens only — `POST /api/tokens`, `GET /api/user`, revoke. No session auth UI.

## Web kit (Conduit)

```bash
almasix new forgeweb --kit web --stack tailwind -n
cd forgeweb && python -m venv .venv && source .venv/bin/activate
pip install -e .
python smith migrate
npm install && npm run build
python smith serve
```

Conduit ships a theme-toggle island on the authenticated layout. Routes live in
`routes/web.py`; components under `app/conduit/`.

## SPA kit (Inertia)

```bash
almasix new forgespa --kit react -n
cd forgespa
pip install -e .
npm install && npm run build
python smith migrate && python smith serve
```

Web kits declare `almasix[conduit]`; SPA kits declare `almasix[inertia]`.
Both extras resolve to the published first-party packages.
Pages under `resources/js/Pages/` use the official Inertia client. Root Prism
view provides `@inertia` / `@inertiaHead`. Middleware alias `inertia` runs on
the web stack; `stateful_api()` is enabled for cookie SPA flows.

## API kit (Signet)

```bash
almasix new forgeapi --kit api -n
# issue a token
curl -X POST /api/tokens -d '{"email":"…","password":"…","name":"cli"}'
curl /api/user -H "Authorization: Bearer …"
```

## Extending

Kits are files under `src/almasix/installer/stubs/kits/`. Publish a private
scaffold with `smith stub:publish --scaffold` and point `almasix new --stubs`
at your tree to keep team overlays.

## Exhaust checklist

- [x] Web / API / SPA overlays
- [x] React + Vue + Svelte
- [x] Tailwind 4 + Bootstrap + none (Web)
- [x] Forge landing + authenticated chrome + dark mode
- [x] Full auth / 2FA / teams / settings / notifications shell
- [x] Tokens API-only
- [x] Installer prompt + flags
- [x] Progress + smoke
