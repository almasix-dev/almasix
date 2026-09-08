---
title: Grail Console
description: Grail commands, Command classes, discovery, and the Fiddle REPL.
---

## Grail

Every Avalon application ships **Grail** — the in-app CLI. With your virtualenv active and Avalon installed, run commands as `grail …`. You can also invoke the root `grail` script with `python grail …`.

```bash
grail list
grail make:command SendDigest
grail inspire
grail fiddle
```

`fiddle` is Avalon’s interactive REPL. Familiar aliases work the same way:

```bash
grail fiddle
grail tinker
grail repl
```

Framework commands (`serve`, `migrate`, `make:*`, …) live on the same surface as discovered app `Command` subclasses.

## Writing commands

```python
# app/console/commands/send_digest.py
from avalon.console import Command

class SendDigest(Command):
    signature = "mail:digest {user?} {--queue=default}"
    description = "Send the daily digest"

    def handle(self) -> int:
        user = self.argument("user") or "everyone"
        self.info(f"Queue={self.option('queue')} → {user}")
        return 0
```

Generate a stub with `grail make:command SendDigest`.

### Exit codes

`handle()` may return an `int`, or nothing at all (which means success). Use the constants rather than bare numbers:

```python
def handle(self) -> int:
    if not self.argument("user"):
        return self.INVALID      # 2
    return self.SUCCESS          # 0 — self.FAILURE is 1
```

To stop immediately with a message, call `fail()`. It raises `CommandFailed`, prints the message on stderr, and the command exits with `FAILURE`:

```python
if not queue_is_reachable():
    self.fail("The queue connection is unreachable.")
```

## Closure commands

Commands do not need a class. Define them in `routes/console.py`, the way Laravel defines them in `routes/console.php`:

```python
# routes/console.py
from avalon.console import Artisan

def send(user: str, queue: str) -> int:
    print(f"Sending to {user} on {queue}")
    return 0

Artisan.command("mail:send {user} {--queue=default}", send).purpose("Send a message")
```

Parameters are filled by name from the command's arguments and options. A parameter named `command` receives the `Command` instance itself, and any parameter type-hinted with a class is resolved from the container:

```python
def report(command, reports: ReportService, format: str = "text") -> int:
    command.info(reports.render(format))
    return 0

Artisan.command("report:daily {--format=text}", report)
```

`purpose()` (aliased as `describe()`) sets the description shown by `grail list`. Without it, the callable's first docstring line is used.

## Defining input expectations

### Signature tokens

| Token | Meaning |
| --- | --- |
| `{name}` | Required argument |
| `{name?}` | Optional argument |
| `{name=value}` | Optional with default |
| `{names*}` | Argument array (all remaining values) |
| `{names?*}` | Optional argument array |
| `{names=*a,b}` | Argument array with defaults |
| `{tags...}` | Variadic — Avalon's original spelling of `{tags*}` |
| `{--flag}` | Boolean option |
| `{--queue=}` | Option that accepts a value |
| `{--queue=default}` | Option with a default |
| `{--id=*}` | Option array — repeat the flag to collect values |
| `{--Q\|queue=}` | Option with a `-Q` shortcut |
| `{user : The user ID}` | Any token, with a description |

Descriptions are separated by a colon surrounded by spaces, so defaults containing colons (`{--url=https://…}`) are safe.

```python
signature = "mail:send {user : Who to notify} {--Q|queue=default : Which queue} {--cc=*}"
```

```bash
grail mail:send 7 -Q bulk --cc=a@example.com --cc=b@example.com
```

`--cc` arrives as `["a@example.com", "b@example.com"]`. Everything after a bare `--` is treated as a positional value.

### Prompting for missing input

Mix in `PromptsForMissingInput` and a required argument that was not supplied is asked for instead of erroring:

```python
from avalon.console import Command, PromptsForMissingInput

class SendDigest(PromptsForMissingInput, Command):
    signature = "mail:digest {user}"

    def prompt_for_missing_arguments_using(self) -> dict:
        return {"user": "Which user should receive the digest?"}
```

Values may be callables for full control, and `prompt_for_missing_argument(name)` can be overridden outright. Without a mapping, Avalon asks `What is the user?`. In a non-interactive shell the underlying prompt raises rather than hanging.

## Command I/O

### Retrieving input

`argument(key, default)` and `option(key, default)` read single values; `arguments()` and `options()` return the whole bag; `has_option(key)` checks presence. Every value is also set as an attribute before `handle()` runs, so `self.user` works alongside `self.argument("user")`.

### Writing output

`line`, `info`, `comment`, `question`, `warn`, `error`, `success`, and `alert` write styled output (`error` goes to stderr). `new_line(count)` adds blank lines, and `table(headers, rows)` prints an aligned table.

```python
self.alert("Digest complete")
self.table(["Queue", "Sent"], [["bulk", 128]])
```

### Progress bars

`with_progress_bar()` maps over an iterable while advancing a bar, returning the results:

```python
sent = self.with_progress_bar(users, lambda user: mailer.send(user))
```

### Asking questions

`ask`, `secret`, `confirm`, `anticipate`, and `choice` are the Laravel-shaped wrappers over [Prompts](/prompts/). `choice(..., multiple=True)` collects several answers.

## Programmatically executing commands

The `Artisan` façade runs commands from anywhere — controllers, jobs, other commands:

```python
from avalon.console import Artisan

Artisan.call("mail:send 7 --queue=bulk")
Artisan.call("mail:send", {"user": 7, "--queue": "bulk", "--cc": ["a@x.test", "b@x.test"]})
```

Keys beginning with `--` are options; a `True` boolean passes the flag and `False` omits it; lists repeat the option. `Artisan.output()` returns everything the last call printed, and `Artisan.call_silently()` runs without echoing it.

To run a command on a queue worker, `await Artisan.queue()` (Avalon's queue dispatch is async):

```python
await Artisan.queue("mail:send", {"user": 7}, queue="bulk")
```

### Calling commands from other commands

```python
def handle(self) -> int:
    self.call("cache:clear")
    self.call_silently("queue:restart")
    return self.SUCCESS
```

## Isolatable commands

Mix in `Isolatable` and the command gains an `--isolated` flag. While one instance holds the lock, other invocations exit immediately instead of running concurrently:

```python
from avalon.console import Command, Isolatable

class ImportOrders(Isolatable, Command):
    signature = "orders:import"

    def isolatable_id(self) -> str:
        return f"orders:import:{self.option('tenant')}"

    def isolation_lock_seconds(self) -> int:
        return 300
```

```bash
grail orders:import --isolated       # exits 0 when already running
grail orders:import --isolated=12    # exits 12 instead
```

The lock uses the [cache](/cache/) when a store is configured, and falls back to a filesystem mutex under `storage/framework/schedule`.

## Signal handling

`trap()` registers OS signal handlers for long-running commands:

```python
def handle(self) -> int:
    self.stopping = False
    self.trap([signal.SIGTERM, signal.SIGINT], lambda _sig: setattr(self, "stopping", True))
    while not self.stopping:
        self.work()
    return self.SUCCESS
```

## Events

The console dispatches through the [event dispatcher](/events/):

| Event | When |
| --- | --- |
| `ConsoleStarting` | The kernel finished discovering commands |
| `CommandStarting` | Before `handle()` runs — carries name, arguments, options |
| `CommandFinished` | After it returns — adds `exit_code` |

```python
from avalon.console import CommandFinished
from avalon.events import Event

Event.listen(CommandFinished, lambda event: log_duration(event.command, event.exit_code))
```

## Stub customization

Every generator — `make:model`, `make:controller`, `make:migration`, and the rest — renders a `.stub` file. Publish them to change what your application generates:

```bash
grail stub:publish
grail stub:publish --force   # overwrite stubs you have already published
```

The stubs land in `stubs/` at your project root. A generator prefers your copy and falls back to the framework's, so publish only the ones you want to change and delete the rest:

```
stubs/
├── model.stub
├── controller.stub
├── migration.stub
└── …
```

Placeholders are `{{ name }}`-style tokens, filled by the generator that renders the stub.

## Publishing package files

A service provider offers files to the application with `publishes()`, and the user copies them when they choose:

```python
class CourierServiceProvider(ServiceProvider):
    def boot(self) -> None:
        here = Path(__file__).parent
        self.publishes({here / "config" / "courier.py": self.app.path("config", "courier.py")}, "courier-config")
```

```bash
grail vendor:publish                                  # choose from a list
grail vendor:publish --tag=courier-config
grail vendor:publish --provider=courier.CourierServiceProvider
grail vendor:publish --tag=courier-config --force     # overwrite what is there
```

Declaring a path copies nothing on its own. Avalon publishes its own stubs and language files this way, under the `avalon-stubs` and `avalon-lang` tags.

## Registering commands

`ConsoleKernel` finds commands in four places, in order:

1. Framework commands in `avalon.console.commands` (e.g. `inspire`)
2. The application package `app.console.commands`
3. Files under `app/console/commands/*.py`, when that directory is not an importable package
4. Closure commands defined in `routes/console.py`

There is no list to maintain: a `Command` subclass with a `signature` in one of those places is a command. Everything Grail can run is a `Command` class, which is why `Artisan.call`, the scheduler, and the CLI all reach exactly the same set.

A command module that fails to import does not take the rest of the CLI down with it. Grail reports it and carries on:

```
Some commands could not be loaded:
  app.console.commands.broken: ModuleNotFoundError: No module named 'nowhere'
```

Failed command *runs* report through the exception `Handler` before exiting.

## Fiddle REPL

`grail fiddle` (or `tinker` / `repl`) boots the application and opens an interactive shell with helpers and models available.

Articulate is **async**. Fiddle auto-resolves coroutine expression results, so these both work:

```python
User.all()
await User.query().get()
users = run(User.all())   # explicit sync bridge for assignments
```

Results render as **JSON key/value panels** (models, collections, dicts, lists). Helpers:

```python
dump(users)          # pretty dump, continue
dd(users)            # dump and exit Fiddle
to_json(users)       # JSON string
serialize(users)     # plain Python dict/list
```

## `dump()` / `dd()`

Debug helpers live on the package root:

```python
from avalon import dump, dd

dump(user, request)   # Rich panel(s) in the terminal; execution continues
dd(User.find(1))      # same chrome, then halt
```

| Context | Behavior |
| --- | --- |
| HTTP **web** | Dedicated `dd()` HTML page (CDN-free), status 200 — not reported as an error |
| HTTP **api** | JSON `{dd, caller, values}` |
| Console command | Pretty print, exit code `0` |
| Fiddle | Pretty print, leave the REPL |

`DumpAndDie` is never logged by the exception Handler (`should_report` is false).

In Caliburn views: `@dump(user)` embeds an HTML card; `@dd(user)` halts with the dump page. See [Stacks & Directives](/caliburn/stacks/#debugging).

Shell preference:

1. **IPython** (preferred) — colored prompts, autoawait, coroutine displayhook
2. **ptpython** — if IPython is absent
3. **Rich fallback** — pretty output + tip to install IPython

```bash
pip install 'avalon[fiddle]'
# or, for contributors:
pip install -e '.[dev]'
```

Preloaded names typically include `app`, `config`, `Route`, `url`, `DB`, `Model`, `log`, `run`, and app models such as `User` / `Post` when present.

### Choosing what Fiddle preloads

`config/fiddle.py` decides what is waiting for you in the shell:

```python
config = {
    # Commands to have as callables: "inspire" → inspire()
    "commands": ["inspire"],
    # Extra names to import, as name -> dotted path
    "alias": {"Str": "avalon.support.Str"},
    # Names to keep out, even if a model would have claimed them
    "dont_alias": ["Post"],
}
```

Your models under `app/models` are aliased automatically; `dont_alias` wins over everything, including `alias`. A command listed in `commands` becomes a callable — `:` and `-` become `_`, arguments are positional, and options are keywords:

```python
inspire()
queue_work(once=True)     # grail queue:work --once
```

## Prompts

Interactive UI lives in [`avalon.console.prompts`](/prompts/) — `text`, `select`, `confirm`, `spin`, `progress`, and Command helpers `ask` / `choice` / `secret` / `anticipate`.

## Related

- [Prompts](/prompts/)
- [Task Scheduling](/scheduling/)
- [Error Handling](/errors/)
- [Logging](/logging/)
