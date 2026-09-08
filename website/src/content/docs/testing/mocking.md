---
title: Mocking
description: Fakes for mail, queues, notifications, storage, events, the HTTP client, processes, broadcasting, and search — plus a clock a test can move.
---

## Introduction

A test should not send mail, run a job, or call someone else's API. Every
façade that reaches outside the process can be faked, and a fake records what
would have happened so the test can assert on it.

```python
from almasix.testing import fake


async def test_signing_up_sends_a_welcome() -> None:
    mail = fake("mail")

    await client.post("/register", {"email": "ada@example.com"})

    mail.assert_sent(WelcomeMail)
```

`fake(name)` installs one; `fakeable()` lists them; `restore_fakes()` puts
everything back. In a `TestCase`, `self.fake("mail", "queue")` installs several
at once and returns them by name.

| Name | Fakes | Assertions |
| --- | --- | --- |
| `mail` | The mailer | `assert_sent`, `assert_not_sent`, `assert_queued`, `assert_nothing_sent` |
| `queue` | The job dispatcher | `assert_pushed`, `assert_pushed_on`, `assert_pushed_times`, `assert_nothing_pushed` |
| `notification` | The notification sender | `assert_sent_to`, `assert_sent_on_channel`, `assert_sent_times`, `assert_nothing_sent` |
| `storage` | The default disk | `assert_exists`, `assert_missing`, `assert_count`, `assert_has` |
| `event` | The event dispatcher | `assert_dispatched`, `assert_not_dispatched` |
| `http` | The HTTP client | `assert_sent`, `assert_sent_count`, `assert_nothing_sent` |
| `process` | The process runner | `assert_ran`, `assert_ran_times`, `assert_nothing_ran` |
| `broadcast` | The broadcaster | `assert_broadcast`, `assert_nothing_broadcast` |
| `scout` | The search engine | `assert_indexed`, `assert_removed`, `written` |

A fake installed by hand is put back by hand. The scaffolded `tests/conftest.py`
calls `restore_fakes()` after every test, so nothing outlives the test that
faked it.

## Queues

```python
queue = fake("queue")

await dispatch(SendDigest())

queue.assert_pushed(SendDigest)
queue.assert_pushed(SendDigest, lambda job: job.queue == "digests")
queue.assert_pushed_on("digests", SendDigest)
queue.assert_pushed_times(SendDigest, 1)
queue.assert_not_pushed(ChargeCard)
queue.assert_nothing_pushed()
assert queue.recorded(SendDigest)[0].queued is True
```

`fake_queue([SendDigest])` fakes only the jobs it names, and lets everything
else run — useful when one job in a flow is slow and the rest are the point.

## Notifications

```python
notifications = fake("notification")

await notify(user, ShipmentArrived())

notifications.assert_sent_to(user, ShipmentArrived)
notifications.assert_sent_on_channel(ShipmentArrived, "mail")
notifications.assert_sent_times(ShipmentArrived, 1)
notifications.assert_not_sent_to(other, ShipmentArrived)
notifications.assert_nothing_sent()
```

A callback may take the notification, or the notification and the notifiable:

```python
notifications.assert_sent_to(user, ShipmentArrived, lambda n, to: to.get_key() == 1)
```

Notifiables are matched by key when they have one, so an equal model counts as
the same recipient.

## Storage

```python
disk = fake("storage")

await client.post("/avatars", files={"file": ("me.png", b"...")})

disk.assert_exists("avatars/me.png")
disk.assert_has("avatars/me.png", b"...")
disk.assert_missing("avatars/other.png")
disk.assert_count("avatars", 1)
disk.assert_directory_empty("trash")
```

The fake disk keeps files in memory, so nothing is written and nothing has to
be cleaned up.

## Mail, events, HTTP, processes, broadcasting, search

Each of these has a fake of its own, documented with the feature it belongs to:
[Mail](/mail/), [Events](/events/), [HTTP Client](/http-client/),
[Processes](/processes/), [Broadcasting](/broadcasting/), and
[Search](/search/). `fake(name)` is the same object those pages describe —
one door, so a test does not have to remember nine different ways in.

## Time

A test that depends on the clock can move it:

```python
from almasix.testing import freeze_time, frozen_time, travel, travel_back, travel_to

travel(days=2)                                  # forward two days
travel(hours=-1)                                # or back an hour
travel_to(datetime(2030, 1, 1, tzinfo=timezone.utc))
freeze_time()                                   # hold it still, here
travel_back()                                   # and let it run again

with frozen_time(datetime(2030, 1, 1, tzinfo=timezone.utc)):
    post = await Post.create({"title": "New year"})
    # created_at is 2030-01-01
```

`now()`, `today()`, and the timestamps a model writes all read the moved clock.
The context manager form puts the clock back on the way out, including when the
test fails; the plain calls return a traveller whose `.back()` does the same.

## Plain Python mocks

None of this replaces `unittest.mock`. A collaborator of your own is best
mocked the ordinary way:

```python
from unittest.mock import AsyncMock

async def test_the_report_asks_the_ledger(monkeypatch) -> None:
    ledger = AsyncMock(return_value=[{"total": 10}])
    monkeypatch.setattr("app.reports.ledger.rows", ledger)

    await build_report()

    ledger.assert_awaited_once()
```

The fakes exist for the framework's own façades, where a test cannot easily
reach in and swap the thing underneath.
