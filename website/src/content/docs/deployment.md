---
title: Deployment
description: Run an Almasix app in production — servers, workers, env, Docker, and releasing.
---

Almasix is an **ASGI** application. In production you run Uvicorn (or another
ASGI server) behind a reverse proxy, keep `APP_DEBUG` off, migrate before
traffic hits new code, and run queue workers as separate processes.

This page is about **deploying your app**. A short section at the end covers
how the Almasix framework itself is published to PyPI, for open-source
consumers who want that picture.

## Server requirements

- Python **3.11+**
- An ASGI server — Uvicorn is what `smith serve` uses
- A reverse proxy (nginx, Caddy, Traefik, a cloud load balancer) that terminates
  TLS and forwards to the app
- Whatever databases, Redis, or mail services your `config/*.py` points at

## Environment and secrets

Never commit `.env`. On the host or in the orchestrator, set at least:

| Variable | Production expectation |
| --- | --- |
| `APP_ENV` | `production` |
| `APP_DEBUG` | `false` — debug pages and Vite comments must not ship |
| `APP_KEY` | A long random secret (`smith key:generate` once, then inject) |
| `APP_URL` | The public origin, including scheme |

Database, Redis, mail, and queue credentials come from the same env file or
from your platform’s secret store. Prefer injecting secrets at runtime over
baking them into images.

## Serving the application

From the application root:

```bash title="terminal"
smith serve --host 0.0.0.0 --port 8000 --workers 4 --no-reload --proxy-headers
```

| Flag | Role |
| --- | --- |
| `--workers` | Uvicorn worker processes (reload turns off automatically when `> 1`) |
| `--no-reload` | Required for production even with one worker |
| `--proxy-headers` | Honour `X-Forwarded-*` from the reverse proxy |
| `--forwarded-allow-ips` | Which proxy IPs may set those headers (default `*`) |

Point the ASGI import at `bootstrap.app:asgi` (the scaffold default). Equivalent
bare Uvicorn:

```bash title="terminal"
uvicorn bootstrap.app:asgi --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers
```

### Trusted proxies inside the app

`smith serve --proxy-headers` tells Uvicorn to trust forwarded headers. For
request IP / scheme helpers inside Almasix middleware, also trust proxies in
`bootstrap/app.py`:

```python title="bootstrap/app.py"
from almasix.http import HEADER_X_FORWARDED_ALL

def configure_middleware(middleware: Middleware) -> None:
    middleware.trust_proxies(at="*", headers=HEADER_X_FORWARDED_ALL)
    middleware.trust_hosts(at=["example.com", "*.example.com"])
```

See [Middleware](/middleware/).

### Static assets

Vite writes into `public/build/`. The HTTP kernel mounts `public/{css,js,images,fonts,build}`
when those folders exist. Build assets in CI or in the image:

```bash title="terminal"
npm ci && npm run build
```

A CDN or the reverse proxy can still front `/build` if you prefer.

## Health checks

Every application created with `Application.configure(...).create()` registers
**`GET /up`** by default — an empty `200` outside the Almasix middleware stacks,
so `smith down` does not take the probe offline. Point your load balancer at it.

```python title="bootstrap/app.py"
application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .with_health("/up")   # default; pass None to disable
    .create()
)
```

## Optimize before traffic

```bash title="terminal"
smith optimize
```

That compile-checks every Prism template (`view:cache`). Config, routes, and
event listeners are **not** written to disk caches: an ASGI process boots once
and serves for its lifetime, so those caches would save almost nothing and risk
serving stale values. See [Smith Console](/console/).

## Migrations and queue workers

On each deploy, before or as the new workers start:

```bash title="terminal"
smith migrate --force
smith optimize
```

Run queue consumers as **separate** long-lived processes (not inside the web
workers):

```bash title="terminal"
smith queue:work --tries=3
```

Schedule `smith schedule:work` (or cron `* * * * * smith schedule:run`) the same
way. See [Queues](/queues/) and [Task Scheduling](/scheduling/).

## Logs

Configure channels in `config/logging.py`. In containers, prefer `stderr` (or a
`stack` that includes it) so the platform collects logs. The exception Handler
reports through the logger — see [Logging](/logging/) and [Error Handling](/errors/).

## Bare metal

1. Install Python 3.11+, create a venv, `pip install -r requirements.txt` (or
   pin `almasix` and your app deps).
2. Place `.env` with production values; `APP_DEBUG=false`.
3. `smith migrate --force && smith optimize`.
4. Run under systemd (or supervisord): one unit for
   `smith serve --host 127.0.0.1 --port 8000 --workers 4 --no-reload --proxy-headers`,
   plus units for `queue:work` and the scheduler.
5. Terminate TLS at nginx/Caddy; proxy to `127.0.0.1:8000`; health-check `/up`.

## Container

Build from the **application** root (the directory with `bootstrap/` and
`smith`), not from the framework repo:

```dockerfile title="Dockerfile"
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    APP_DEBUG=false

COPY pyproject.toml README.md ./
COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["smith", "serve", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--no-reload", "--proxy-headers"]
```

[`examples/deploy/`](https://github.com/almasix-dev/almasix/tree/main/examples/deploy)
adds a compose sketch (web + `queue:work` + Postgres) with an `/up` healthcheck.

Run migrations as a release job or an entrypoint step before workers accept
traffic — do not rely on web processes to migrate.

## How Almasix is published (framework)

The framework is on [PyPI](https://pypi.org/project/almasix/)
(`pip install almasix`). Releases use GitHub Actions Trusted Publishing (OIDC)
— see `.github/workflows/publish.yml`. No API tokens are stored in the repo.

To cut a release (maintainers):

1. Confirm `project.version` in `pyproject.toml` and `almasix.__version__` match
   (CI refuses a tag that disagrees with the packaged version).
2. Merge to `main`.
3. Optional rehearsal: Actions → **Publish** → Run workflow → target `testpypi`.
4. Create an annotated tag (for example `v0.6.2`) and a GitHub Release on that
   tag. Publishing the Release triggers the PyPI job.

Install with:

```bash title="terminal"
pip install almasix
# or pin
pip install almasix==0.6.2
```

## Related

- [Installation](/installation/)
- [Middleware](/middleware/) (trusted proxies / hosts)
- [Security headers & CORS](/security/)
- [Smith Console](/console/) (`optimize`, `serve`, `down` / `up`)
- [Queues](/queues/)
