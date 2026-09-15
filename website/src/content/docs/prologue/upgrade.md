---
title: Upgrade Guide
description: Move an Almasix application from one release to the next.
---

Read the [Release Notes](/prologue/release-notes/) for what shipped. This page
covers what to change in **your** application when you bump the `almasix`
dependency inside the project virtualenv (`pip install -U almasix==…` with the
env active). To refresh the global `almasix` installer itself, use
`pipx upgrade almasix` or `uv tool upgrade almasix`.

## From 0.9.2 to 0.9.3

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.9.3
   ```

2. **Two-factor QR** — starter kits render a scannable SVG QR for TOTP setup.
   Existing apps that use the kit `totp` helper should add `qrcode>=7.4` to
   their dependencies (`pip install 'qrcode>=7.4'`). No other layout changes
   required.

## From 0.9.1 to 0.9.2

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.9.2
   ```

2. **Generators** — `smith make:model` now accepts Laravel-style companions
   (`-c` / `-r` / `-f` / `-s` / `-a`, `--policy`, `-R`, `--api`) and clustered
   short options (`-mc`, `-mr`, `-mfsc`). Migration scaffolds annotate the
   blueprint with `table: Blueprint` (nested `def` in `up()`) so editors can
   autocomplete column helpers. No app layout changes required.

## From 0.9.0 to 0.9.1

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.9.1
   ```

2. **IDE** — Rebuild the symbol index (`smith ide:index` / Almasix → Rebuild
   Index). JetBrains **0.2.3+** uses the richer dump for config-key lines, env
   value options, and template-var navigation. No app layout changes.

## From 0.8.x to 0.9.0

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.9.0
   ```

2. **Optional IDE** — JetBrains Almasix Idea **0.2.0+** reads
   `smith ide:index --json` from the project interpreter (no LSP4IJ). VS Code
   still uses `almasix-lsp`. See [Editor setup](/editor-setup/).

3. **No required app layout changes** for a typical 0.8 scaffold. Re-run your
   test suite after upgrading.

## From 0.8.0 to 0.8.1

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.8.1
   ```

2. **Docs only** — no application code changes. Optionally skim
   [Compared to other frameworks](/prologue/compared/) and the JetBrains notes
   on [Editor setup](/editor-setup/) if you use PyCharm on Windows with WSL.

## From 0.7.x to 0.8.0

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.8.0
   ```

2. **Optional `config/services.py`** — new apps get a scaffold for Mailgun /
   Postmark / Resend / SES / Cloudflare / Vonage / Slack credentials. Existing
   apps can copy the stub from a fresh `almasix new` or keep using SMTP-only
   mail without it.

3. **Mail config** — default `config/mail.py` now lists ESP, sendmail,
   failover, and roundrobin mailers. Existing SMTP / log / array setups keep
   working; merge new mailer entries only if you need them.

4. **Notifications** — Slack and Vonage ship in core. No change required unless
   you add `"slack"` / `"vonage"` to a notification’s `via()` list.

5. **Event abort semantics** — a listener that returns `False` from
   `MessageSending` / `NotificationSending` now cancels delivery (same as
   Laravel). Review any listeners that returned `False` for other reasons.

## From 0.6.x to 0.7.0

1. **Bump the package**

   ```bash title="terminal"
   pip install -U almasix==0.7.0
   ```

2. **Inline validation** — you can validate without a FormRequest type-hint:

   ```python title="app/http/controllers/post_controller.py"
   data = request.validate({
       "email": "required|email",
       "title": ["required", "min:3"],
   })
   ```

   FormRequest injection is unchanged. Soft checks use `validator(data, rules)`.

3. **No required app layout changes** for a typical 0.6 scaffold. Re-run your
   test suite after upgrading.

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

4. **Docs** — no application changes. If you bookmarked older section titles,
   use the sidebar or search; the teaching pages were rewritten for first-time
   Almasix readers.

## From 0.5.x to 0.6.x

1. **Bump the package**

   ```bash title="terminal"
   pip install -U 'almasix==0.6.*'
   # or pin exactly
   pip install -U almasix==0.6.2
   ```

   Prefer **0.7.0** if you are jumping from 0.5.x in one step — see
   [From 0.6.x to 0.7.0](#from-06x-to-070) for validation DSL notes.

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
