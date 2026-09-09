---
title: Authorization
description: Gates, policies, auto-discovery, custom abilities, @can, and the can middleware.
---

## Introduction

Authentication answers *who* the user is. **Authorization** answers *what they
may do*. Almasix ships Laravel-shaped Gates and Policies on `almasix.auth`:

```python
from almasix.auth import Gate, Policy, authorize
```

Register abilities in a provider `boot()` method (typically
`app/providers/app_service_provider.py`) after the kernel boots. Checks are
synchronous so they work in controllers, Form Requests, and Prism templates.

## Where the files live

| Role | Path |
| --- | --- |
| Register gates / policies | `app/providers/app_service_provider.py` (`boot()`) |
| User model (`can` / `cannot`) | `app/models/user.py` — `AuthenticatableMixin` already includes `Authorizable` |
| Policy classes | `app/policies/<model>_policy.py` (created by `smith make:policy`) |
| Models | `app/models/<model>.py` |
| Controllers | `app/http/controllers/…` |
| Form requests | `app/http/requests/…` |
| Route `can` middleware | `routes/web.py` / `routes/api.py` |
| Prism `@can` | `resources/views/….prism.html` |
| Alias `can` | `bootstrap/app.py` (installer wires `can` → `Authorize`) |

## Gates

A gate is a named closure. Define it in a provider — **not** at import time on
a model module — so the bound `Gate` façade exists:

```python
# app/providers/app_service_provider.py
from almasix.auth import Gate
from almasix.providers.provider import ServiceProvider

class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        Gate.define("view-dashboard", lambda user: user is not None)
        Gate.define("update-post", lambda user, post: user.id == post.user_id)
```

The first argument is always the user (or `None` for guests).

### Allowing guests

If the user parameter is optional, guests may pass:

```python
def view_post(user=None, post=None):
    return post is not None and post.published

Gate.define("view-post", view_post)
```

A required user parameter **denies** guests without calling the callback.
`user: User | None`, `user: Optional[User]`, or `user=None` all count as optional.

### Checking abilities

```python
if Gate.allows("update-post", post):
    ...

Gate.denies("update-post", post)
Gate.check(["update-post", "delete-post"], post)  # all must pass
Gate.any(["update-post", "delete-post"], post)
Gate.none(["update-post", "delete-post"], post)

Gate.authorize("update-post", post)  # raises AuthorizationException (403)
response = Gate.inspect("update-post", post)  # AuthorizationResponse
```

Helpers `gate()` and `authorize()` mirror the façade.

Callbacks may be a lambda, a `handle()` class, a `"pkg.mod.Class@method"`
string, or `[PolicyClass, "method"]`.

### Another user

```python
Gate.for_user(other).allows("update-post", post)
```

### Intercepting checks

```python
Gate.before(lambda user, ability: True if getattr(user, "admin", False) else None)
Gate.after(lambda user, ability, result, arguments: result)
```

`before` / `after` returning non-`None` win. Admins typically `return True` from
`before`.

`Gate.default_deny_response(...)` customizes the message/status when a check
returns `False` / `None`.

## Authorizable users

`AuthenticatableMixin` includes `Authorizable`. You do **not** register this
separately — any user loaded by the auth guard already has:

```python
user.can("update-post", post)
user.cannot("update-post", post)
user.cant("update-post", post)       # alias of cannot
user.can_any(["update", "delete"], post)
user.canany(["update", "delete"], post)
```

Those methods call `Gate.for_user(self)` so they do not depend on the current
request user.

## Policies

Policies group abilities for a model. Generate a stub:

```bash
smith make:policy PostPolicy --model=Post --resource
# writes app/policies/post_policy.py
```

`--resource` (implied when `--model` is set) stubs `view_any`, `view`, `create`,
`update`, `delete`, `restore`, and `force_delete`.

```python
# app/policies/post_policy.py
from almasix.auth import Policy
from app.models.post import Post

class PostPolicy(Policy):
    def before(self, user, ability):
        if getattr(user, "admin", False):
            return True
        return None

    def view_any(self, user) -> bool:
        return user is not None

    def update(self, user, post: Post) -> bool:
        return user.id == post.user_id

    def delete(self, user, post: Post):
        if user.id == post.user_id:
            return True
        return self.deny("You do not own this post.")
```

`Policy` includes `allow`, `deny`, `deny_with_status`, and `deny_as_not_found`
(HTTP 404).

### Registering policies

**Explicit (recommended in `boot()`):**

```python
# app/providers/app_service_provider.py
from almasix.auth import Gate
from app.models.post import Post
from app.policies.post_policy import PostPolicy

class AppServiceProvider(ServiceProvider):
    def boot(self) -> None:
        Gate.policy(Post, PostPolicy)
        # or many at once (Laravel AuthServiceProvider::$policies):
        Gate.register_policies({
            Post: PostPolicy,
        })
```

### Auto-discovery (if you skip `Gate.policy`)

When Almasix authorizes against a model and no mapping exists, it **guesses** a
policy class, in order:

1. The model's `policy` attribute, if it is a class:
   `class Post: policy = PostPolicy`
2. Custom guessers from `Gate.guess_policy_names_using(...)`
3. Default paths from the model name / module:

   | Model | Guessed import |
   | --- | --- |
   | `Post` | `app.policies.post_policy.PostPolicy` |
   | `app.models.post.Post` | `app.policies.post_policy.PostPolicy` |
   | `app.models.blog.post.Post` | `app.policies.blog.post_policy.PostPolicy` **and** `app.policies.blog.post.PostPolicy` |

Guessing **imports** that class if it exists. There is no directory scanner —
put the policy on the guessed path, or register it explicitly.

`Gate.guess_policy_names_using` **replaces** the default guesser (it does not
append). Return a class, an import string, a list of either, or `None`:

```python
Gate.guess_policy_names_using(
    lambda model: f"app.policies.{model.__name__.lower()}_policy.{model.__name__}Policy"
)
```

### Custom policy methods

Any method on the policy is an ability. There is no extra registration step.

1. Add the method to `app/policies/post_policy.py`:

   ```python
   def publish(self, user, post: Post) -> bool:
       return user.id == post.user_id and not post.published

   def assign_editor(self, user, post: Post, editor) -> bool:
       return user.admin
   ```

2. Call it by **method name** (snake or camelCase) against an instance or class:

   ```python
   Gate.allows("publish", post)
   user.can("publish", post)
   self.authorize("publish", post)
   Gate.allows("assign_editor", [post, editor])
   ```

3. Optional HTTP wiring:

   ```python
   # routes/web.py
   Route.post("/posts/{post}/publish", [PostController, "publish"]).can("publish", "post")

   # controller
   class PostController(Controller):
       async def publish(self, post: Post):
           self.authorize("publish", post)

   # form request
   class PublishPostRequest(FormRequest):
       def authorize(self):
           return Gate.allows("publish", self.route("post"))
   ```

   ```html
   @can('publish', post)
     <button>Publish</button>
   @endcan
   ```

Resource actions (`index`/`show`/`store`/`update`/`destroy`) still map to the
standard CRUD names; custom methods are only used when you authorize that name.

Authorize against an **instance** (`update`, `publish`) or a **class**
(`create` / `view_any`):

```python
Gate.allows("update", post)
Gate.allows("create", Post)
```

### Resource gates

Named abilities on a policy without going through model matching:

```python
Gate.resource("posts", PostPolicy)
Gate.allows("posts.update", post)
Gate.resource("posts", PostPolicy, abilities={"publish": "publish"})
Gate.allows("posts.publish", post)
```

## Controllers and Form Requests

Controllers inherit `authorize` / `authorize_for_user` / `can` / `cannot` /
`authorize_when` / `authorize_unless`:

```python
class PostController(Controller):
    async def update(self, post: Post):
        self.authorize("update", post)
        ...

    async def publish(self, post: Post):
        self.authorize_when(post.draft, "publish", post)
```

Set `authorizes_resource = Post` (or `(Post, "post")`) to map resource actions
(`index` → `view_any`, `show` → `view`, `store` → `create`, `update` →
`update`, `destroy` → `delete`) before the action runs.

Form Requests may return a bool or an `AuthorizationResponse`:

```python
# app/http/requests/update_post_request.py
class UpdatePostRequest(FormRequest):
    def authorize(self):
        return Gate.allows("update", self.route("post"))
```

`False` still raises HTTP 403.

## Route middleware

The `can` alias is registered in `bootstrap/app.py`:

```python
Route.put("/posts/{post}", [PostController, "update"]).can("update", "post")
# equivalent: middleware=["can:update,post"]
```

Pass a class path for class-based abilities: `can:create,app.models.post.Post`.

## Prism

```html
@can('update', post)
  <a href="/posts/edit">Edit</a>
@else
  <span>Read only</span>
@endcan

@cannot('delete', post)
  ...
@endcannot

@canany(['update', 'delete'], post)
  ...
@endcanany
```

`@cannotany` is the inverse of `@canany`.

## Testing

```python
from almasix.auth import Gate, AuthorizationException

Gate.flush()
Gate.define("ping", lambda user: True)
assert Gate.for_user(user).allows("ping")
```

`AuthorizationException` is an `HttpException` (403, or 404 when a policy
uses `deny_as_not_found`).
