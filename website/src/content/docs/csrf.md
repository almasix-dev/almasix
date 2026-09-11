---
title: CSRF Protection
description: Verify mutating web requests with a session-backed CSRF token.
---

Stateful `web` routes mint a CSRF token in the session and reject unsafe methods
when the token is missing or wrong. API routes stay **stateless** — use bearer
tokens instead of CSRF.

## How it works

1. `StartSession` loads the signed (and encrypted) session cookie
2. `VerifyCsrfToken` ensures `_csrf_token` exists and checks mutating requests
3. Every successful response also sets a readable `XSRF-TOKEN` cookie so SPA /
   Inertia clients can echo it as `X-XSRF-TOKEN`
4. Prism `@csrf` emits a hidden `_token` field from `csrf_token`

Accepted sources for the token:

- Form field `_token` (from `@csrf`)
- Header `X-CSRF-TOKEN` (plain token, e.g. from a meta tag)
- Header `X-XSRF-TOKEN` (value of the `XSRF-TOKEN` cookie — decrypts when
  `EncryptCookies` wrapped it)

Mismatch raises **419** (`TokenMismatchError`).

### Inertia / Vue / React / Svelte

Official `@inertiajs/*` clients use axios defaults (`xsrfCookieName` /
`xsrfHeaderName`). After the first `GET` of a page, the browser has
`XSRF-TOKEN`; subsequent `form.post(...)` calls send `X-XSRF-TOKEN`
automatically. You do not need a hidden `@csrf` field in Vue forms.

## Prism forms

```html title="resources/views/auth/login.prism.html"
<form method="post" action="/login">
  @csrf
  <input name="email" type="email">
  <button type="submit">Sign in</button>
</form>
```

`AuthServiceProvider` shares `csrf_token` into every view so `@csrf` works
without manual wiring.

## Middleware group

Register on the `web` stack (scaffold default):

```python title="bootstrap/app.py"
middleware.web(
    prepend=["cookies.encrypt", "session.start", "csrf", "auth.start"],
    append=["locale"],
)
```

Do **not** put `csrf` on the `api` group.

## Related

- [Session](/session/)
- [Middleware](/middleware/)
- [Prism stacks & directives](/prism/stacks/)
