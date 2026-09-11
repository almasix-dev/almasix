---
title: Session
description: Cookie and Redis session drivers for stateful web routes.
---

Almasix sessions power the `web` middleware group. The default **cookie** driver
stores a signed JSON bag in `almasix_session` (wrapped by `EncryptCookies`). Set
`SESSION_DRIVER=redis` to keep only a signed session id in the cookie and store
the payload in Redis. The `api` group stays stateless (no session cookie).

## Web stack

```python title="bootstrap/app.py"
from almasix.session import EncryptCookies, StartSession, VerifyCsrfToken
from almasix.auth.middleware import StartAuth

middleware.alias({
    "cookies.encrypt": EncryptCookies,
    "session.start": StartSession,
    "csrf": VerifyCsrfToken,
    "auth.start": StartAuth,
})
middleware.web(
    prepend=["cookies.encrypt", "session.start", "csrf", "auth.start"],
)
```

Order matters: decrypt cookies → start session → CSRF → hydrate auth.

## Request API

```python title="app/http/controllers/welcome_controller.py"
request.session.put("locale", "fr")
request.session.get("locale")
request.session.flash("status", "Saved.")
request.session.forget("draft")
```

Flash values survive one redirect, then age out on the next request.

## Config

`config/session.py` (and `APP_KEY` in `config/app.py`):

| Key | Default | Role |
| --- | --- | --- |
| `session.driver` | `cookie` | `cookie` or `redis` |
| `session.cookie` | `almasix_session` | Cookie name |
| `session.lifetime` | `120` | Minutes |
| `session.path` | `/` | Cookie path |
| `session.secure` | `false` | HTTPS-only |
| `session.connection` | `default` | Redis connection name (redis driver) |
| `session.prefix` | `almasix_session:` | Redis key prefix |
| `app.key` | — | HMAC + cookie encryption secret |

See [Redis](/redis/) for connection settings when using the redis driver.

## Locale

`SetLocale` reads `session["locale"]` when present (after `StartSession`), then
falls back to `Accept-Language` / `APP_LOCALE`.

## Related

- [Redis](/redis/)
- [CSRF Protection](/csrf/)
- [Middleware](/middleware/)
- [Routing](/routing/)
