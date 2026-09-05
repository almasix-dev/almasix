---
title: Events
description: Event.listen / dispatch / subscribe — application events and queued listeners.
---

## Introduction

Avalon’s application event bus lives in `avalon.events`. It is separate from
Articulate **model** events (`creating`, `saved`, …). Use it to decouple
domain actions from side effects.

```python
from avalon.events import Event, event, listen

class OrderShipped:
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id

def send_receipt(event: OrderShipped) -> None:
    ...

Event.listen(OrderShipped, send_receipt)
Event.dispatch(OrderShipped(42))
# or: event(OrderShipped(42))
```

## Registering listeners

Register in a provider `boot()` method, or subclass `EventServiceProvider` and
fill the `listen` map:

```python
from avalon.events import Event, EventServiceProvider

class AppEventServiceProvider(EventServiceProvider):
    listen = {
        OrderShipped: [SendShipmentNotification],
    }
```

Closure listeners and class listeners (with a `handle` method) are both supported.
String class paths resolve via import.

### Wildcards

```python
Event.listen("orders.*", lambda name, payload: ...)
```

Wildcard listeners receive `(event_name, payload)`.

### Subscribers

```python
class OrderSubscriber:
    def subscribe(self, events) -> None:
        events.listen(OrderShipped, self.on_shipped)

    def on_shipped(self, event: OrderShipped) -> None:
        ...

Event.subscribe(OrderSubscriber)
```

## Dispatching

```python
Event.dispatch(OrderShipped(1))
Event.until("ping")          # halt on first non-None response
event(OrderShipped(1))       # helper
```

Return `False` from a listener to stop propagation.

## Queued listeners

Implement `ShouldQueue` (from `avalon.events` / `avalon.queue`) on a listener
class. When the event fires, Avalon pushes a `CallQueuedListener` job:

```python
from avalon.events import ShouldQueue

class SendShipmentNotification(ShouldQueue):
    queue = "listeners"
    delay = 0

    def handle(self, event: OrderShipped) -> None:
        ...
```

Optional `should_queue(event) -> bool`, `via_connection()`, `via_queue()`, and
`with_delay(event)` mirror the Laravel surface.

## Generating stubs

```bash
grail make:event OrderShipped
grail make:listener SendShipmentNotification --event=OrderShipped --queued
grail event:list
```

## Broadcasting (M26)

`ShouldBroadcast` is a marker protocol today. Annotate events early; channel
broadcasting ships with M26.

## Testing

```python
Event.fake()
Event.dispatch(OrderShipped(1))
Event.assert_dispatched(OrderShipped)
Event.assert_not_dispatched(OtherEvent)
Event.assert_nothing_dispatched()  # after a fresh fake()
```
