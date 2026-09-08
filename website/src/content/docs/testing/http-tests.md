---
title: HTTP Tests
description: Drive the application in-process — requests through the real middleware stack, and a response that can be asked about its status, headers, JSON, session, and views.
---

## Introduction

`TestClient` makes requests against the application's own ASGI app in-process:
no socket, no server, and the full middleware stack. Every request is a
coroutine, because every request Almasix serves is one.

```python
class HomeTest(TestCase):
    async def test_the_home_page_answers(self) -> None:
        response = await self.get("/")

        response.assert_ok().assert_see("Welcome")
```

`TestCase` delegates `get`, `post`, `put`, `patch`, `delete` and their `*_json`
siblings to the client, so `self.get(...)` and `self.client.get(...)` are the
same call.

## Making requests

```python
await self.get("/posts", params={"page": 2})
await self.post("/posts", {"title": "Hello"})       # form fields
await self.post_json("/api/posts", {"title": "Hi"})  # JSON in, JSON expected
await self.put("/posts/1", {"title": "Edited"})
await self.delete("/posts/1")
await self.post("/webhook", "raw body text")
```

| Method | Sends |
| --- | --- |
| `get` / `post` / `put` / `patch` / `delete` | Form fields, or a string as the raw body |
| `get_json` / `post_json` / `put_json` / `patch_json` / `delete_json` | JSON, with `Accept: application/json` |
| `options` / `head` | Nothing |

`files=` uploads, `headers=` and `cookies=` add to what the client already
carries, and `follow_redirects=` overrides the client's setting for one call.

### Headers, cookies, and tokens

Whatever is set on the client travels with every request it makes:

```python
self.with_headers({"X-Request-Id": "abc"})
self.with_header("Accept-Language", "sw")
self.with_token("a-bearer-token")            # Authorization: Bearer ...
self.client.with_basic_auth("ada", "secret")
self.client.without_token()
self.client.flush_headers()

self.client.with_cookie("theme", "dark")
self.client.with_cookies({"theme": "dark", "seen": "1"})
```

Cookies the application sets are kept, so a login in one request is still a
login in the next.

### Sessions and authentication

```python
self.with_session({"cart": ["cog", "sprocket"]})
self.acting_as(user)             # signed in on the `web` guard
self.acting_as(user, "admin")    # or another one
self.client.flush_session()
```

`with_session` seeds the session the next request starts with, the way a
browser would carry it. `acting_as` writes the guard's own login payload, so
the request arrives authenticated without going through the login form.

### Redirects

Redirects are not followed unless you ask:

```python
response = await self.get("/go-away")
response.assert_redirect("/hello")

followed = await self.client.following_redirects().get("/go-away")
followed.assert_ok()
```

`self.from_("/posts")` sets the `Referer`, for a controller that redirects back.

## Asserting on the response

Every assertion returns the response, so they chain, and every failure says
what the response actually was.

### Status

```python
response.assert_ok()             # 200
response.assert_created()        # 201
response.assert_accepted()       # 202
response.assert_no_content()     # 204, and an empty body
response.assert_successful()     # 2xx
response.assert_redirect()       # 3xx, or a named location
response.assert_bad_request()    # 400
response.assert_unauthorized()   # 401
response.assert_payment_required()  # 402
response.assert_forbidden()      # 403
response.assert_not_found()      # 404
response.assert_method_not_allowed()  # 405
response.assert_not_acceptable()      # 406
response.assert_conflict()       # 409
response.assert_gone()           # 410
response.assert_unprocessable()  # 422
response.assert_too_many_requests()   # 429
response.assert_server_error()   # 5xx
response.assert_status(418)
```

A failing status assertion quotes the body, because that is nearly always what
explains it.

### Headers and cookies

```python
response.assert_header("X-Pot")
response.assert_header("X-Pot", "tea")
response.assert_header_missing("X-Debug")
response.assert_content_type("application/json")
response.assert_cookie("session")
response.assert_cookie("theme", "dark")
response.assert_cookie_missing("tracker")
response.assert_location("/hello")
response.assert_redirect_contains("hello")
response.assert_download("report.csv")
```

### The body

```python
response.assert_see("Hello")              # HTML-escaped, like Laravel's
response.assert_see("<b>", escape=False)
response.assert_dont_see("Goodbye")
response.assert_see_text("Almasix & friends")   # tags stripped first
response.assert_dont_see_text("Goodbye")
response.assert_see_in_order(["First", "Second"])
response.assert_content("exactly this")
response.assert_streamed_content("exactly this")
```

`response.text`, `response.content`, `response.status`, `response.headers`, and
`response.cookies` are there when an assertion is not what you want.

### JSON

```python
response.assert_json({"ok": True})              # these pairs are in the body
response.assert_json({"ok": True}, strict=True) # and nothing else is
response.assert_exact_json({"ok": True})
response.assert_json_path("user.name", "Ada")
response.assert_json_path("user.id", lambda value: value > 0)
response.assert_json_missing_path("user.password")
response.assert_json_fragment({"title": "Search"})
response.assert_json_missing({"title": "Nothing"})
response.assert_json_count(2, "posts")
response.assert_json_structure({"user": ["id", "name"], "posts": {"*": ["id"]}})
response.assert_json_is_array("posts")
response.assert_json_is_object()

assert response.json("user.roles") == ["author", "admin"]
assert response.json()["ok"] is True
```

Paths are dotted, and `*` in a structure means "every item looks like this".

### Validation errors

```python
response.assert_invalid()                       # some field failed
response.assert_invalid("email")
response.assert_invalid(["email", "name"])
response.assert_invalid({"email": "is required"})
response.assert_valid()                         # nothing failed
response.assert_valid("email")                  # this field did not
assert response.errors() == {"email": ["Required."]}
```

`assert_session_has_errors` and `assert_session_has_no_errors` read the same
errors, for a form that redirects back rather than answering with JSON.

### The session

```python
response.assert_session_has("cart")
response.assert_session_has("cart", ["cog"])
response.assert_session_has("total", lambda value: value > 0)
response.assert_session_has_all({"cart": ["cog"], "step": 2})
response.assert_session_missing("token")
assert response.session("cart") == ["cog"]
```

### Views

```python
response.assert_view_is("posts.index")
response.assert_view_has("posts")
response.assert_view_has("title", "Posts")
response.assert_view_missing("secret")
```

The client records what Prism rendered while the request ran, so these read the
data the template was given rather than the HTML it produced.

### Debugging

`response.dump()` prints the status, the headers, and the body — the response
equivalent of `dd()`.

## Middleware

A test can stand middleware down for the rest of the test:

```python
from almasix.testing import with_middleware, without_middleware

self.without_middleware()                     # all of it
without_middleware(self.app, "csrf")          # by alias
without_middleware(self.app, [VerifyCsrfToken])  # by class
with_middleware(self.app)                     # put it all back
```

Prefer testing with the middleware in place; a route whose protection is only
ever bypassed in tests is a route nobody has tested.
