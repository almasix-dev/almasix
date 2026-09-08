---
title: Task Scheduling
description: Define scheduled tasks in code — frequencies, constraints, hooks, output, sub-minute tasks, and the commands that run them.
---

## Introduction

In the past you may have written a cron entry for each task you needed to run
on a schedule. That gets painful quickly: the schedule is not in source
control, and you have to SSH into the server to see what is there.

Almasix's scheduler lets you define the whole schedule inside the application,
in code, and needs a single cron entry on the server. Tasks are usually
defined in `routes/console.py`.

```python
# routes/console.py
from almasix.console import schedule
from almasix.orm import DB


async def clear_recent_users() -> None:
    await DB.table("recent_users").delete()


schedule.call(clear_recent_users).daily()
```

**Deviation, in Almasix's favour:** a scheduled callback may be `async`, and the
scheduler awaits it. Laravel has nothing to do here, but Almasix's ORM, queue,
and HTTP client are awaitable, so a callback that could not await them would be
useless for most of what people schedule.

Then one cron entry runs the whole schedule:

```
* * * * * cd /path/to/app && smith schedule:run >> /dev/null 2>&1
```

## Defining schedules

`schedule.call()` takes any callable, and names the task after the function
unless you say otherwise:

```python
schedule.call(clear_recent_users).daily()
schedule.call(warm_cache, description="warm the cache").hourly()
```

If you would rather keep `routes/console.py` for command definitions only,
define the schedule in `bootstrap/app.py` instead — the callback is handed the
schedule as it is registered:

```python
# bootstrap/app.py
application = (
    Application.configure(BASE_PATH)
    .with_middleware(configure_middleware)
    .with_schedule(lambda schedule: schedule.call(clear_recent_users).daily())
    .create()
)
```

A task is listed under what it runs — the command line, the shell line, or the
callback's name. `name()` changes the identity its locks are keyed on, and
`purpose()` changes the description that appears beside it:

```python
schedule.call(clear_recent_users).name("clear-recent-users").purpose(
    "Clear the recent users table"
).daily()
```

To see what is scheduled and when each task next runs, use `schedule:list`:

```bash
smith schedule:list
```

```
  * * * * *  heartbeat            next: 2026-09-08 07:38:00
  0 2 * * *  mail:digest          next: 2026-09-09 02:00:00
  every 10 seconds  metrics:push  next: 2026-09-08 07:37:20
```

### Scheduling Smith commands

`schedule.command()` schedules a [Smith command](/console/) by name. Arguments
and options can be part of the string, or a list:

```python
schedule.command("emails:send taylor --force").daily()
schedule.command("emails:send", ["taylor", "--force"]).daily()
```

**Named deviation:** Laravel also accepts a command *class* here. Almasix
schedules by name, because that is the identity Smith resolves and the string
is what appears in `schedule:list`.

#### Scheduling closure commands

A command defined as a closure schedules itself. Chain `schedule()` onto the
definition, passing any arguments the closure needs:

```python
# routes/console.py
from almasix.console import Artisan

Artisan.command("delete:recent-users", clear_recent_users).purpose(
    "Delete recent users"
).schedule().daily()

Artisan.command("emails:send {user} {--force}", send_emails).purpose(
    "Send emails to the given user"
).schedule(["taylor", "--force"]).daily()
```

### Scheduling queued jobs

`schedule.job()` schedules a [queued job](/queues/) without wrapping it in a
callback:

```python
from app.jobs.heartbeat import Heartbeat

schedule.job(Heartbeat()).every_five_minutes()
```

The second and third arguments choose the queue and the connection:

```python
# Dispatch to the "heartbeats" queue on the "redis" connection...
schedule.job(Heartbeat(), "heartbeats", "redis").every_five_minutes()
```

### Scheduling shell commands

`schedule.exec()` hands a command to the operating system:

```python
schedule.exec("node /home/forge/script.js").daily()
```

The task's exit code is the shell's, and everything it wrote is available to
the [output](#task-output) and [hook](#task-hooks) methods.

### Schedule frequency options

Every task starts out running every minute. These methods change that:

| Method | Description |
| --- | --- |
| `.cron("* * * * *")` | Run on a custom cron schedule. |
| `.every_second()` | Run every second. |
| `.every_two_seconds()` | Run every two seconds. |
| `.every_five_seconds()` | Run every five seconds. |
| `.every_ten_seconds()` | Run every ten seconds. |
| `.every_fifteen_seconds()` | Run every fifteen seconds. |
| `.every_twenty_seconds()` | Run every twenty seconds. |
| `.every_thirty_seconds()` | Run every thirty seconds. |
| `.every_minute()` | Run every minute. |
| `.every_two_minutes()` | Run every two minutes. |
| `.every_three_minutes()` | Run every three minutes. |
| `.every_four_minutes()` | Run every four minutes. |
| `.every_five_minutes()` | Run every five minutes. |
| `.every_ten_minutes()` | Run every ten minutes. |
| `.every_fifteen_minutes()` | Run every fifteen minutes. |
| `.every_thirty_minutes()` | Run every thirty minutes. |
| `.hourly()` | Run every hour. |
| `.hourly_at(17)` | Run every hour at 17 minutes past. |
| `.every_odd_hour(minutes=0)` | Run every odd hour. |
| `.every_two_hours(minutes=0)` | Run every two hours. |
| `.every_three_hours(minutes=0)` | Run every three hours. |
| `.every_four_hours(minutes=0)` | Run every four hours. |
| `.every_six_hours(minutes=0)` | Run every six hours. |
| `.daily()` | Run every day at midnight. |
| `.daily_at("13:00")` | Run every day at 13:00. |
| `.twice_daily(1, 13)` | Run daily at 1:00 and 13:00. |
| `.twice_daily_at(1, 13, 15)` | Run daily at 1:15 and 13:15. |
| `.days_of_month([1, 10, 20])` | Run on the given days of the month. |
| `.weekly()` | Run every Sunday at 00:00. |
| `.weekly_on(1, "8:00")` | Run weekly on Monday at 8:00. |
| `.monthly()` | Run on the first of the month at 00:00. |
| `.monthly_on(4, "15:00")` | Run monthly on the 4th at 15:00. |
| `.twice_monthly(1, 16, "13:00")` | Run monthly on the 1st and 16th at 13:00. |
| `.last_day_of_month("15:00")` | Run on the month's last day at 15:00. |
| `.quarterly()` | Run on the first day of each quarter at 00:00. |
| `.quarterly_on(4, "14:00")` | Run each quarter on the 4th at 14:00. |
| `.yearly()` | Run on the first day of the year at 00:00. |
| `.yearly_on(6, 1, "17:00")` | Run yearly on June 1st at 17:00. |
| `.at("13:00")` | Another spelling of `.daily_at()`, for reading order. |
| `.timezone("America/New_York")` | Read this task's times in a timezone. |

Laravel's camelCase spelling works for every one of them, so
`.everyFiveMinutes()` and `.dailyAt("13:00")` are the same calls as
`.every_five_minutes()` and `.daily_at("13:00")`. Pick one per project and
stay with it; the snake_case names are the documented ones.

Frequencies **write cron fields** rather than replacing the whole expression,
which is what lets them combine:

```python
# Once a week, on Monday at 13:00...
schedule.call(clear_recent_users).weekly().mondays().at("13:00")

# Hourly from 8am to 5pm on weekdays, in Chicago time...
schedule.command("foo").weekdays().hourly().timezone("America/Chicago").between(
    "8:00", "17:00"
)
```

The same rule has a sharp edge: `.cron()` writes all five fields, so it
discards a day constraint set before it. Put `.cron()` first.

```python
schedule.command("foo").cron("*/5 * * * *").weekdays()  # every five minutes, Mon–Fri
schedule.command("foo").weekdays().cron("*/5 * * * *")  # the weekday limit is gone
```

These are the additional constraints:

| Method | Description |
| --- | --- |
| `.weekdays()` | Limit the task to weekdays. |
| `.weekends()` | Limit the task to weekends. |
| `.sundays()`, `.mondays()`, `.tuesdays()`, `.wednesdays()`, `.thursdays()`, `.fridays()`, `.saturdays()` | Limit the task to one named day. |
| `.days([0, 3])` | Limit the task to the given days. |
| `.between("8:00", "17:00")` | Limit the task to a window in the day. |
| `.unless_between("23:00", "4:00")` | Keep the task out of a window. |
| `.when(callback)` | Limit the task to a truth test. |
| `.skip(callback)` | Skip the task on a truth test. |
| `.environments(["staging", "production"])` | Limit the task to environments. |

#### Day constraints

`days()` limits a task to days of the week, given as numbers where Sunday is
`0`:

```python
schedule.command("emails:send").hourly().days([0, 3])
```

The constants on `Schedule` say the same thing with names:

```python
from almasix.console import Schedule

schedule.command("emails:send").hourly().days([Schedule.SUNDAY, Schedule.WEDNESDAY])
```

Cron's own day rule applies when you write an expression yourself: with **both**
a day-of-month and a day-of-week restricted, a task runs when *either* matches.
So `cron("0 0 1 * mon")` means "the first of the month, and every Monday".

#### Between time constraints

`between()` limits a task to a window in the day, and `unless_between()`
excludes one. Both ends are inclusive, and a window that ends before it starts
is read as crossing midnight:

```python
schedule.command("emails:send").hourly().between("7:00", "22:00")
schedule.command("emails:send").hourly().unless_between("23:00", "4:00")
```

#### Truth test constraints

`when()` runs the task only if the callback returns true, and `skip()` is its
inverse. Chained `when()` calls must all pass:

```python
schedule.command("emails:send").daily().when(lambda: Cache.get("digest:enabled"))
schedule.command("emails:send").daily().skip(lambda: date.today().day == 1)
```

A plain boolean is accepted where a callback is expected, for the cases where
the answer is known when the schedule is defined:

```python
schedule.command("emails:send").daily().when(config("mail.digest_enabled"))
```

#### Environment constraints

`environments()` limits a task to the environments named in `APP_ENV`:

```python
schedule.command("emails:send").daily().environments(["staging", "production"])
```

### Timezones

`timezone()` says which timezone a task's times are written in:

```python
schedule.command("report:generate").timezone("America/New_York").at("2:00")
```

The name is anything `zoneinfo` accepts. A task with no timezone is read
against the server's local time, which is what `schedule:run` uses.

:::caution
Some timezones use daylight saving. When the clocks change, a task scheduled
inside the shifted hour may run twice or not at all. Prefer UTC for tasks where
that matters.
:::

### Preventing task overlaps

Scheduled tasks run even if the previous run has not finished. `without_overlapping()`
stops that:

```python
schedule.command("emails:send").without_overlapping()
```

The lock is held for a day unless you say otherwise. Pass minutes to shorten
it, which bounds how long a crashed run can keep other runs out:

```python
schedule.command("emails:send").without_overlapping(10)
```

Locks come from the [cache](/cache/) when the cache manager is booted, keyed
`schedule:{name}`. Without a cache — a bare `smith schedule:run` in a fresh
app — the scheduler falls back to a file lock under
`storage/framework/schedule/`. If a task gets stuck and leaves its lock
behind, release it:

```bash
smith schedule:clear-cache
```

### Running tasks on one server

:::caution
This needs a cache store every server shares — `redis`, `database`, or
`memcached`. The `array` and `file` stores are per-process and per-machine, so
every server would claim the task.
:::

When the scheduler runs on several servers, `on_one_server()` gives the task to
whichever server claims it first:

```python
schedule.command("report:generate").fridays().at("17:00").on_one_server()
```

`use_cache()` chooses the store those claims are taken from:

```python
schedule.use_cache("redis")
```

#### Naming single server tasks

A command names itself, but a closure or a job does not — and two servers would
take two different locks. Name them, and Almasix raises a `RuntimeError` if you
forget:

```python
schedule.job(CheckUptime("https://almasix.dev")).name(
    "check_uptime:almasix.dev"
).every_five_minutes().on_one_server()

schedule.call(reset_api_counts).name("reset-api-counts").daily().on_one_server()
```

### Background tasks

Tasks due at the same minute run one after another, in the order they were
defined. `run_in_background()` runs a task alongside the others instead of
making them wait:

```python
schedule.command("analytics:report").daily().run_in_background()
```

**Named deviation:** Laravel detaches an OS process and reports back through
`schedule:finish`. Almasix runs the task in a worker thread, so the tasks still
run simultaneously, but `schedule:run` waits for them before it exits — a
thread cannot outlive the interpreter that started it. A task that must
survive the tick belongs on a [queue](/queues/).

### Maintenance mode

Scheduled tasks do not run while the application is down for maintenance, so
they cannot interfere with whatever you are doing to the server:

```bash
smith down    # tasks stop
smith up      # tasks resume
```

`even_in_maintenance_mode()` exempts a task:

```python
schedule.command("emails:send").even_in_maintenance_mode()
```

**Not shipped yet:** maintenance mode today is only the scheduler's side of
Laravel's feature — a marker file at `storage/framework/down` that `smith down`
writes and `smith up` removes. HTTP requests are still served normally; the
503 response, the secret bypass URL, `--render`, and `--retry` are owed by
their own milestone.

### Schedule groups

Tasks that share settings can be defined together. Call the shared methods on
the schedule itself, then `group()` with a callback that defines the tasks:

```python
def digest_tasks() -> None:
    schedule.command("emails:send --force")
    schedule.command("emails:prune")


schedule.daily().on_one_server().timezone("America/New_York").group(digest_tasks)
```

Every task defined inside the callback gets the held attributes. Groups nest,
and since frequencies write cron fields, an inner frequency lands on top of
the outer one rather than replacing it.

## Running the scheduler

`schedule:run` evaluates the schedule and runs whatever is due:

```bash
smith schedule:run
```

That is the only cron entry you need:

```
* * * * * cd /path/to/app && smith schedule:run >> /dev/null 2>&1
```

The command exits non-zero if any task it ran did. Tasks a constraint turned
away are reported as skipped, and do not count as failures.

To run one task immediately, whatever its frequency says, use `schedule:test`.
With no `--name` it asks which task you meant:

```bash
smith schedule:test
smith schedule:test --name mail:digest
```

### Sub-minute scheduled tasks

Cron cannot go below a minute, but the scheduler can — down to every second:

```python
schedule.call(clear_recent_users).every_second()
```

When any sub-minute task is defined, `schedule:run` keeps running until the end
of the current minute instead of exiting straight away, waking on the seconds
those tasks asked for.

A sub-minute task that takes longer than its interval delays the ones behind
it, so it is best to make the task hand the work off:

```python
schedule.job(DeleteRecentUsers()).every_ten_seconds()
schedule.command("users:delete").every_ten_seconds().run_in_background()
```

#### Interrupting sub-minute tasks

Because `schedule:run` now runs for the whole minute, a deployment can leave an
instance running the previous release's code until the minute is out. Add this
to the end of your deployment script:

```bash
smith schedule:interrupt
```

The running command stops at the end of the current second. The signal is
scoped to the minute it was sent in, so it never stops the following minute's
run.

### Running the scheduler locally

You would not normally add a cron entry on your development machine. Run the
scheduler in the foreground instead:

```bash
smith schedule:work
```

It ticks every minute until you stop it, and stays inside the minute when
sub-minute tasks are defined. `--sleep` changes the gap between ticks.

## Task output

`send_output_to()` writes what a task printed to a file:

```python
schedule.command("emails:send").daily().send_output_to(storage_path("logs/emails.log"))
```

`append_output_to()` adds to the file instead of replacing it:

```python
schedule.command("emails:send").daily().append_output_to(
    storage_path("logs/emails.log")
)
```

`email_output_to()` sends it on. Configure [mail](/mail/) first:

```python
schedule.command("report:generate").daily().send_output_to(path).email_output_to(
    "taylor@example.com"
)
```

`email_output_on_failure()` sends it only when the task exits non-zero:

```python
schedule.command("report:generate").daily().email_output_on_failure(
    "taylor@example.com"
)
```

**Deviation, in Almasix's favour:** Laravel restricts the output methods to
`command` and `exec` tasks. Almasix captures `stdout` and `stderr` around every
task, so `call` and `job` tasks can send their output to a file or an inbox
too.

## Task hooks

`before()` and `after()` run code around the task:

```python
schedule.command("emails:send").daily().before(
    lambda: print("The task is about to run...")
).after(lambda: print("The task has run..."))
```

`then()` is another name for `after()`. `on_success()` and `on_failure()` run
depending on the exit code, where a failure means the task exited non-zero or
raised:

```python
schedule.command("emails:send").daily().on_success(
    lambda: print("It worked")
).on_failure(lambda: print("It did not"))
```

Hooks run in Laravel's order: `before`, the task, `after` / `then`, then
`on_success` or `on_failure`.

A hook that takes a parameter is handed the task's output as a
[`Stringable`](/strings/):

```python
def notify(output) -> None:
    log().error(f"emails:send failed: {output.limit(500)}")


schedule.command("emails:send").daily().on_failure(notify)
```

### Pinging URLs

`ping_before()` and `then_ping()` GET a URL around the task, which is how
external monitors are told a task started or finished:

```python
schedule.command("emails:send").daily().ping_before(url).then_ping(url)
```

`ping_on_success()` and `ping_on_failure()` ping only on that outcome:

```python
schedule.command("emails:send").daily().ping_on_success(success_url).ping_on_failure(
    failure_url
)
```

Each has a conditional form that only registers the ping when the condition
holds — `ping_before_if()`, `then_ping_if()`, `ping_on_success_if()`, and
`ping_on_failure_if()`:

```python
schedule.command("emails:send").daily().ping_before_if(
    config("app.env") == "production", url
)
```

Pings go through the [HTTP client](/http-client/), and a ping that cannot reach
its URL never fails the task.

## Events

The scheduler dispatches these on the [event bus](/events/):

| Event |
| --- |
| `almasix.console.scheduling.ScheduledTaskStarting` |
| `almasix.console.scheduling.ScheduledTaskFinished` |
| `almasix.console.scheduling.ScheduledBackgroundTaskFinished` |
| `almasix.console.scheduling.ScheduledTaskSkipped` |
| `almasix.console.scheduling.ScheduledTaskFailed` |

Each carries the task it is about, and the finished ones carry the exit code
and the captured output:

```python
from almasix.console.scheduling import ScheduledTaskFailed
from almasix.events import Event
from almasix.log import log

Event.listen(
    ScheduledTaskFailed,
    lambda event: log().error(f"{event.task.summary()} exited {event.exit_code}"),
)
```

`ScheduledTaskSkipped` also carries a `reason`, which says whether a
constraint, a lock, another server, or maintenance mode turned the task away.

## Commands

| Command | What it does |
| --- | --- |
| `smith schedule:run` | Run the due tasks — the one cron entry. |
| `smith schedule:work` | Run the scheduler in the foreground. |
| `smith schedule:list` | List the tasks and when each next runs. |
| `smith schedule:test` | Run one task now, whatever its frequency. |
| `smith schedule:interrupt` | Stop an in-progress `schedule:run`. |
| `smith schedule:clear-cache` | Release without-overlapping locks. |
| `smith down` / `smith up` | Stop and resume scheduled tasks. |

## Cron expressions

`cron()` takes the five standard fields — minute, hour, day of month, month,
day of week — and reads `*`, `?`, lists (`1,15`), ranges (`8-17`), steps
(`*/5`, `1-23/2`, `10/5`), month names (`jan`), and day names (`mon`). Sunday
is `0`, and `7` is accepted for it too.

**Named deviation:** the `L`, `W`, and `#` extensions are not implemented.
`last_day_of_month()` covers the common use of `L`, and it asks the calendar
at run time rather than writing a fixed day into the expression when the task
is defined — so it is right in February, and right for a process that runs
across a month boundary.

## Related

- [Smith Console](/console/) — the commands the scheduler runs
- [Queues](/queues/) — for work that should outlive the tick
- [Cache](/cache/) — where overlapping and one-server locks live
- [Mail](/mail/) — for `email_output_to`
- [Events](/events/) — the scheduler's lifecycle events
