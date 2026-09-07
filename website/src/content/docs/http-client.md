---
title: HTTP Client
description: Outbound Http.get/post façade with fakes, retry, pool, and async.
---

## Introduction

Avalon’s HTTP client lives in `avalon.client`. It is the Laravel-shaped
wrapper around **httpx** for *outbound* requests (calling other APIs). Inbound
HTTP stays in `avalon.http`.

```python
from avalon.client import Http

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
| Façade | `src/avalon/client/facade.py` — `Http` |
| Pending request | `src/avalon/client/pending.py` — `PendingRequest` |
| Response | `src/avalon/client/response.py` — `Response` |
| Fakes / recording | `src/avalon/client/factory.py` — `Factory`, `Sequence` |
| Pool | `src/avalon/client/pool.py` |
| Provider | `src/avalon/client/provider.py` — `ClientServiceProvider` |
| Exceptions | `src/avalon/client/exceptions.py` |

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
need form encoding, `with_body()` to send a raw payload, or `body_format()` to
pick one of `json` / `form` / `multipart` / `body` directly — anything else
raises `PendingRequestException`.

### Fluent options

```python
Http.with_headers({"X-Trace": "1"}).get(url)
Http.with_token("secret").get(url)                 # Bearer
Http.with_basic_auth("user", "pass").get(url)
Http.with_query_parameters({"page": 2}).get(url)
Http.base_url("https://api.example.test").get("/users")
Http.timeout(5).connect_timeout(2).get(url)
Http.accept_json().as_json().post(url, {"ok": True})
Http.with_url_parameters({"id": 7}).get("https://api.example.test/users/{id}")
```

`when` / `unless` wrap optional configuration:

```python
Http.when(use_token, lambda http: http.with_token(token)).get(url)
```

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

### Exceptions

| Exception | Raised when |
| --- | --- |
| `RequestException` | a failed response meets a `throw` policy or retries are exhausted |
| `ConnectionException` | httpx could not complete the request (DNS, refused, timeout) |
| `StrayRequestException` | a request has no matching fake and strays are prevented |
| `OutOfFakeResponses` | a `fail_when_empty()` sequence is drained |
| `PendingRequestException` | the pending request is misconfigured (e.g. unknown body format) |

All of them subclass `HttpClientException`.

## Retry

```python
# up to 3 attempts in total; sleep is milliseconds between attempts
Http.retry(3, 100).get(url)

# narrow what counts as retryable, and keep the last response instead of raising
Http.retry(3, 100, when=lambda error: error.server_error(), throw=False).get(url)
```

`times` is the **maximum number of attempts**, not the number of extra ones, so
`retry(3)` sends the request at most three times.

By default every failed response (4xx/5xx) and every `ConnectionException` is
retried. Once the attempts are exhausted a `RequestException` is raised — pass
`throw=False` to get the last failed response back instead. A
`ConnectionException` always propagates when the attempts run out.

The `when` callback receives the failure (either the `Response` or the
exception) and, if it accepts a second argument, the `PendingRequest`.

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

Pool jobs run on a thread pool. Fakes still apply.

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
from avalon.client import Http

Http.fake()
Http.get("https://example.test")          # empty 200

Http.fake({
    "github.com/*": Http.response({"ok": True}, 201),
    "https://api.example.test/fail": Http.response(None, 500),
})

Http.fake(lambda request: Http.response({"url": request.url}))
Http.fake(Http.response({"same": "for every request"}))
Http.fake({"api.example.test/*": ConnectionException("dns failure")})
```

A stub may be a `Response`, a callable taking the `RecordedRequest`, a bare
status code, a JSON-able body, or an exception instance to raise.

Unmatched URLs while faking still return an empty **200**, unless you prevent
strays:

```python
Http.prevent_stray_requests()
Http.get("https://not-faked.test")   # StrayRequestException
Http.allow_stray_requests()
```

### Sequences

```python
Http.fake_sequence().push({"id": 1}).push_status(500).when_empty(Http.response({"done": True}))
Http.get(url)  # first
Http.get(url)  # 500
Http.get(url)  # empty handler
```

`fail_when_empty()` raises `OutOfFakeResponses` when the queue is drained;
`dont_fail_when_empty()` goes back to an empty 200. Assert that every queued
response was consumed with `Http.assert_sequences_are_empty()`.

### Assertions

```python
Http.assert_sent("https://api.example.test/*")
Http.assert_sent(lambda req: req.method == "POST" and req["name"] == "Ada")
Http.assert_not_sent("https://evil.test/*")
Http.assert_sent_count(2)
Http.assert_sent_in_order(["https://a.test/*", "https://b.test/*"])
Http.assert_nothing_sent()
Http.assert_sequences_are_empty()
Http.recorded()                       # list[RecordedRequest]
```

`RecordedRequest` has `method`, `url`, `headers`, `data`, `body`, `query()`,
`header()`, and dict-style access into JSON/form `data`.

Reset fakes between tests:

```python
from avalon.client import set_factory

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
Http.with_headers({"X-App": "avalon"}).get(url)   # per request

from avalon.client import get_factory
get_factory().with_headers({"X-App": "avalon"})
get_factory().base_url("https://api.example.test")
```

`before_sending` inspects the `RecordedRequest` immediately before dispatch.

## Dump / dd

```python
Http.dump().get(url)    # prints pending options, still sends
Http.dd().get(url)      # dump and die (raises DumpAndDie)
```
