---
title: Broadcasting
description: Send server-side events to the browser over websockets — channels, authorization, presence, model broadcasting, and the drivers that carry them.
---

## Introduction

An event happens on the server and a browser needs to know about it: a post is
published, an order ships, someone joins a room. Broadcasting takes an event
you already dispatch and puts it on a channel that connected clients are
listening to.

```python
from almasix.broadcasting import PrivateChannel, ShouldBroadcast


class OrderShipped(ShouldBroadcast):
    def __init__(self, order):
        self.order = order

    def broadcast_on(self):
        return [PrivateChannel(f"orders.{self.order.id}")]
```

```python
from almasix.broadcasting import broadcast

broadcast(OrderShipped(order)).to_others()
```

That is the whole contract: an event that inherits `ShouldBroadcast` and names
its channels. Dispatching it — with `broadcast()`, `Event.dispatch()`, or the
`event()` helper — puts the broadcast on the queue and runs your listeners as
usual.

## File map

| Piece | Path |
| --- | --- |
| Façade | `src/almasix/broadcasting/facade.py` — `Broadcast` |
| Manager | `src/almasix/broadcasting/manager.py` — `BroadcastManager` |
| Channels | `src/almasix/broadcasting/channels.py` |
| Event contracts | `src/almasix/broadcasting/events.py` — `ShouldBroadcast`, mixins |
| Drivers | `src/almasix/broadcasting/broadcasters/` — log, null, websocket, redis, pusher |
| Socket server | `src/almasix/broadcasting/sockets.py`, `endpoints.py` |
| Queued broadcast | `src/almasix/broadcasting/jobs.py` — `BroadcastEvent` |
| Model broadcasting | `src/almasix/broadcasting/model.py` — `BroadcastsEvents` |
| Signing | `src/almasix/broadcasting/signing.py` |
| Testing | `src/almasix/broadcasting/testing.py` — `FakeBroadcaster` |
| Provider | `src/almasix/broadcasting/provider.py` |
| Config | `config/broadcasting.py` |
| Channels file | `routes/channels.py` |

## Configuration

`config/broadcasting.py` names the connections, and `BROADCAST_CONNECTION`
picks the one in use. A new application defaults to `log`, which writes each
broadcast to the log and sends nothing — the application is broadcastable
before you have decided how the browser hears about it.

| Driver | What it does |
| --- | --- |
| `log` | Writes the event, the channels, and the payload to the log |
| `null` | Accepts and discards — the off switch |
| `websocket` | Almasix's own socket server, in the application process |
| `redis` | Publishes to Redis for a socket server to relay |
| `pusher` | Posts to Pusher Channels over its REST API |

`Broadcast.extend("mine", resolver)` registers a driver of your own; the
resolver is called with the connection name and its configuration and returns
a `Broadcaster`.

## Defining broadcast events

Inherit `ShouldBroadcast` and name the channels. Everything else has a
default:

```python
class PostPublished(ShouldBroadcast):
    def __init__(self, post):
        self.post = post

    def broadcast_on(self):
        return [Channel("announcements"), PrivateChannel(self.post.author)]

    def broadcast_as(self):        # default: the class name
        return "post.published"

    def broadcast_with(self):      # default: the public attributes
        return {"id": self.post.id, "title": self.post.title}

    def broadcast_when(self):      # default: always
        return self.post.published
```

Without `broadcast_with()`, the payload is every public attribute of the
event, models serialized with `to_dict()`, plus `socket`. Without
`broadcast_as()`, the name is the class name — Python module paths are not
what a JavaScript file wants to type.

### Queued, immediate, and after-commit

`ShouldBroadcast` events go through the queue, on `broadcast_queue` and
`broadcast_connection` if the event names them. Two variants change when:

| Marker | When it goes out |
| --- | --- |
| `ShouldBroadcast` | Queued, as a `BroadcastEvent` job |
| `ShouldBroadcastNow` | During dispatch, no queue involved |
| `ShouldBroadcastAfterCommit` | Queued, but not until the transaction commits |

A queued broadcast captures its channels and payload at dispatch time, so
what sits on the queue is plain JSON that any driver can carry.

### Choosing connections at runtime

Mix in `InteractsWithBroadcasting` and the event can pick:

```python
broadcast(OrderShipped(order)).via("pusher")
```

### Leaving the current user out

Mix in `InteractsWithSockets`. Echo sends an `X-Socket-ID` header once it has
connected, and `to_others()` reads it:

```python
broadcast(OrderShipped(order)).to_others()   # everyone on the channel but me
```

## Channels

| Class | Prefix | Who may listen |
| --- | --- | --- |
| `Channel` | — | Anyone connected |
| `PrivateChannel` | `private-` | Whoever your callback allows |
| `PresenceChannel` | `presence-` | Same, and members see each other |
| `EncryptedPrivateChannel` | `private-encrypted-` | Same, payload sealed with the app key |

A channel can be named after a model, which is what makes model broadcasting
read well: `PrivateChannel(post)` is `private-app.models.post.Post.1`, and a
model may override `broadcast_channel()` to shorten that.

### Authorizing channels

`routes/channels.py` says who may listen to what. The broadcasting provider
loads it, so channels exist in console runs too:

```python
from almasix.broadcasting import Broadcast


@Broadcast.channel("orders.{order}")
def order_channel(user, order: Order):
    return order.user_id == user.get_key()
```

Annotate a parameter with a model and Almasix looks the row up before calling
you — the same binding a route gets. A record that does not exist refuses the
subscription rather than raising.

A channel class is the other spelling, resolved from the container:

```python
Broadcast.channel("orders.{order}", OrderChannel)   # smith make:channel OrderChannel
```

Return `True` to allow, anything falsey to refuse, and — on a presence
channel — a dict, which becomes the member information everyone else sees. A
pattern nobody registered is refused: silence is not consent.

`Broadcast.channel(..., guards=["web", "api"])` picks which guards may
authenticate the request; the default is whatever `request.user()` returns.

Run `smith channel:list` to see what is registered.

## The authorization endpoints

The provider adds these, unless `broadcasting.routes` is `False`:

| Route | What it is for |
| --- | --- |
| `POST /broadcasting/auth` | May this socket join this channel? |
| `POST /broadcasting/user-auth` | Who is this socket? |

Both answer in Pusher's format — an `auth` string of `key:signature`, plus
`channel_data` for presence — so one endpoint serves Almasix's socket server
and a hosted one alike. The signature is HMAC-SHA256 over
`socket_id:channel[:channel_data]`, signed with the connection's `secret`,
falling back to `APP_KEY`.

`broadcasting.middleware` decides what runs in front of them; the default is
`["web"]`, because that is where sessions live.

## Almasix's own socket server

With the `websocket` driver the application serves its own socket at
`/broadcasting/socket` — no third party, no separate process.

```python
Route.websocket("/live", MyHandler())     # your own sockets, same router
```

The protocol is small and Pusher-shaped:

| Direction | Frame |
| --- | --- |
| server → client | `almasix:connection_established` with the `socket_id` |
| client → server | `subscribe` with `channel`, plus `auth` when private |
| server → client | `almasix:subscription_succeeded`, with `members` on presence |
| client → server | `unsubscribe`, `ping` |
| server → client | `almasix:member_added`, `almasix:member_removed`, `almasix:pong` |
| server → client | the broadcast itself: `{event, channel, data}` |

```js
const socket = new WebSocket("ws://localhost:8000/broadcasting/socket");

socket.onmessage = (message) => {
    const frame = JSON.parse(message.data);

    if (frame.event === "almasix:connection_established") {
        socketId = frame.data.socket_id;
        socket.send(JSON.stringify({
            event: "subscribe",
            data: { channel: "announcements" },
        }));
    }
};
```

A client may also send `client-*` events, which are forwarded to the rest of
a private channel it has joined. They are off unless the connection's
`client_events` is true — one browser sending data to every other one is
worth opting into.

One process serves its own connections. More than one worker means each
worker only reaches the browsers attached to it; put Redis in front, or point
`BROADCAST_CONNECTION` at `pusher`, when you scale past one.

## Model broadcasting

Mix `BroadcastsEvents` into a model, before `Model`, and its writes broadcast
themselves:

```python
class Post(BroadcastsEvents, Model):
    def broadcast_on(self, event: str):
        return [] if event == "deleted" else [self, self.author]
```

`broadcast_on()` is asked for `created`, `updated`, `trashed`, `restored`, and
`deleted`; returning `[]` keeps that one quiet. Returning the model means its
own private channel.

The event is named for the model and the change — `PostUpdated` — and carries
`{"model": ...}`, unless the model defines `broadcast_as(event)` or
`broadcast_with(event)`. Set `broadcasts_now = True` to skip the queue, or
inherit `BroadcastsEventsAfterCommit` to wait for the transaction.

## Broadcast notifications

`broadcast` is a notification channel like any other:

```python
class InvoicePaid(Notification):
    def via(self, notifiable):
        return ["database", "broadcast"]

    def to_broadcast(self, notifiable):
        return {"invoice": self.invoice.id, "amount": self.invoice.total}
```

It goes to the notifiable's own private channel — or wherever
`route_notification_for_broadcast()` says — as
`BroadcastNotificationCreated`, with the notification's id and type included.

## Testing

`Broadcast.fake()` points every connection at a recorder:

```python
fake = Broadcast.fake()

broadcast(OrderShipped(order)).send()
await flush_broadcasts()

fake.assert_broadcast("OrderShipped")
fake.assert_broadcast_on("OrderShipped", "private-orders.1")
fake.assert_broadcast_count(1)
fake.assert_not_broadcast("OrderCancelled")
```

Dispatch hands a broadcast to the event loop and returns, so a test that is
about to assert should `await flush_broadcasts()` first. `Event.fake()` still
swallows the whole event, broadcast included.

## Differences from Laravel

- **Marker, not interface.** `ShouldBroadcast` is a base class you inherit;
  Python has no interfaces to implement.
- **Its own socket server.** Laravel points you at Reverb, Pusher, or Ably.
  Almasix ships a websocket driver that runs inside the application, and
  speaks a Pusher-shaped protocol so the alternatives stay available.
- **Names default to the class name**, not the fully qualified path.
- **Payloads are captured at dispatch**, not rebuilt when the job runs,
  because queue payloads here are JSON rather than serialized objects.
- **`flush_broadcasts()`** exists because dispatch is synchronous and the
  send is not; Laravel has no equivalent because PHP has no event loop.
