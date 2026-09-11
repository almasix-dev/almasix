---
title: Routing
description: Define web and API routes with Almasix's Route DSL.
---

Routes map an HTTP verb and a URI to the code that answers it. Almasix splits
the **browser** and **API** surfaces into two files: `routes/web.py` returns
HTML and carries sessions; `routes/api.py` returns JSON and stays stateless by
default.

Register routes with the `Route` façade from `almasix.routing`. Controllers are
resolved from the container.

```python title="routes/web.py"
from app.http.controllers.welcome_controller import WelcomeController

from almasix.routing import Route

Route.get("/", [WelcomeController, "index"])
Route.post("/posts", [WelcomeController, "store"])
```

An action may be written three ways, and they are interchangeable everywhere a
route takes one:

| Shape | Example |
| --- | --- |
| Controller and method | `[PostController, "show"]` |
| Callable | `Route.get("/ping", lambda: {"ok": True})` |
| Dotted string | `"app.http.controllers.post_controller.PostController@show"` |

The string form is imported when the route first answers, so it must be the
full dotted path to the class. Inside a `controller=` group a bare method name
is enough — see [Route groups](#route-groups).

## Route polarity

| File | Audience | Default response | Middleware group |
| --- | --- | --- | --- |
| `routes/web.py` | Browsers | HTML | `web` |
| `routes/api.py` | Clients / SPAs | JSON | `api` |

```python title="routes/web.py"
with Route.group(middleware=["web"]):
    Route.get("/", [WelcomeController, "index"])
```

```python title="routes/api.py"
with Route.group(prefix="/api", middleware=["api"]):
    Route.get("/health", [HealthController, "index"])
```

The `web` group runs session start, cookie encryption, CSRF, and auth
hydration. The `api` group stays stateless — bearer tokens through `auth.start`
only.

## Available router methods

Every HTTP verb has a helper, and each returns the `RouteDefinition` it
registered so the fluent methods on the rest of this page can configure it.

```python title="routes/web.py"
Route.get("/posts", [PostController, "index"])
Route.head("/posts", [PostController, "head"])
Route.post("/posts", [PostController, "store"])
Route.put("/posts/{post}", [PostController, "update"])
Route.patch("/posts/{post}", [PostController, "update"])
Route.delete("/posts/{post}", [PostController, "destroy"])
Route.options("/posts", [PostController, "preflight"])
```

A `get` route also answers `HEAD`, because a client asking only for the headers
of a page that exists should not be told it does not. `route:list` prints it as
`GET|HEAD`. `Route.head` registers `HEAD` alone, for the rare route that wants
to answer a header probe differently from the page itself.

To answer several verbs with one handler, use `match`; to answer all of them,
use `any`:

```python title="routes/web.py"
Route.match(["put", "patch"], "/posts/{post}", [PostController, "update"])
Route.match("delete", "/posts/{post}", [PostController, "destroy"])
Route.any("/webhook", [WebhookController, "receive"])
```

Verb names are case-insensitive, and `match` takes a single verb as a plain
string as well as a list. `any` registers `GET`, `HEAD`, `POST`, `PUT`,
`PATCH`, `DELETE`, and `OPTIONS`.

Every verb helper also takes the common route options as keyword arguments,
which is often shorter than the fluent equivalent:

```python title="routes/web.py"
Route.get(
    "/posts/{post}",
    [PostController, "show"],
    name="posts.show",
    middleware=["auth"],
    where={"post": r"[0-9]+"},
    defaults={"locale": "en"},
    domain="{account}.example.com",
)
```

### Redirect routes

A URI that only exists to point somewhere else does not need a controller:

```python title="routes/web.py"
Route.redirect("/here", "/there")
Route.redirect("/legacy", "/new", 307)
Route.permanent_redirect("/old", "/new")
```

`redirect` answers every verb and sends a `302` unless you pass a status.
`permanent_redirect` is the same thing with a `301`, which is the status a
search engine will remember.

### View routes

A page that renders a template and needs nothing from the database does not
need a controller either:

```python title="routes/web.py"
Route.view("/about", "pages.about", {"title": "About us"})
Route.view("/terms", "pages.terms", status=200, headers={"cache-control": "public"})
```

The route answers `GET` and `HEAD`. The third argument is the data handed to
the template; see [Views](/views/).

### Listing your routes

`route:list` prints what the application answers, sorted by URI:

```bash title="terminal"
python smith route:list
```

```text title="terminal"
Method     URI             Name         Action
---------  --------------  -----------  ----------------------------------------------------
GET|HEAD   /posts          posts.index  app.http.controllers.post_controller.PostController@index
POST       /posts          posts.store  app.http.controllers.post_controller.PostController@store
GET|HEAD   /posts/{post}   posts.show   app.http.controllers.post_controller.PostController@show
```

The options narrow and reshape that table:

| Option | Effect |
| --- | --- |
| `--method=POST` | Only routes answering this verb |
| `--name=posts` | Only routes whose name contains this text |
| `--path=admin` | Only routes whose URI contains this text |
| `--except-path=admin` | Skip routes whose URI contains this text |
| `--domain=hub.test` | Only routes answering on this domain |
| `--action=PostController` | Only routes whose action contains this text |
| `--sort=name` | Sort by `uri`, `name`, `method`, `action`, or `domain` |
| `--reverse` | Reverse the sort |
| `--except-vendor` | Skip routes the framework registered |
| `--only-vendor` | Only routes the framework registered |
| `--middleware` | Add the `Domain` and `Middleware` columns |
| `--json` | Print the routes as JSON instead of a table |

`--middleware` is opt-in because most routes carry a whole middleware group,
and printing it pushes the URI off an eighty-column terminal.

## Route parameters

### Required parameters

A segment in braces is captured and passed to the handler under its own name:

```python title="routes/web.py"
Route.get("/posts/{post}/comments/{comment}", [CommentController, "show"])
```

```python title="app/http/controllers/comment_controller.py"
from almasix.http import Controller


class CommentController(Controller):
    async def show(self, post, comment):
        return {"post": post, "comment": comment}
```

Parameters arrive as strings unless the handler's type hint asks for a model —
see [Route model binding](#route-model-binding). They are also available on the
request through `request.route("post")`, and they are **not** merged into
`request.all()` or `request.input()`, so a query parameter can never impersonate
a path segment.

### Optional parameters

A trailing `?` makes a parameter optional. Almasix registers one path for each
shorter form and lets the handler's own default fill in the gap:

```python title="routes/web.py"
Route.get("/greet/{name?}", lambda name=None: {"name": name or "stranger"})
```

Both `/greet` and `/greet/ada` now answer. Give the handler a default for the
parameter — nothing supplies it on the shorter path. Optional parameters drop
right to left, so `/a/{b?}/{c?}` answers `/a/{b}/{c}`, `/a/{b}`, and `/a`.

### Regular expression constraints

`where` constrains what a parameter may contain. This is not a check inside the
handler: a value that fails the pattern means the route **does not match at
all**, so a later route — or the fallback — gets its chance.

```python title="routes/web.py"
Route.get("/users/{name}", [UserController, "show"]).where("name", r"[A-Za-z]+")
Route.get("/posts/{post}", [PostController, "show"]).where({"post": r"[0-9]+"})
```

The named shorthands cover the patterns most routes want, and each takes
several parameter names at once:

```python title="routes/web.py"
Route.get("/posts/{post}", [PostController, "show"]).where_number("post")
Route.get("/users/{name}", [UserController, "show"]).where_alpha("name")
Route.get("/tags/{tag}", [TagController, "show"]).where_alpha_numeric("tag")
Route.get("/orders/{order}", [OrderController, "show"]).where_uuid("order")
Route.get("/events/{event}", [EventController, "show"]).where_ulid("event")
Route.get("/{category}", [CategoryController, "show"]).where_in(
    "category", ["movie", "song", "painting"]
)
Route.get("/{a}/{b}", handler).where_number("a", "b")
```

`where_in` escapes the values it is given, so a `.` in one of them is a literal
dot rather than "any character".

To constrain a parameter everywhere it appears, register a global pattern once.
`Route.pattern` is normally called from a service provider's `boot`, before the
route files load:

```python title="app/providers/app_service_provider.py"
from almasix.providers.provider import ServiceProvider
from almasix.routing import Route


class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        Route.pattern("id", r"[0-9]+")
        Route.patterns({"slug": r"[a-z-]+", "locale": r"[a-z]{2}"})
```

A route's own `where` wins over the global pattern for that parameter.

Almasix compiles each distinct pattern into one path convertor named after a
hash of the pattern itself, so the same constraint on a thousand routes costs
one convertor and two different patterns never collide. Built-in convertors
survive untouched: `{file:path}` still means a path convertor, not a binding
field.

## Named routes

A name lets you generate a route's URL without repeating its URI, so moving
`/posts/{post}` to `/blog/{post}` is one edit. Name a route fluently or with
the keyword argument — they are the same thing:

```python title="routes/web.py"
Route.get("/posts/{post}", [PostController, "show"]).name("posts.show")
Route.get("/posts", [PostController, "index"], name="posts.index")
```

```python title="app/http/controllers/post_controller.py"
from almasix.routing import route

route("posts.show", 7)  # 'https://example.com/posts/7'
```

[URL Generation](/urls/) documents `route()` and its relatives in full.

A name has to identify exactly one route, or `route()` could not know which URL
to build, so a second route claiming a name already taken raises
`DuplicateRouteName` at registration:

```python title="routes/web.py"
Route.get("/a", handler).name("home")
Route.get("/b", handler).name("home")
# DuplicateRouteName: Two routes are named 'home': /a and /b. …
```

Read a name back with `get_name()`, and test one against a glob with `named()`:

```python title="routes/web.py"
route_definition = Route.get("/posts/{post}", handler).name("posts.show")

route_definition.get_name()             # 'posts.show'
route_definition.named("posts.*")       # True
route_definition.named("users.*", "posts.*")  # True
Route.has("posts.show")                 # True
Route.has("posts.show", "posts.edit")   # False — every name must exist
```

:::note
`name` and `middleware` are methods on the definition. The values they store
live on `route_name` and `middleware_names`, so reading the attribute and
calling the method cannot collide.
:::

## Route groups

A group shares attributes with every route defined inside it. Groups are
**context managers** (`with Route.group(...)`):

```python title="routes/web.py"
with Route.group(prefix="/admin", middleware=["auth"], name="admin."):
    Route.get("/users", [UserController, "index"]).name("users")
    # → /admin/users, middleware ['auth'], named 'admin.users'
```

Every attribute a group accepts:

| Keyword | Effect on the routes inside |
| --- | --- |
| `prefix` | Prepended to the URI (a leading slash is added if you omit it) |
| `middleware` | Appended to each route's middleware |
| `without_middleware` | Exempts each route from middleware applied elsewhere |
| `name` | Prepended to each route's name |
| `domain` | The host the routes answer on |
| `controller` | The controller a bare method name refers to |
| `where` | Constraints applied to each route's parameters |
| `scope_bindings` | Resolve nested parameters through their parent |

Nested groups compose, outermost first. Prefixes and names concatenate,
middleware accumulates in order, and `where` constraints merge; `domain`,
`controller`, and `scope_bindings` take the innermost value that set them.

```python title="routes/api.py"
with Route.group(prefix="/api", middleware=["throttle"], name="api."):
    with Route.group(prefix="/v1", middleware=["auth"], name="v1."):
        Route.get("/users", handler).name("users")
        # → /api/v1/users, ['throttle', 'auth'], 'api.v1.users'
    Route.get("/health", handler)
    # → /api/health, ['throttle'] — the inner frame is already popped
```

### Middleware

Middleware may be attached to a group, passed as a keyword, or added fluently.
All three append to the same list:

```python title="routes/web.py"
Route.get("/dashboard", handler).middleware("auth")
Route.get("/settings", handler).middleware(["auth", "verified"])
Route.get("/billing", handler, middleware=["auth"]).middleware("verified")
```

`without_middleware` exempts a route from middleware a group or the global
stack applied — the webhook that must not run CSRF, most often:

```python title="routes/web.py"
with Route.group(middleware=["web", "csrf"]):
    Route.post("/webhook", handler).without_middleware("csrf")
```

Exclusion matches the name before any parameter, so `without_middleware("auth")`
also removes `auth:api`. Read what will actually run with
`gather_middleware()`. A group can exclude too, with `without_middleware=[…]`.

`can` appends an authorization check as middleware:

```python title="routes/web.py"
Route.put("/posts/{post}", [PostController, "update"]).can("update", Post)
```

Group middleware may name a middleware group (`web` / `api`) or an alias
registered in `bootstrap/app.py` — see [Middleware](/middleware/). For rate
limits, attach `throttle:…` — see [Rate Limiting](/rate-limiting/).

### Controllers

When every route in a group points at the same controller, name it once and
give each route only its method:

```python title="routes/web.py"
with Route.group(controller=PostController, prefix="/posts", name="posts."):
    Route.get("", "index").name("index")
    Route.get("/{post}", "show").name("show")
    Route.post("", "store").name("store")
```

An action that already says which controller it belongs to keeps it, so a
one-off `[OtherController, "index"]` inside the group still works.

### Subdomain routing

`domain` scopes a route to a host, and a `{parameter}` in the pattern is
captured like any other — which is how a multi-tenant application reads the
tenant off the URL:

```python title="routes/web.py"
with Route.group(domain="{account}.example.com"):
    Route.get("/who", lambda account: {"account": account}).name("tenant.who")

Route.get("/panel", [AdminController, "index"]).domain("admin.example.com")
```

The host is matched without its port and case-insensitively, and a
`{subdomain}` parameter is merged into the request's path parameters, so a
controller takes it exactly like a path segment.

:::note
Path matching happens first; Almasix then checks the host on the matched route.
A request that reaches a host-scoped path on the wrong host is handed to the
[fallback route](#fallback-routes) rather than being told the path does not
exist.
:::

### Scoped bindings for a group

`scope_bindings=True` makes every nested parameter in the group resolve through
its parent, which is described under
[Scoped bindings](#scoping-nested-bindings).

## Resource routing

A **CRUD resource** is seven routes with predictable URIs, verbs, and names.
`Route.resource` writes all seven from one line:

```python title="routes/web.py"
Route.resource("photos", PhotoController)
```

| Verb | URI | Action | Route name |
| --- | --- | --- | --- |
| `GET`, `HEAD` | `/photos` | `index` | `photos.index` |
| `GET`, `HEAD` | `/photos/create` | `create` | `photos.create` |
| `POST` | `/photos` | `store` | `photos.store` |
| `GET`, `HEAD` | `/photos/{photo}` | `show` | `photos.show` |
| `GET`, `HEAD` | `/photos/{photo}/edit` | `edit` | `photos.edit` |
| `PUT`, `PATCH` | `/photos/{photo}` | `update` | `photos.update` |
| `DELETE` | `/photos/{photo}` | `destroy` | `photos.destroy` |

The member parameter is the singular of the last segment, snake-cased, so
`photos` gives `{photo}` and `blog_posts` gives `{blog_post}`.

Register several resources at once with `resources`:

```python title="routes/web.py"
Route.resources({"photos": PhotoController, "posts": PostController})
```

Resources register immediately. Fluent methods such as `.only("index")`
**rewrite** the registered routes in place, so a bare
`Route.resource("photos", PhotoController)` needs nothing after it, and chaining
still works.

### Partial resource routes

`only` and `except_` choose which of the seven to register. Either accepts
separate arguments or a list:

```python title="routes/web.py"
Route.resource("photos", PhotoController).only("index", "show")
Route.resource("posts", PostController).except_(["create", "edit", "destroy"])
```

`except` is a Python keyword, so the method is `except_`.

### API resource routes

`create` and `edit` exist only to serve HTML forms, so an API has no use for
them. `api_resource` leaves them out:

```python title="routes/api.py"
Route.api_resource("photos", PhotoController)
Route.api_resources({"photos": PhotoController, "tags": TagController})
```

That registers `index`, `store`, `show`, `update`, and `destroy`.

### Nested resources

A dot nests one resource inside another, and the parent's member parameter
becomes part of the URI:

```python title="routes/web.py"
Route.resource("photos.comments", CommentController)
# GET|HEAD  /photos/{photo}/comments                  photos.comments.index
# POST      /photos/{photo}/comments                  photos.comments.store
# GET|HEAD  /photos/{photo}/comments/{comment}        photos.comments.show
# …
```

A **slash** is not nesting: it is a literal URI prefix, and it does not enter
the route name. `Route.api_resource("api/tags", TagController)` answers at
`/api/tags` and is named `tags.index`, `tags.show`, and so on — the `/api` says
where the resource lives, not what it is called.

#### Shallow nesting

Once a child's own id is in the URL, repeating the parent only invites the two
to disagree. `shallow()` drops the parent segment from the routes that already
identify a member, and names those routes without the parent too:

```python title="routes/web.py"
Route.resource("photos.comments", CommentController).shallow()
# GET|HEAD  /photos/{photo}/comments            photos.comments.index
# GET|HEAD  /photos/{photo}/comments/create     photos.comments.create
# POST      /photos/{photo}/comments            photos.comments.store
# GET|HEAD  /comments/{comment}                 comments.show
# GET|HEAD  /comments/{comment}/edit            comments.edit
# PUT|PATCH /comments/{comment}                 comments.update
# DELETE    /comments/{comment}                 comments.destroy
```

`shallow()` on a resource with no parent changes nothing.

### Naming resource routes

Pass a mapping to rename individual routes, or a single string to replace the
whole name prefix:

```python title="routes/web.py"
Route.resource("photos", PhotoController).names({"index": "photos.all"})
Route.resource("photos", PhotoController).only("show").names("pics")
# → 'pics.show'
```

### Naming resource route parameters

`parameters` renames the URI parameter. A mapping keys the new name by segment;
a bare string sets the member parameter for the whole resource:

```python title="routes/web.py"
Route.resource("users", UserController).only("show").parameters({"users": "admin_user"})
# → /users/{admin_user}

Route.resource("posts", PostController).only("show").parameters("slug")
# → /posts/{slug}
```

### Scoping resource routes

`scoped()` resolves a nested child through its parent, so
`/photos/{photo}/comments/{comment}` cannot return a comment that belongs to
another photo. Passing a mapping also chooses the column the child is looked up
by:

```python title="routes/web.py"
Route.resource("photos.comments", CommentController).scoped({"comment": "slug"})
# → /photos/{photo}/comments/{comment:slug}, resolved through photo.comments
```

Called with no arguments it still scopes; only the lookup column stays the
model's route key.

### Middleware on resource routes

`middleware` takes one name, a list, or a mapping of action to middleware.
`without_middleware` takes the same shapes:

```python title="routes/web.py"
Route.resource("photos", PhotoController).middleware("auth")
Route.resource("posts", PostController).middleware({"store": ["csrf"], "destroy": "admin"})
Route.resource("hooks", HookController).middleware(["web", "csrf"]).without_middleware(
    {"store": "csrf"}
)
```

### Constraints, missing models, and soft deletes

`where`, `missing`, and `with_trashed` carry onto every route the resource
registered, or onto the actions you name:

```python title="routes/web.py"
from almasix.http import json

Route.resource("photos", PhotoController).where({"photo": r"[0-9]+"}).missing(
    lambda request: json({"gone": True}, status=410)
).with_trashed(["show"])
```

`with_trashed()` with no arguments reaches every action;
[`missing`](#customizing-the-missing-model-response) and
[`with_trashed`](#soft-deleted-models) behave exactly as they do on a single
route.

### Resource options up front

Every option that does not need a callable can be passed as a keyword instead
of chained:

```python title="routes/web.py"
Route.resource(
    "photos",
    PhotoController,
    only=["show"],
    names="pics",
    parameters="slug",
    middleware=["auth"],
    where={"slug": r"[a-z-]+"},
    shallow=True,
)
```

`scoped`, `missing`, and `with_trashed` are fluent only.

### Singleton resource routes

Some resources have exactly one member: a user's profile, an application's
settings. A singleton has no id in its URI, and nothing to list:

```python title="routes/web.py"
Route.singleton("profile", ProfileController)
# GET|HEAD   /profile        profile.show
# GET|HEAD   /profile/edit   profile.edit
# PUT|PATCH  /profile        profile.update
```

`creatable()` adds `create`, `store`, and `destroy`, for a singleton that may
not exist yet. `destroyable()` adds only `destroy`:

```python title="routes/web.py"
Route.singleton("profile", ProfileController).creatable()
# create, store, show, edit, update, destroy

Route.singleton("settings", SettingsController).destroyable()
# show, edit, update, destroy
```

`api_singleton` drops the form actions, leaving `show` and `update`.
`singletons` and `api_singletons` register several at once:

```python title="routes/api.py"
Route.api_singleton("profile", ProfileController)
Route.api_singletons({"profile": ProfileController, "settings": SettingsController})
```

Every fluent method a resource has works on a singleton too.

### Localizing resource URIs

`create` and `edit` are the two URI segments that are words rather than data,
so a non-English application will want them translated. Set them once, before
the route files register anything:

```python title="app/providers/app_service_provider.py"
from almasix.providers.provider import ServiceProvider
from almasix.routing import resource_verbs, set_resource_verbs


class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        set_resource_verbs(create="crear", edit="editar")
        # Route.resource("fotos", …) now answers at
        # /fotos/crear and /fotos/{foto}/editar
        resource_verbs()  # {'create': 'crear', 'edit': 'editar'}
```

`set_resource_verbs` leaves alone whichever argument you omit. Only the URI
changes — the route names stay `fotos.create` and `fotos.edit`, so
`route("fotos.create")` keeps working.

## Route model binding

### Implicit binding

A controller that declares `post: Post` should be handed a `Post`, not the
string `"7"`. Type-hint the parameter with a model whose name matches the URI
parameter and Almasix looks it up for you:

```python title="routes/web.py"
Route.get("/posts/{post}", [PostController, "show"])
```

```python title="app/http/controllers/post_controller.py"
from app.models.post import Post

from almasix.http import Controller


class PostController(Controller):
    async def show(self, post: Post):
        return {"title": post.title}
```

An id no row carries is a `404`. A parameter hinted as `str` or `int` — or not
hinted at all — arrives as the raw string, so nothing is queried behind your
back.

### Customizing the key

The lookup column is the model's route key, which is its primary key unless the
model says otherwise:

```python title="app/models/post.py"
from almasix.orm import Model


class Post(Model):
    table = "posts"

    @staticmethod
    def get_route_key_name() -> str:
        return "slug"
```

:::note
`get_route_key_name` is read off the **class**, so declare it as a
`staticmethod` or a `classmethod`. A plain instance method cannot be called
without an instance, and Almasix falls back to the primary key rather than
raising at routing time.
:::

To bind by a column for one route only, name it in the URI after a colon:

```python title="routes/web.py"
Route.get("/posts/{post:slug}", [PostController, "show"])
Route.get("/users/{user:slug}/posts/{post}", [PostController, "show"])
```

The binding field is read off the URI and does not appear in the compiled path,
so the URL is still `/posts/routing`. `route_definition.binding_fields()`
reports the mapping — `{"post": "slug"}`.

### Scoping nested bindings

When one parameter nests inside another, `scope_bindings()` resolves the child
through the parent's relationship, so a URL cannot mix a comment with a photo
that does not own it:

```python title="routes/web.py"
Route.get("/posts/{post}/comments/{comment}", handler).scope_bindings()

with Route.group(scope_bindings=True):
    Route.get("/posts/{post}/comments/{comment}", handler)
```

The parent is the nearest parameter to the left that resolved to a model — a
scalar such as a `{locale}` is skipped — and the relationship read on it is the
plural of the child's parameter name, so `{comment}` looks for
`post.comments`. `without_scoped_bindings()` turns scoping back off for one
route inside a group that enabled it.

### Customizing the missing model response

A `404` is the right answer when a row is gone, but not always the most useful
one. `missing` says what to answer instead:

```python title="routes/web.py"
from almasix.http import json

Route.get("/posts/{post}", [PostController, "show"]).missing(
    lambda request: json({"gone": True}, status=410)
)
```

The handler is called with the request when it takes an argument, and with
nothing when it does not.

### Soft deleted models

Binding ignores soft-deleted rows by default. `with_trashed()` lets it find
them, which is what a "restore this post" screen needs:

```python title="routes/web.py"
Route.get("/posts/{post}/restore", [PostController, "restore"]).with_trashed()
```

### Implicit enum binding

An enum parameter is resolved to its member, by value or by name, so an
invalid value is a `404` before the handler runs rather than a `500` inside it.
Int-backed enums work too — the path segment is compared as a string:

```python title="app/enums/category.py"
import enum


class Category(enum.Enum):
    FRUITS = "fruits"
    PEOPLE = "people"


class Rank(enum.IntEnum):
    FIRST = 1
    SECOND = 2
```

```python title="app/http/controllers/category_controller.py"
from app.enums.category import Category, Rank

from almasix.http import Controller


class CategoryController(Controller):
    async def show(self, category: Category, rank: Rank):
        return {"category": category.value, "rank": rank.name}
```

```python title="routes/web.py"
Route.get("/categories/{category}/ranks/{rank}", [CategoryController, "show"])
```

`/categories/fruits` and `/categories/FRUITS` both give `Category.FRUITS`, and
`/ranks/2` gives `Rank.SECOND`. `/categories/green` is a `404`. As with models,
the resolution comes from the **type hint** — an unhinted parameter arrives as
the raw string.

### Explicit binding

Explicit bindings are registered by parameter name, apply everywhere that name
appears, and **win over the type hint**. Register them in a service provider's
`boot`.

`Route.model` binds a parameter to a model, with an optional handler for the
miss:

```python title="app/providers/app_service_provider.py"
from app.models.post import Post

from almasix.http import json
from almasix.providers.provider import ServiceProvider
from almasix.routing import Route


class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        Route.model("post", Post)
        Route.model("draft", Post, lambda: json({"gone": True}, status=410))
```

`Route.bind` takes a callable instead, for a parameter that is not a model
lookup at all. It receives the raw path value, and its result is awaited when
the callable returns something awaitable:

```python title="app/providers/app_service_provider.py"
from app.models.post import Post

from almasix.providers.provider import ServiceProvider
from almasix.routing import Route


class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        Route.bind("code", lambda value: value.upper())
        Route.bind("post", lambda value: Post.query().where("slug", value).first())
```

## Fallback routes

A fallback answers anything no other route claimed, which is how an
application renders its own "not found" page instead of the framework's:

```python title="routes/web.py"
from almasix.http import json

Route.fallback(lambda: json({"fell": "through"}, status=404))
```

The fallback is registered last however early you declare it, so it only
catches what nothing else did. A second call replaces the first — an
application has one catch-all or none. It accepts `name=` and `middleware=`.

## Form method spoofing

An HTML form can send `GET` and `POST` and nothing else, so a form that means
`PUT` says so in a hidden field. `method_field()` writes it:

```html title="resources/views/posts/edit.prism.html"
<form action="{{ route('posts.update', post) }}" method="POST">
  @csrf
  {!! method_field('PUT') !!}
  <button>Save</button>
</form>
```

Clients that cannot send a body may use the `X-HTTP-Method-Override` header
instead:

```python title="tests/feature/posts_test.py"
response = client.post("/posts/1", headers={"X-HTTP-Method-Override": "PUT"})
```

The rules are narrow on purpose:

- Only a **POST** is examined. A `GET` carrying `_method=DELETE` is left alone,
  because otherwise a plain link could delete something.
- Only `PUT`, `PATCH`, and `DELETE` may be claimed. Anything else — including
  `GET` — is ignored and the request stays a `POST`.
- The field is read from `application/x-www-form-urlencoded` and
  `multipart/form-data` bodies; the header form is read whatever the body is.

The handler sees the spoofed verb on `request.method` and the verb that
actually arrived on `request.real_method`; `request.spoofed_method` is the verb
`_method` asked for, or `None`. Set `http.spoof_methods` to `False` in
`config/http.py` to switch the whole mechanism off.

:::note
Spoofing runs as ASGI middleware, before routing, because the router matches on
the verb in the scope: a form posting to a `PUT`-only route would be told `405`
before any handler ran. The body is buffered and replayed only for a POST that
could be carrying the field, and only up to one mebibyte.
:::

## Accessing the current route

The `Route` façade reads the route answering the request in flight:

```python title="app/http/controllers/nav_controller.py"
from almasix.http import Controller
from almasix.routing import Route


class NavController(Controller):
    async def index(self):
        Route.current()               # the RouteDefinition, or None
        Route.current_route_name()    # 'posts.show'
        Route.current_route_action()  # 'PostController@show'
        Route.is_("posts.*")          # True — 'is' is a Python keyword
        return {}
```

Outside a request every one of them answers `None` or `False` rather than
raising, so console and queue code can ask freely.

The request carries the same information:

```python title="app/http/controllers/nav_controller.py"
async def index(self, request: Request):
    request.route_name          # 'posts.show'
    request.route_is("posts.*") # True
    request.route_named("posts.show")  # same test
    request.matched_route       # the RouteDefinition
    request.route("post")       # a path parameter
```

In a Prism template `route_is` and `current_route_name` are injected already,
which is how a navigation link marks itself active:

```html title="resources/views/partials/nav.prism.html"
<a href="{{ route('posts.index') }}" class="@if(route_is('posts.*'))active@endif">
  Posts
</a>
```

## Signed routes

The `signed` middleware rejects a link whose signature no longer matches, or
whose deadline has passed, with a `403` — the resource is there, this link is
just not allowed to reach it:

```python title="routes/web.py"
Route.get("/unsubscribe/{user}", [UnsubscribeController, "show"]).name(
    "unsubscribe"
).middleware("signed")

Route.get("/invite/{token}", [InviteController, "show"]).middleware("signed:relative")
```

`signed` checks the whole URL, origin included. `signed:relative` checks only
the path and query, which is what a proxy that rewrites the host needs. Both
aliases are provided by the framework, so a route can name them without
`bootstrap/app.py` aliasing anything. [URL Generation](/urls/) covers the other
half: `signed_route` and `temporary_signed_route`.

## Websocket routes

ASGI supports long-lived connections. Register one with `Route.websocket`:

```python title="routes/web.py"
Route.websocket("/live", LiveHandler())
```

The action is called with the websocket and owns the connection for its
lifetime. Websocket routes take a `name` and `middleware` the same way HTTP
routes do, and honour a group's prefix and name — but HTTP middleware does not
run, because Almasix's middleware is request-in / response-out and a socket is
neither. A handler authorizes each frame itself.
[Broadcasting](/broadcasting/) does exactly that, and its socket endpoint is
worth reading as the worked example.

## Python-friendly details

A few naming and registration rules come from Python itself:

- **Groups** use `with Route.group(...)` context managers.
- **Resources** register immediately; fluent methods rewrite them in place.
- **`except_` and `is_`** use a trailing underscore because `except` and `is`
  are Python keywords.
- **Route options** may be keyword arguments
  (`Route.get(uri, action, name="x")`) as well as fluent calls.
- Fluent methods also answer to camelCase aliases (`whereNumber` →
  `where_number`); the snake_case name is the documented one.
- **Route files are plain Python** and load once at boot — there is no separate
  route-cache command.
- For CORS and rate limits, see [Security](/security/) and
  [Rate Limiting](/rate-limiting/).

## Related

- [Middleware](/middleware/) — aliases, `web` / `api` stacks, `signed`
- [Controllers](/controllers/) — actions, dependency injection, resource controllers
- [URL Generation](/urls/) — `route()`, `signed_route()`, `url()`, `asset()`
- [Requests](/requests/) — `request.route()`, `real_method`, input bags
- [Articulate](/articulate/) — models, route keys, soft deletes
- [Rate Limiting](/rate-limiting/) — `throttle` middleware
