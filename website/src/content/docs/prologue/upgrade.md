---
title: Upgrade Guide
description: Move an Almasix application from one release to the next.
---

Read the [Release Notes](/prologue/release-notes/) for what shipped. This page
covers what to change in **your** application when you bump the `almasix`
dependency.

## From 0.6.1 to 0.6.2

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.6.2
   ```

2. **Inertia / SPA CSRF** — no app code change required. Restart the app so
   `VerifyCsrfToken` mints `XSRF-TOKEN` on web responses; Vue/React/Svelte
   `form.post(...)` should stop returning **419**.

3. **Existing kits** — if you hit kit install or Conduit `theme_toggle` issues on
   an older scaffold, prefer re-scaffolding or pulling the stub fixes from
   [Starter Kits](/starter-kits/). After re-scaffolding, walk register → email
   verify → logout → login in the browser to confirm Day-1 auth.

## From 0.5.x to 0.6.x

1. **Bump the package**

   ```bash title="terminal"
   pip install -U 'almasix==0.6.*'
   # or pin exactly
   pip install -U almasix==0.6.2
   ```

2. **Optional: starter kits** — new apps can pick a kit with
   `almasix new myapp --kit web|api|react|vue|svelte` (CSS via `--css` for web).
   Existing apps are unchanged; see [Starter Kits](/starter-kits/).

3. **Optional: Conduit / Inertia** — enable Conduit for Prism + reactive
   components, or install the Inertia adapter for SPA stacks. Both are additive.

4. **password.confirm** — middleware now follows the named `password.confirm`
   route (fallback `/confirm-password`). If you registered confirm under another
   path with that name, Two Factor and similar screens redirect correctly after
   restarting the app server.

5. **No required app layout changes** for a typical 0.5 scaffold. Re-run your
   test suite after upgrading.

## From 0.4.x to 0.5.x

1. **Bump the package**

   ```bash title="terminal"
   pip install -U 'almasix==0.5.*'
   # or pin exactly
   pip install -U almasix==0.5.1
   ```

2. **Breaking: `Artisan` → `Smith`** — the console façade and test helper are
   renamed (PHP Laravel's CLI was named Artisan; Almasix now uses Smith).
   Update imports and call sites:

   ```python title="examples/upgrade.py"
   # before
   from almasix.console import Artisan
   from almasix.testing import artisan
   Artisan.call("inspire")
   artisan("inspire").assert_successful()

   # after
   from almasix.console import Smith
   from almasix.testing import smith
   Smith.call("inspire")
   smith("inspire").assert_successful()
   # TestCase.smith(...) replaces TestCase.artisan(...)
   ```

   There is no deprecated alias. Closure commands, `Smith.queue`, and Loupe’s
   `Smith` binding follow the same name.

3. **Logging** — prefer `from almasix.log import Log` then `Log.info(...)`
   (not stdlib `logging`). See [Logging](/logging/).

4. **Installer** — Vite stacks run `npm install && npm run build` by default
   when `npm` is on `PATH` (`--no-npm` to skip). Fresh apps include auth UI
   stubs (login/register/dashboard) and stack-styled error pages.

5. **Prism** — view data named `action` is no longer overwritten by the
   `action()` URL helper; forms should use `form_action` (or any non-helper
   name).

## From 0.3.x to 0.4.x

1. **Bump the package**

   ```bash title="terminal"
   pip install -U 'almasix==0.4.*'
   # or pin exactly
   pip install -U almasix==0.4.0
   ```

2. **Health check** — `Application.configure(…).create()` now registers
   `GET /up` by default (empty `200`, outside your middleware stacks). Point
   load balancers at it, or disable with `.with_health(None)`.

3. **Production serve** — prefer:

   ```bash title="terminal"
   smith serve --host 0.0.0.0 --port 8000 --workers 4 --no-reload --proxy-headers
   ```

   See [Deployment](/deployment/).

4. **Trusted proxies** — if you terminate TLS at a reverse proxy, keep
   `middleware.trust_proxies(…)` in `bootstrap/app.py` as well as
   `--proxy-headers` on the process.

5. **No required app layout changes** for a typical 0.3 scaffold. Re-run your
   test suite after upgrading.

## From 0.2.x or 0.1.x

Prefer jumping to the latest 0.5.x and following the steps above. Review the
[Release Notes](/prologue/release-notes/) for intermediate behaviour if you
must stay on an older line temporarily.

## General checklist

- Keep `APP_DEBUG=false` in production
- Run `smith migrate --force` before new web workers take traffic
- Run `smith optimize` after deploy (compile-checks Prism templates)
- Restart `smith queue:work` and the scheduler after the code bump
