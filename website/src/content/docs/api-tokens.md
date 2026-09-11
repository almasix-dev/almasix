---
title: API Tokens
description: Personal access tokens, abilities, SPA cookie auth, and mobile Bearer tokens — Signet-class authentication.
---

**API tokens** answer “which user is calling this API?” without standing up a
full OAuth2 server. Almasix ships a Signet-class package
(`almasix.signet`, optional extras `almasix[tokens]` / `almasix[signet]`) for:

1. **Personal access tokens (PATs)** — hashed tokens owned by a user, sent as
   `Authorization: Bearer …` (mobile apps, CLIs, first-party API clients).
2. **SPA cookie authentication** — first-party single-page apps keep using the
   session cookie + CSRF; Signet only accepts that cookie from configured
   stateful domains.

They are **always tied to a user account**. Application / client-credentials
API keys that authenticate a *client* with no user are a different product and
are **not** part of this package (see [Out of scope](#out-of-scope)).

## Installation

The package is in the framework today. Publish the config and migration when
you want them in your app tree:

```bash title="terminal"
pip install 'almasix[tokens]'   # or almasix[signet] — empty extras that mark the feature
smith vendor:publish --tag=signet-config
smith vendor:publish --tag=signet-migrations
smith migrate
```

Add the mixin to your authenticatable model:

```python title="app/models/example.py"
from almasix.auth import AuthenticatableMixin
from almasix.orm import Model
from almasix.signet import HasApiTokens

class User(HasApiTokens, AuthenticatableMixin, Model):
    ...
```

Register a Signet guard in `config/auth.py`:

```python title="examples/api-tokens.py"
"guards": {
    "web": {"driver": "session", "provider": "users"},
    "signet": {"driver": "signet", "provider": "users"},
}
```

Protect routes with `auth:signet` — the guard tries the session user for
first-party SPA requests, then falls back to a Bearer PAT.

## Issuing tokens

```python title="examples/api-tokens.py"
issued = await user.create_token("Nuno's iPhone", ["server:update"])
print(issued.plain_text_token)  # "12|a3f2…" — show once, store hashed
```

The plain-text value is `{id}|{secret}`. Only the SHA-256 hash is stored.
Abilities default to `["*"]` (full access for that user).

Mobile apps typically `POST` credentials to an endpoint that returns a token:

```python title="routes/api.py"
Route.post("/signet/token", [TokenController, "issue"])
```

Store the returned token in the platform keychain and send it on every request.

## Abilities

```python title="examples/api-tokens.py"
issued = await user.create_token("deploy", ["server:update", "server:read"])

# On an authenticated request:
if user.token_can("server:update"):
    ...
if user.token_cant("server:delete"):
    ...
```

Middleware aliases (register in `bootstrap/app.py`, or call
`middleware.stateful_api()` which also registers them):

```python title="routes/web.py"
middleware.alias({
    "abilities": CheckAbilities,      # all listed abilities required
    "ability": CheckForAnyAbility,    # at least one
})

Route.get("/orders", ...).middleware(["auth:signet", "abilities:check-status,place-orders"])
```

For first-party SPA session requests (no PAT), `token_can` returns `True` so
policies can stay uniform — authorization still belongs in Gates / Policies.

## Protecting routes

```python title="routes/web.py"
Route.get("/user", [UserController, "show"], middleware=["auth:signet"])
```

`auth:signet` authenticates either:

- a session cookie from a **stateful** domain, or
- a valid Bearer personal access token.

## Revoking and expiration

```python title="examples/api-tokens.py"
await user.tokens_delete()                          # all tokens
await user.current_access_token().delete()          # this request's token
await user.tokens().where("id", "=", token_id).first()  # then .delete()
```

Configure minutes until expiry in `config/signet.py` (`expiration`), or pass
`expires_at=` to `create_token`. Prune with:

```bash title="terminal"
smith signet:prune-expired --hours=24
```

## SPA authentication

1. List first-party domains in `config/signet.py` → `stateful`.
2. Call `middleware.stateful_api()` in `bootstrap/app.py` so the `api` group
   gets session + CSRF for those domains.
3. Before login, `GET /signet/csrf-cookie` (sets `XSRF-TOKEN`).
4. `POST /login` with the session guard as usual.
5. Subsequent API calls send cookies + `X-XSRF-TOKEN`.

CORS must allow credentials; the session cookie domain should cover your SPA
subdomain.

## Testing

```python title="examples/api-tokens.py"
from almasix.signet import Signet

Signet.acting_as(user, ["profile:read"])
# next HTTP request through the test client is authenticated as user
```

Or issue a real token and `with_token(plain_text_token)`.

## Configuration

| Key | Meaning |
| --- | --- |
| `signet.stateful` | Domains allowed to use cookie session auth against the API |
| `signet.guard` | Session guards consulted before Bearer lookup |
| `signet.expiration` | Default PAT lifetime in minutes (`None` = never) |
| `Signet.use_personal_access_token_model(...)` | Swap the token model |

Helpers: `Signet.current_application_url_with_port()`,
`Signet.current_request_host()` for the stateful list.

## Out of scope

| Need | Use instead |
| --- | --- |
| Client / application API keys (no user) | Separate client-credentials surface (not Signet) |
| Third-party OAuth2 server | Passport-class package (deferred) |
| Social login (Google, GitHub, …) | Socialite-class providers (deferred) |

Classic `driver: "token"` looking up `users.api_token` remains available for
simple demos; prefer Signet PATs for production APIs.
