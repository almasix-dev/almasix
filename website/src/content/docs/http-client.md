---
title: HTTP Client
description: Outbound Http.get/post façade with fakes, retry, pool, and async.
---

## Introduction

Almasix’s HTTP client lives in `almasix.client`. It is the Laravel-shaped
wrapper around **httpx** for *outbound* requests (calling other APIs). Inbound
HTTP stays in `almasix.http`.

```python
from almasix.client import Http

response = Http.get("https://api.example.test/users")
response.json()
response.status()   # 200
response.ok()       # True
```

The `ClientServiceProvider` (registered with the foundation) binds a process-wide
`Factory`. You rarely construct it yourself.

## File map

| Piece | Path |
| --- | --- |
| Façade | `src/almasix/client/facade.py` — `Http` |
| Pending request | `src/almasix/client/pending.py` — `PendingRequest` |
| Response | `src/almasix/client/response.py` — `Response` |
| Fakes / recording | `src/almasix/client/factory.py` — `Factory`, `Sequence` |
| Pool | `src/almasix/client/pool.py` — `Pool`, `PoolRequest` |
| Batching | `src/almasix/client/batch.py` — `Batch` |
| Events | `src/almasix/client/events.py` |
| URI templates | `src/almasix/client/uri_template.py` |
| Provider | `src/almasix/client/provider.py` — `ClientServiceProvider` |
| Exceptions | `src/almasix/client/exceptions.py` |

## Making requests

```python
Http.get(url, query={"page": 1})
Http.head(url)
Http.post(url, {"name": "Ada"})
Http.put(url, {"name": "Ada"})
Http.patch(url, {"name": "Ada"})
Http.delete(url)
Http.options(url)
Http.send("GET", url)
```

Dict / list bodies default to JSON. Use `as_form()` or `as_multipart()` when you
need form encoding, `with_body(content, content_type)` to send a raw payload, or
`body_format()` to pick one of `json` / `form` / `multipart` / `body` directly —
anything else raises `PendingRequestException`.

```python
Http.with_body(base64.b64encode(photo), "image/jpeg").post(url)
```

### Fluent options

```python
Http.with_headers({"X-Trace": "1"}).get(url)
Http.with_token("secret").get(url)                 # Bearer
Http.with_basic_auth("user", "pass").get(url)
Http.with_query_parameters({"page": 2}).get(url)
Http.base_url("https://api.example.test").get("/users")
Http.timeout(5).connect_timeout(2).get(url)
Http.accept_json().as_json().post(url, {"ok": True})
```

`when` / `unless` wrap optional configuration:

```python
Http.when(use_token, lambda http: http.with_token(token)).get(url)
```

### URI templates

`with_url_parameters()` expands the URL as an [RFC 6570](https://www.rfc-editor.org/rfc/rfc6570)
URI template. Simple expansion percent-encodes reserved characters, so use the
`+` operator when a value is itself a URL:

```python
Http.with_url_parameters({
    "endpoint": "https://laravel.com",
    "page": "docs",
    "version": "12.x",
    "topic": "validation",
}).get("{+endpoint}/{page}/{version}/{topic}")
# -> https://laravel.com/docs/12.x/validation
```

The `+`, `#`, `.`, `/`, `;`, `?`, and `&` operators are supported, along with
the `*` (explode) and `:n` (prefix) modifiers. URLs are left untouched when no
URL parameters are set.

### Attachments and sink

```python
Http.attach("photo", open("me.jpg", "rb"), "me.jpg").post(url)
Http.sink("/tmp/body.bin").get(url)
```

## Inspecting responses

```python
r = Http.get(url)
r.body()            # str
r.content()         # bytes
r.json()            # parsed object
r.json("name")      # dict key
r.object()          # SimpleNamespace
r.collect()         # Support Collection
r.header("Content-Type")
r.ok() / r.successful() / r.failed()
r.client_error() / r.server_error()
r.redirect()
r.unauthorized() / r.forbidden() / r.not_found()
r["name"]           # json key
```

### Throwing on error

```python
Http.throw().get(url)                 # raises RequestException on 4xx/5xx
Http.throw(lambda r: log(r.status())).get(url)   # callback runs once, then raises
Http.get(url).throw()
Http.throw_if(True).get(url)
Http.throw_unless(healthy).get(url)
response.throw_if_status(403)
response.throw_unless_status(200)
response.on_error(lambda r: log(r.status()))
```

Successful responses are never thrown, so `throw_if(True)` on a 200 is a no-op.
`RequestException` exposes the `Response` as `exc.response` and forwards
attribute access to it, so `exc.status()` and `exc.json()` work directly.

The exception message includes the response body, truncated to 120 characters:

```python
from almasix.client import RequestException

RequestException.truncate_at(240)          # globally, e.g. from a provider
RequestException.dont_truncate()
Http.truncate_exceptions_at(240).get(url)  # for one request
```

### Exceptions

| Exception | Raised when |
| --- | --- |
| `RequestException` | a failed response meets a `throw` policy or retries are exhausted |
| `ConnectionException` | httpx could not complete the request (DNS, refused, timeout) |
| `StrayRequestException` | a request has no matching fake and strays are prevented |
| `OutOfFakeResponses` | a fake sequence is drained |
| `PendingRequestException` | the pending request is misconfigured (e.g. unknown body format) |
| `BatchInProgressException` | a batch that has already been sent is modified |

All of them subclass `HttpClientException`.

## Retry

```python
# up to 3 attempts in total; sleep is milliseconds between attempts
Http.retry(3, 100).get(url)

# compute the delay per attempt
Http.retry(3, lambda attempt, error: attempt * 100).get(url)

# or list the delays; the attempt count follows from the list
Http.retry([100, 200]).get(url)

# narrow what counts as retryable, and keep the last response instead of raising
Http.retry(3, 100, when=lambda error: error.server_error(), throw=False).get(url)
```

`times` is the **maximum number of attempts**, not the number of extra ones, so
`retry(3)` sends the request at most three times.

By default every failed response (4xx/5xx) and every `ConnectionException` is
retried. Once the attempts are exhausted a `RequestException` is raised — pass
`throw=False` to get the last failed response back instead. A
`ConnectionException` always propagates when the attempts run out.

The `when` callback receives the failure as an exception — `RequestException`
for a failed response, `ConnectionException` for a transport failure — and, if
it accepts a second argument, the live `PendingRequest`. Reconfiguring that
request applies to the next attempt:

```python
def refresh_token(error, request):
    if error.response.status() != 401:
        return False
    request.with_token(new_token())
    return True

Http.with_token(token).retry(2, 0, refresh_token).post(url)
```

## Concurrent pool

```python
responses = Http.pool(lambda pool: (
    pool.get("https://api.example.test/a"),
    pool.as_("users").get("https://api.example.test/users"),
    pool.post("https://api.example.test/x", {"n": 1}),
))
responses[0].ok()
responses["users"].json()
```

Pool jobs run on a thread pool, capped by `concurrency` (default 8). Fakes still
apply. `pool` itself cannot be configured, so set headers and other options on
each request:

```python
responses = Http.pool(lambda pool: [
    pool.with_headers({"X-Example": "example"}).get(url),
    pool.as_("token").with_token("secret").get(other),
], concurrency=5)
```

A request that fails hard puts the exception in the results instead of sinking
the whole pool, so a value may be a `Response`, a `ConnectionException`, or a
`RequestException`.

## Batching

`Http.batch()` is a pool with completion callbacks:

```python
from almasix.client import Batch

results = Http.batch(lambda batch: [
    batch.get("https://api.example.test/first"),
    batch.as_("second").get("https://api.example.test/second"),
]).before(lambda batch: ...
).progress(lambda batch, key, response: ...
).then(lambda batch, results: ...
).catch(lambda batch, key, outcome: ...
).finally_(lambda batch, results: ...
).concurrency(5).send()
```

`then` only runs when every request succeeded; `catch` fires per failure (a
failed response or a client exception) and `finally_` always runs. Python
reserves `finally`, hence the trailing underscore.

Inspect a batch from inside those callbacks or after `send()`:

```python
batch.total_requests
batch.pending_requests
batch.failed_requests
batch.processed_requests()
batch.finished()
batch.has_failures()
batch.results()
```

Adding requests to a batch that has been sent raises `BatchInProgressException`.
`defer()` sends the batch on a background thread and returns immediately;
`wait()` blocks for the results.

```python
batch = Http.batch(...).then(handle).defer()
batch.wait(timeout=5)
```

## Macros

Register reusable request configurations, then call them off the façade:

```python
Http.macro("github", lambda: Http.with_headers({"X-Example": "example"}).base_url("https://github.com"))

Http.github().get("/repos")
```

Macros may take arguments (`Http.macro("service", lambda name: ...)`) and are
cleared with `Http.flush_macros()`.

## Events

Every request dispatches through the application event dispatcher:

```python
from almasix.client import ConnectionFailed, RequestSending, ResponseReceived
from almasix.events import Event

Event.listen(RequestSending, lambda event: log(event.request.url))
Event.listen(ResponseReceived, lambda event: log(event.response.status()))
Event.listen(ConnectionFailed, lambda event: log(event.exception))
```

`RequestSending` fires before dispatch (faked requests included),
`ResponseReceived` once a response exists, and `ConnectionFailed` when no
response could be obtained.

## Async (ASGI-friendly)

```python
await Http.aget(url)
await Http.apost(url, {"ok": True})
await Http.with_token("x").apatch(url, {"n": 1})
```

Verbs: `aget`, `ahead`, `apost`, `aput`, `apatch`, `adelete`, `aoptions`.
Under the hood this is `httpx.AsyncClient`.

## Testing with fakes

Never hit the network in tests:

```python
from almasix.client import Http

Http.fake()
Http.get("https://example.test")          # empty 200, nothing leaves the process

Http.fake({
    "github.com/*": Http.response({"ok": True}, 201),
    "https://api.example.test/fail": Http.response(None, 500),
})

Http.fake(lambda request: Http.response({"url": request.url}))
Http.fake(Http.response({"same": "for every request"}))
Http.fake({"api.example.test/*": Http.failed_connection()})
Http.fake({"api.example.test/*": Http.failed_request({"code": "not_found"}, 404)})
```

A stub may be a `Response`, a callable taking the `RecordedRequest`, a bare
status code, a JSON-able body, or an exception instance to raise.
`Http.failed_connection()` and `Http.failed_request()` build those exceptions.

**Requests that match no stub are executed for real**, exactly as in Laravel —
`Http.fake()` with no arguments (or a `"*"` key) is what fakes everything. To
make un-faked requests fail instead of escaping to the network:

```python
Http.prevent_stray_requests()
Http.get("https://not-faked.test")            # StrayRequestException

Http.allow_stray_requests(["http://127.0.0.1:5000/*"])   # exempt some patterns
Http.allow_stray_requests()                   # allow all again
```

### Sequences

```python
Http.fake_sequence().push({"id": 1}).push_status(500).when_empty(Http.response({"done": True}))
Http.get(url)  # first
Http.get(url)  # 500
Http.get(url)  # when_empty handler
```

Use `Http.sequence()` to attach a sequence to one URL inside a `fake()` map:

```python
Http.fake({
    "github.com/*": Http.sequence().push("Hello World").push({"foo": "bar"}).push_status(404),
})
```

A drained sequence raises `OutOfFakeResponses`. Opt out with `when_empty(...)`
for a fallback response, or `dont_fail_when_empty()` for an empty 200. Assert
that every queued response was consumed with `Http.assert_sequences_are_empty()`.

### Assertions

```python
Http.assert_sent("https://api.example.test/*")
Http.assert_sent(lambda req: req.method == "POST" and req["name"] == "Ada")
Http.assert_sent(lambda req, resp: req.has_header("X-First", "foo") and resp.ok())
Http.assert_not_sent("https://evil.test/*")
Http.assert_sent_count(2)
Http.assert_sent_in_order(["https://a.test/*", "https://b.test/*"])
Http.assert_nothing_sent()
Http.assert_sequences_are_empty()
```

`Http.recorded()` returns `(RecordedRequest, Response)` pairs, and its filter
callback takes the same one or two arguments as the assertions:

```python
for request, response in Http.recorded():
    ...

Http.recorded(lambda request, response: response.successful())
```

Only requests that produced a response are recorded, so a `ConnectionException`
leaves nothing behind (its `ConnectionFailed` event still fires).

`RecordedRequest` exposes `method`, `url`, `headers`, `data`, `body`, `files`,
`query()`, `header()`, `has_header(key, value=None)`, `is_json()`, `is_form()`,
`is_multipart()`, `has_file(name=None)`, and dict-style access into JSON/form
`data`. Unlike Laravel these are attributes rather than accessor methods where
Python makes that natural (`request.url`, not `request.url()`).

Reset fakes between tests:

```python
from almasix.client import set_factory

@pytest.fixture(autouse=True)
def _reset_http():
    set_factory(None)
    yield
    set_factory(None)
```

## Live requests (httpx)

When you are **not** faking, requests go through httpx. Inject a transport in
tests without DNS:

```python
import httpx

def handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"ok": True})

Http.with_options({"transport": httpx.MockTransport(handler)}).get("https://example.test")
```

## Customizing every request

```python
Http.global_request_middleware(lambda req: req)
Http.global_response_middleware(lambda resp: resp)
Http.with_headers({"X-App": "almasix"}).get(url)   # per request

Http.global_options({"follow_redirects": False})

from almasix.client import get_factory
get_factory().with_headers({"X-App": "almasix"})
get_factory().base_url("https://api.example.test")
```

`before_sending` inspects the `RecordedRequest` immediately before dispatch.

## Dump / dd

```python
Http.dump().get(url)    # prints pending options, still sends
Http.dd().get(url)      # dump and die (raises DumpAndDie)
```
