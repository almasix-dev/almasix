---
title: Upgrade Guide
description: Move an Almasix application from one release to the next.
---

Read the [Release Notes](/prologue/release-notes/) for what shipped. This page
covers what to change in **your** application when you bump the `almasix`
dependency.

## From 0.3.x to 0.4.x

1. **Bump the package**

   ```bash
   pip install -U 'almasix==0.4.*'
   # or pin exactly
   pip install -U almasix==0.4.0
   ```

2. **Health check** — `Application.configure(…).create()` now registers
   `GET /up` by default (empty `200`, outside your middleware stacks). Point
   load balancers at it, or disable with `.with_health(None)`.

3. **Production serve** — prefer:

   ```bash
   smith serve --host 0.0.0.0 --port 8000 --workers 4 --no-reload --proxy-headers
   ```

   See [Deployment](/deployment/).

4. **Trusted proxies** — if you terminate TLS at a reverse proxy, keep
   `middleware.trust_proxies(…)` in `bootstrap/app.py` as well as
   `--proxy-headers` on the process.

5. **No required app layout changes** for a typical 0.3 scaffold. Re-run your
   test suite after upgrading.

## From 0.2.x or 0.1.x

Prefer jumping to the latest 0.4.x and following the steps above. Review the
[Release Notes](/prologue/release-notes/) for intermediate behaviour if you
must stay on an older line temporarily.

## General checklist

- Keep `APP_DEBUG=false` in production
- Run `smith migrate --force` before new web workers take traffic
- Run `smith optimize` after deploy (compile-checks Prism templates)
- Restart `smith queue:work` and the scheduler after the code bump
