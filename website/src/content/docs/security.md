---
title: Security headers & CORS
description: Default security headers, CSP nonces, CORS, and maintenance mode.
---

A scaffolded Almasix application answers with security headers on every web
response, CORS headers on the paths listed in `config/cors.py`, and a 503
while `smith down` has left its marker. This page is the how and the why.

## Security headers

The `security.headers` middleware rides the `web` stack by default. Every
response that leaves a web route carries:

| Header | Default |
| --- | --- |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `SAMEORIGIN` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `X-XSS-Protection` | `0` (modern browsers ignore it; the header is kept for old ones) |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` |

API routes do not get them: a JSON API that never embeds in a page has no
need for `X-Frame-Options`. Opt in by putting `security.headers` on the
`api` group.

### CSP and HSTS

Both are opt-in, because a Content-Security-Policy that the application did
not plan for breaks every page, and HSTS on a local `http://` install is a
trap.

```python title="examples/security.py"
from almasix.http import SecurityHeaders

middleware.alias({
    "security.headers": SecurityHeaders(
        csp="default-src 'self'; script-src 'nonce-{nonce}'",
        hsts=True,  # max-age=31536000; includeSubDomains
    ),
})
```

`{nonce}` is replaced with a per-request value. Read it from a template with
`csp_nonce()`:

```html title="resources/views/examples/security.prism.html"
<script nonce="{{ csp_nonce() }}">
  /* trusted */
</script>
```

### Opting out

Remove the middleware from the web stack, or replace the global and group
stacks entirely:

```python title="examples/security.py"
def configure(middleware: Middleware) -> None:
    middleware.web(replace=["cookies.encrypt", "session.start", "csrf", "auth.start"])
    # Or clear the global stack (also drops maintenance):
    # middleware.use([])
```

## CORS

`config/cors.py` decides which origins may call this application from a
browser. Paths that do not match `paths` are left alone — a public
marketing page does not sprout `Access-Control-Allow-Origin`.

```python title="config/cors.py"
config = {
    "paths": ["api/*", "signet/csrf-cookie"],
    "allowed_methods": ["*"],
    "allowed_origins": ["*"],
    "allowed_origins_patterns": [],
    "allowed_headers": ["*"],
    "exposed_headers": [],
    "max_age": 0,
    "supports_credentials": False,
}
```

`api/*` matches `/api` and everything under it. Set `cors` to `False` in
configuration to disable the middleware entirely.

## Maintenance mode

`smith down` writes `storage/framework/down`. While that marker exists, the
scheduler skips tasks (unless exempted) and HTTP responses answer **503**.

```bash title="terminal"
smith down --secret=let-me-in --retry=60
# Application is now in maintenance mode.
# Bypass secret: let-me-in
# Visit any URL with ?secret=let-me-in to set the bypass cookie.

smith up
# Application is now live.
```

While the marker is present:

- Every request answers **503** with `Retry-After` when `--retry` was given.
- `--redirect=/elsewhere` sends a 302 instead.
- `--render=errors.503` renders a Prism view as the body.
- `--secret=…` (or `--with-secret`) lets an operator visit `?secret=…` once;
  the response sets a cookie and redirects to the same URL without the query,
  and subsequent requests pass through.

A marker that is only the plain word `down` still means down — the middleware
treats an unreadable payload as an empty one, so older markers answer 503
rather than 500.

### Options

| Flag | Effect |
| --- | --- |
| `--redirect=` | Redirect instead of 503 |
| `--render=` | Prism view for the 503 body |
| `--retry=` | `Retry-After` seconds |
| `--refresh=` | `Refresh` header seconds |
| `--secret=` | Bypass secret |
| `--with-secret` | Generate a random bypass secret |
| `--status=` | HTTP status (default 503) |

## Defaults on by default

A new application from `almasix new` ships with:

- `maintenance` on the global middleware stack
- `security.headers` on the `web` group
- `config/cors.py` with the defaults above

That is deliberate: a scaffold that forgets the headers is worse than one
that opts out of them.

## Related

- [Middleware](/middleware/) — registering stacks and aliases
- [CSRF Protection](/csrf/) — the form token that rides the same web stack
- [Routing](/routing/) — groups that name `web` and `api`
