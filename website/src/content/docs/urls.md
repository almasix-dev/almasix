---
title: URL Generation
description: Build links that honor APP_URL and APP_BASE_PATH.
---

Every URL an Almasix application emits goes through one place, because two
rules have to hold everywhere. An app mounted under a subpath
(`APP_BASE_PATH=/apps/progress`) must never emit a root-absolute link, and a
URI written once in `routes/web.py` should not be repeated in every template
that links to it.

## Configuration

| Env / config | Role |
| --- | --- |
| `APP_URL` | Origin (`https://example.com`) |
| `APP_BASE_PATH` | Public path prefix (`/apps/progress`) |

The HTTP kernel mounts the ASGI app at the same prefix, so `smith serve`
answers on exactly the paths `url()` emits.

Everything on this page is available two ways: as a module-level helper for the
common case, and as a method on `UrlGenerator` when you need to configure the
generator itself. `UrlGenerator.from_config()` builds the one this application's
configuration describes.

## The basics

### Generating URLs

`url()` builds a URL for a path, prefixed with the base path and rooted at
`APP_URL`. The outputs below are what an app configured with
`APP_URL=https://shop.test` and `APP_BASE_PATH=/eu` emits:

```python
# app/http/controllers/checkout_controller.py
from almasix.routing import url

url("/checkout")                   # 'https://shop.test/eu/checkout'
url("/checkout", absolute=False)   # '/eu/checkout'
```

Extra path segments may be passed as the second argument, and a query string as
`query`:

```python
url("users", [1, "posts", 2])      # 'https://shop.test/eu/users/1/posts/2'
url("/posts", query={"page": 2})   # 'https://shop.test/eu/posts?page=2'
url("/posts", query={"tag": ["a", "b"]})  # '…/posts?tag=a&tag=b'
```

A list value repeats the key, and a `None` value is left out rather than
serialized as the word `None`. A path that is already absolute (`https://…` or
`//…`) is returned unchanged, though it will still take a query string.

:::note
Laravel spells the query string with a fluent `withQuery`. Almasix takes it as
a `query=` keyword argument, since `url()` is a function rather than the entry
point to a builder.
:::

### Assets

`asset()` is the same code path for files under `public/`, so a subpath app
emits correct asset links too:

```python
# app/http/controllers/welcome_controller.py
from almasix.routing import asset

asset("build/app.css")                  # 'https://shop.test/eu/build/app.css'
asset("build/app.css", absolute=False)  # '/eu/build/app.css'
```

Default apps ship Vite and Tailwind emitting into `public/build/`; keep calling
`asset(...)` for anything under `public/`. See
[Asset Bundling](/asset-bundling/).

### Forcing HTTPS

`secure_url` and `secure_asset` emit `https` whatever `APP_URL` says, for the
handful of links — a checkout, a login form — that must not be downgraded even
in a development environment served over HTTP:

```python
from almasix.routing import secure_asset, secure_url

# With APP_URL=http://shop.test:
secure_url("/checkout")            # 'https://shop.test/checkout'
secure_asset("build/app.css")      # 'https://shop.test/build/app.css'
url("/checkout")                   # 'http://shop.test/checkout'
```

### Without a booted application

A script or a unit test has no `APP_URL` to honour and no base path to prefix,
so the generator emits a relative URL rather than raising:

```python
url("/a")                # '/a'
asset("build/app.css")   # '/build/app.css'
```

## Accessing the current URL

`UrlGenerator` reads the request in flight:

```python
# app/http/controllers/nav_controller.py
from almasix.routing import UrlGenerator


class NavController(Controller):
    async def index(self):
        urls = UrlGenerator.from_config()

        urls.full()           # 'https://shop.test/posts?page=2'
        urls.current()        # 'https://shop.test/posts' — the query string dropped
        urls.previous()       # the Referer, or the site root
        urls.previous("/dashboard")   # the Referer, or '/dashboard'
        urls.previous_path()  # '/back' — previous() without the origin
        urls.query("/posts", {"page": 3})  # '…/posts?page=3'
        return {}
```

`query` merges onto whatever the path already carries, so
`query("/posts?a=1", {"b": 2})` gives `/posts?a=1&b=2`. Outside a request
`full()` and `current()` answer the site root instead of raising.

:::note
Laravel's `previous()` reads a session-stored previous URL and falls back to the
`Referer` header. Almasix reads the header only, so a request that arrives
without one lands on the fallback.
:::

## URLs for named routes

`route()` is the reason route names exist. Moving `/posts/{post}` to
`/blog/{post}` becomes one edit in `routes/web.py` instead of a search through
every template:

```python
# routes/web.py
Route.get("/posts/{post}", [PostController, "show"]).name("posts.show")
```

```python
from almasix.routing import route

route("posts.show", 7)   # 'https://shop.test/posts/7'
```

Parameters may be passed in whichever shape reads best at the call site — all
five of these mean the same thing:

```python
route("posts.show", 7)              # a scalar fills a single-parameter route
route("posts.show", [7])            # a list, positionally
route("posts.show", (7,))           # a tuple, positionally
route("posts.show", {"post": 7})    # a mapping, by name
route("posts.show", post=7)         # keyword arguments
```

Keyword arguments are usually clearest once there is more than one:

```python
# /users/{user}/posts/{post}
route("users.posts.show", user=1, post=2)  # 'https://shop.test/users/1/posts/2'
```

A model is read for its route key, so you can pass the object you already have
rather than digging out its id:

```python
route("posts.show", post)  # calls post.get_route_key()
```

Almasix looks for `get_route_key()`, then Laravel's `getRouteKey()`, then
`get_key()`.

### Parameters the URI does not name

A parameter the URI has no place for becomes the query string, which is the
rule that makes pagination and filter links work:

```python
route("posts.show", post=7, page=2)
# 'https://shop.test/posts/7?page=2'

route("posts.index", {"page": 2, "sort": "new"})
# 'https://shop.test/posts?page=2&sort=new'
```

Values are URL-encoded on the way in, so `route("greet", "a b/c")` gives
`/greet/a%20b%2Fc` rather than an extra path segment.

### Optional parameters and relative URLs

An optional parameter may simply be left out, and `absolute=False` drops the
origin while keeping the base path — which is what a `Location` header or an
in-page link wants:

```python
route("greet")                        # 'https://shop.test/greet'
route("greet", "ada")                 # 'https://shop.test/greet/ada'
route("posts.show", 7, absolute=False)  # '/posts/7'
```

### When a name or a parameter is missing

Both failures name what is wrong rather than emitting a broken link:

```python
route("nope")
# RouteNotFound: No route is named 'nope'. Named routes: about, greet, home, …

route("posts.show")
# MissingRouteParameter: The URI '/posts/{post}' names the parameter 'post'
# and nothing supplied it.

route("posts.show", [1, 2, 3])
# MissingRouteParameter: Route 'posts.show' takes 1 parameter(s) (post),
# and 3 were passed.
```

:::note
Laravel appends leftover positional values to the URL as extra path segments.
Almasix raises, because a count that does not match the URI is far more likely
a mistake than an intention.
:::

### Redirecting to a named route

`to_route` builds the redirect response, with a relative `Location` so it works
behind a subpath or a proxy:

```python
# app/http/controllers/post_controller.py
from almasix.routing import to_route


class PostController(Controller):
    async def store(self, request: Request):
        return to_route("posts.show", 7)                # 302 → /posts/7
        # or to_route("posts.index", status=303)
```

### A route's own default parameters

`defaults()` on a route supplies a parameter the URL did not carry, for that
route alone. It wins over the application-wide
[URL defaults](#default-values) below, being the more specific statement about
that one URI:

```python
# routes/web.py
Route.get("/{locale}/about", [PageController, "about"]).name("about").defaults(
    "locale", "en"
)
```

```python
route("about")  # 'https://shop.test/en/about'
```

`defaults` also takes a mapping, and the value it supplies reaches the handler
as well when the URL omitted it.

## Signed URLs

A signed URL carries an HMAC of itself under `APP_KEY`, so a link may be handed
to a user without also handing them the ability to edit it. An "unsubscribe me"
mail can name the subscription in the open, because changing the id
invalidates the signature.

```python
# app/mail/unsubscribe.py
from almasix.routing import signed_route, temporary_signed_route

signed_route("unsubscribe", user.id)
# 'https://shop.test/unsubscribe/7?signature=2f7a4786c8b1…'

temporary_signed_route("unsubscribe", 30, user.id)
# the same, plus ?expires=… — valid for 30 minutes
```

`temporary_signed_route` takes the lifetime **in minutes** as its second
argument, before the parameters. Both accept every parameter shape `route()`
does, and both take `absolute=False`.

### Validating a signature

The `signed` middleware is the usual way to check one — see
[Routing](/routing/#signed-routes). It answers `403` rather than `404`, because
the resource is there and this link is simply not allowed to reach it:

```python
# routes/web.py
Route.get("/unsubscribe/{user}", [UnsubscribeController, "show"]).name(
    "unsubscribe"
).middleware("signed")
```

To check one yourself:

```python
from almasix.routing import has_valid_relative_signature, has_valid_signature

target = signed_route("unsubscribe", 7)

has_valid_signature(target)                            # True
has_valid_signature(target.replace("/7?", "/8?"))      # False — edited
has_valid_signature("https://shop.test/unsubscribe/7") # False — unsigned
```

### Absolute and relative signatures

The two shapes differ in what the signature covers:

- **Absolute** — scheme, host, path, and query. This is what `signed_route`
  produces by default, and it cannot be replayed against another host.
- **Relative** — path and query only, so the link survives a proxy that
  rewrites the origin, and `http` becoming `https`. Produce it with
  `absolute=False`, check it with `has_valid_relative_signature`, and validate
  it on the route with `signed:relative`.

```python
target = signed_route("unsubscribe", 7, absolute=False)
# '/unsubscribe/7?signature=ea8ee073a083…'

has_valid_relative_signature(target)                          # True
has_valid_relative_signature(f"https://elsewhere.test{target}")  # True
has_valid_signature(f"https://shop.test{target}")             # False
```

### Expiry and the details

An expired link fails `has_valid_signature` even though its signature is still
correct. Pass `ignore_expiry=True` to separate the two cases, which is how you
tell a user "this link has expired" instead of "this link is invalid":

```python
import time

from almasix.routing.signing import sign

stale = sign("https://shop.test/unsubscribe/7", expires_at=int(time.time()) - 10)

has_valid_signature(stale)                       # False
has_valid_signature(stale, ignore_expiry=True)   # True — only the deadline passed
```

Three details worth knowing:

- **Query order does not matter.** The parameters are sorted before hashing, so
  a mail client that reorders them — or a router that rebuilds the query —
  does not invalidate the link.
- **Signing is idempotent.** Signing an already-signed URL replaces the
  signature rather than appending a second one.
- **The key is `app.key`,** with the `base64:` prefix that `key:generate`
  writes tolerated. With no application booted a fixed development key is used,
  so a script can sign a URL without bootstrapping.

The lower-level pieces are on `almasix.routing.signing`: `sign(url,
expires_at=…, absolute=…)` signs any URL, `expiry_from(minutes)` (or
`expiry_from(seconds=…)`) builds the timestamp, and `signature_parameters(query)`
strips the two parameters signing owns — `signature` and `expires`.

## URLs for controller actions

`action` generates the URL of a controller action, for a route you would rather
find by its handler than by a name. It takes the same shapes a route
registration does:

```python
from almasix.routing import action, to_action

action([PostController, "index"])       # 'https://shop.test/posts'
action("PostController@index")          # the same route
action([PostController, "show"], 7)     # 'https://shop.test/posts/7'

to_action([PostController, "index"])    # a 302 redirect to /posts
```

Parameters behave exactly as they do for `route()`. An action no route answers
raises `RouteNotFound`.

## Default values

A localized application prefixes every route with `{locale}` and would
otherwise have to pass it at every single call site. `defaults` supplies the
value once:

```python
from almasix.routing import UrlGenerator

urls = UrlGenerator.from_config()
urls.defaults({"locale": "en"})

route("about")                  # 'https://shop.test/en/about'
route("about", locale="fr")     # 'https://shop.test/fr/about' — explicit wins
urls.defaults()                 # {'locale': 'en'} — reads them back
urls.forget_defaults()          # drops the application-wide ones
```

A default only fills a parameter a URI actually **names**. It never becomes a
query string, so setting a `locale` default does not append `?locale=en` to
every other link in the application:

```python
route("posts.show", 7)  # 'https://shop.test/posts/7'
```

### Defaults are request-scoped

:::note
This is a deliberate departure from Laravel, and an important one. Laravel keeps
default parameters on a singleton, which is safe because a PHP process serves
one request at a time. An ASGI process serves many at once, so Almasix keeps a
per-request overlay in a `ContextVar`: a `{locale}` read off *this* request
cannot leak into the links another request is generating on another task, and
the values die with the request that supplied them.
:::

The `url.defaults` middleware opens that overlay, copying the parameters it is
named off the current request:

```python
# routes/web.py
Route.get("/{locale}/dashboard", [DashboardController, "index"]).middleware(
    "url.defaults"
)
Route.get("/{locale}/help", [HelpController, "index"]).name("localized.help")
```

A request to `/fr/dashboard` now generates `https://shop.test/fr/help` from
`route("localized.help")`, and a concurrent request to `/en/dashboard`
generates `https://shop.test/en/help`. The middleware watches `locale` by
default; name others as a comma-separated parameter, `url.defaults:locale,tenant`.

Calling `defaults()` inside a request the middleware opened writes to that
request's overlay; called anywhere else it writes application-wide, which is
what a service provider wants. Defaults resolve most-specific-first: a route's
own `defaults()`, then the request overlay, then the application-wide values.

## Forcing a scheme or a root URL

Behind a proxy that terminates TLS, the application sees `http` and would emit
`http` links. `force_scheme` overrides the scheme of every absolute URL:

```python
urls = UrlGenerator.from_config()
urls.force_scheme("https")
urls.to("/a")           # 'https://shop.test/a'
urls.force_scheme(None) # back to whatever APP_URL says
```

`force_root_url` overrides `APP_URL` itself, for the generator you call it on —
pointing asset URLs at a CDN, say:

```python
urls.force_root_url("https://cdn.test")
urls.to("/a")   # 'https://cdn.test/a'
urls.force_root_url(None)
urls.to("/a")   # '/a' — no root left, so a relative URL
```

:::note
`force_scheme` is process-wide, because a proxy's TLS termination is a property
of the deployment rather than of one generator. `force_root_url` is per
generator instance. Prefer configuring `APP_URL` and trusted proxies — see
[Middleware](/middleware/) — and reach for these only when configuration cannot
express it.
:::

## In Prism templates

Templates receive the whole URL surface without importing anything:

| Injected | What it is |
| --- | --- |
| `url`, `asset` | `url()` and `asset()` |
| `secure_url`, `secure_asset` | The HTTPS-forcing pair |
| `route`, `signed_route` | Named-route generation |
| `action` | Controller-action generation |
| `route_is`, `current_route_name` | The current route, for active nav links |

```html
<!-- resources/views/posts/index.prism.html -->
<a href="{{ route('posts.show', post) }}">{{ post.title }}</a>
<a href="{{ url('/checkout') }}">Checkout</a>
<img src="{{ asset('images/logo.svg') }}" alt="Logo">
<a href="{{ route('posts.index') }}" class="@if(route_is('posts.*'))active@endif">
  Posts
</a>
```

Two directives are shorthand for the two most common calls, and take the same
arguments as the functions:

```html
<!-- resources/views/mail/unsubscribe.prism.html -->
<a href="@route('posts.show', 7)">Read the post</a>
<a href="@signedRoute('unsubscribe', 7)">Unsubscribe</a>
```

Both write an escaped URL, so they are safe inside an attribute.

## Deliberate deviations from Laravel

- **Default parameters are request-scoped**, not process-wide, because an ASGI
  process serves many requests at once. See
  [Defaults are request-scoped](#defaults-are-request-scoped).
- **Leftover positional parameters raise** instead of being appended to the
  URL as path segments.
- **The query string is a `query=` keyword argument**, where Laravel chains a
  fluent `withQuery`.
- **`previous()` reads the `Referer` header only**, not a session-stored
  previous URL.
- **No fluent `Uri` object.** Laravel's immutable URI builder has no Almasix
  equivalent; build URLs with the helpers here and `urllib.parse` for the rest.
- **Every method also answers to its camelCase name** — `secureAsset` is
  `secure_asset`, `hasValidSignature` is `has_valid_signature`, `forceScheme`
  is `force_scheme` — so a Laravel example transcribes without renaming. The
  snake_case name is the documented one.
- **Without a booted application the generator emits relative URLs** rather
  than raising, so a script or a unit test gets a usable answer.

## Related

- [Routing](/routing/) — named routes, the `signed` middleware, resource routes
- [Responses](/responses/) — `redirect()`, `back()`, and everything a
  controller can return
- [Asset Bundling](/asset-bundling/) — Vite, Tailwind, and `public/build`
- [Views](/views/) — the Prism directives and the helpers templates receive
