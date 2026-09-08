---
title: Smith Console
description: Smith commands, Command classes, discovery, and the Loupe REPL.
---

## Smith

Every Almasix application ships **Smith** — the in-app CLI. With your virtualenv active and Almasix installed, run commands as `smith …`. You can also invoke the root `smith` script with `python smith …`.

```bash
smith list
smith make:command SendDigest
smith inspire
smith loupe
```

`smith list` prints every command Smith can reach, grouped by namespace, and `smith help <command>` describes one. [Command reference](#command-reference) lists what ships with the framework.

Framework commands (`serve`, `migrate`, `make:*`, …) live on the same surface as the `Command` classes your application declares — there is no second kind of command, which is why `Artisan.call` and the scheduler reach all of them.

## Loupe REPL

`smith loupe` (or `tinker` / `repl`) boots the application and opens an interactive shell with helpers and models available.

Articulate is **async**. Loupe auto-resolves coroutine expression results, so these both work:

```python
User.all()
await User.query().get()
users = run(User.all())   # explicit sync bridge for assignments
```

Results render as **JSON key/value panels** (models, collections, dicts, lists). Helpers:

```python
dump(users)          # pretty dump, continue
dd(users)            # dump and exit Loupe
to_json(users)       # JSON string
serialize(users)     # plain Python dict/list
```

## Writing commands

```python
# app/console/commands/send_digest.py
from almasix.console import Command

class SendDigest(Command):
    signature = "mail:digest {user?} {--queue=default}"
    description = "Send the daily digest"

    def handle(self) -> int:
        user = self.argument("user") or "everyone"
        self.info(f"Queue={self.option('queue')} → {user}")
        return 0
```

Generate a stub with `smith make:command SendDigest`.

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
from almasix.console import Artisan

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

`purpose()` (aliased as `describe()`) sets the description shown by `smith list`. Without it, the callable's first docstring line is used.

## Isolatable commands

Mix in `Isolatable` and the command gains an `--isolated` flag. While one instance holds the lock, other invocations exit immediately instead of running concurrently:

```python
from almasix.console import Command, Isolatable

class ImportOrders(Isolatable, Command):
    signature = "orders:import"

    def isolatable_id(self) -> str:
        return f"orders:import:{self.option('tenant')}"

    def isolation_lock_seconds(self) -> int:
        return 300
```

```bash
smith orders:import --isolated       # exits 0 when already running
smith orders:import --isolated=12    # exits 12 instead
```

The lock uses the [cache](/cache/) when a store is configured, and falls back to a filesystem mutex under `storage/framework/schedule`.

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
| `{tags...}` | Variadic — Almasix's original spelling of `{tags*}` |
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
smith mail:send 7 -Q bulk --cc=a@example.com --cc=b@example.com
```

`--cc` arrives as `["a@example.com", "b@example.com"]`. Everything after a bare `--` is treated as a positional value.

### Prompting for missing input

Mix in `PromptsForMissingInput` and a required argument that was not supplied is asked for instead of erroring:

```python
from almasix.console import Command, PromptsForMissingInput

class SendDigest(PromptsForMissingInput, Command):
    signature = "mail:digest {user}"

    def prompt_for_missing_arguments_using(self) -> dict:
        return {"user": "Which user should receive the digest?"}
```

Values may be callables for full control, and `prompt_for_missing_argument(name)` can be overridden outright. Without a mapping, Almasix asks `What is the user?`. In a non-interactive shell the underlying prompt raises rather than hanging.

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

## Registering commands

`ConsoleKernel` finds commands in four places, in order:

1. Framework commands in `almasix.console.commands` (e.g. `inspire`)
2. The application package `app.console.commands`
3. Files under `app/console/commands/*.py`, when that directory is not an importable package
4. Closure commands defined in `routes/console.py`

There is no list to maintain: a `Command` subclass with a `signature` in one of those places is a command. Everything Smith can run is a `Command` class, which is why `Artisan.call`, the scheduler, and the CLI all reach exactly the same set.

A command module that fails to import does not take the rest of the CLI down with it. Smith reports it and carries on:

```
Some commands could not be loaded:
  app.console.commands.broken: ModuleNotFoundError: No module named 'nowhere'
```

Failed command *runs* report through the exception `Handler` before exiting.

## Programmatically executing commands

The `Artisan` façade runs commands from anywhere — controllers, jobs, other commands:

```python
from almasix.console import Artisan

Artisan.call("mail:send 7 --queue=bulk")
Artisan.call("mail:send", {"user": 7, "--queue": "bulk", "--cc": ["a@x.test", "b@x.test"]})
```

Keys beginning with `--` are options; a `True` boolean passes the flag and `False` omits it; lists repeat the option. `Artisan.output()` returns everything the last call printed, and `Artisan.call_silently()` runs without echoing it.

To run a command on a queue worker, `await Artisan.queue()` (Almasix's queue dispatch is async):

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

## Stub customization

Every generator — `make:model`, `make:controller`, `make:migration`, and the rest — renders a `.stub` file. Publish them to change what your application generates:

```bash
smith stub:publish
smith stub:publish --force   # overwrite stubs you have already published
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
smith vendor:publish                                  # choose from a list
smith vendor:publish --tag=courier-config
smith vendor:publish --provider=courier.CourierServiceProvider
smith vendor:publish --tag=courier-config --force     # overwrite what is there
```

Declaring a path copies nothing on its own. Almasix publishes its own stubs and language files this way, under the `almasix-stubs` and `almasix-lang` tags.

## Events

The console dispatches through the [event dispatcher](/events/):

| Event | When |
| --- | --- |
| `ConsoleStarting` | The kernel finished discovering commands |
| `CommandStarting` | Before `handle()` runs — carries name, arguments, options |
| `CommandFinished` | After it returns — adds `exit_code` |

```python
from almasix.console import CommandFinished
from almasix.events import Event

Event.listen(CommandFinished, lambda event: log_duration(event.command, event.exit_code))
```

## Command reference

What the framework ships, 101 commands, as `smith list` groups them. An application's own commands appear alongside these.

### Top level

| Command | Description |
| --- | --- |
| `about` | Show a summary of the application's environment and drivers |
| `docs` | Open Almasix's documentation in a browser |
| `down` | Put the application into maintenance mode (scheduled tasks stop) |
| `env` | Display the current framework environment |
| `loupe` | Interactive Almasix REPL *(also `tinker`, `repl`)* |
| `help` | Describe a command — its usage, arguments, and options |
| `inspire` | Display an inspiring quote |
| `list` | List the commands available to Smith |
| `migrate` | Run outstanding migrations |
| `optimize` | Cache what Almasix can cache, and say what it deliberately does not |
| `serve` | Serve the application with Uvicorn |
| `test` | Run the application's tests through pytest |
| `up` | Bring the application out of maintenance mode |
| `version` | Show Almasix version |

### `cache`

| Command | Description |
| --- | --- |
| `cache:clear` | Flush the application cache |
| `cache:forget` | Remove one item from the cache |

### `channel`

| Command | Description |
| --- | --- |
| `channel:list` | List the registered broadcast channels |

### `config`

| Command | Description |
| --- | --- |
| `config:show` | Show a configuration value or namespace |

### `db`

| Command | Description |
| --- | --- |
| `db:monitor` | Monitor the number of connections on the specified database |
| `db:seed` | Seed the database using DatabaseSeeder (or --class) |
| `db:show` | Show information about a database connection and its tables |
| `db:table` | Show information about the given database table |
| `db:wipe` | Drop all tables from the database |

### `documents`

| Command | Description |
| --- | --- |
| `documents:index` | Create the indexes declared on document models |
| `documents:show` | Show the collections in a document store |

### `env`

| Command | Description |
| --- | --- |
| `env:decrypt` | Decrypt an encrypted environment file |
| `env:encrypt` | Encrypt the environment file |

### `errors`

| Command | Description |
| --- | --- |
| `errors:publish` | Publish framework error views into resources/views/errors/ |

### `event`

| Command | Description |
| --- | --- |
| `event:list` | List registered event listeners |

### `key`

| Command | Description |
| --- | --- |
| `key:generate` | Set the application key (APP_KEY) in .env |

### `lang`

| Command | Description |
| --- | --- |
| `lang:missing` | List keys present in the fallback locale but missing in the target |
| `lang:publish` | Publish framework language files into lang/ |

### `make`

| Command | Description |
| --- | --- |
| `make:cast` | Create an attribute cast in app/casts |
| `make:channel` | Create a broadcast channel class in app/broadcasting |
| `make:class` | Create a class in app, under the path its name gives |
| `make:command` | Create a console command in app/console/commands |
| `make:component` | Create an anonymous Prism component in resources/views/components |
| `make:controller` | Create a controller in app/http/controllers |
| `make:document` | Create a document model in app/models |
| `make:enum` | Create an enum in app/enums |
| `make:event` | Create a new event class |
| `make:exception` | Create an exception in app/exceptions |
| `make:factory` | Create a model factory in database/factories |
| `make:interface` | Create a Protocol in app/contracts |
| `make:job` | Create a queue job in app/jobs |
| `make:lang` | Create an empty lang/<locale>/ tree |
| `make:listener` | Create a new event listener class |
| `make:mail` | Create a mailable in app/mail |
| `make:middleware` | Create a middleware in app/http/middleware |
| `make:migration` | Create a migration in database/migrations |
| `make:model` | Create a model in app/models |
| `make:notification` | Create a notification in app/notifications |
| `make:observer` | Create a model observer in app/observers |
| `make:policy` | Create a new policy class |
| `make:provider` | Create a service provider in app/providers |
| `make:request` | Create a FormRequest in app/http/requests |
| `make:resource` | Create an API resource in app/http/resources |
| `make:rule` | Create a validation rule in app/rules |
| `make:seeder` | Create a seeder in database/seeders |
| `make:test` | Create a test in tests/feature (or tests/unit) |
| `make:view` | Create a Prism view in resources/views |

### `migrate`

| Command | Description |
| --- | --- |
| `migrate:fresh` | Drop all tables and re-run every migration |
| `migrate:install` | Create the migration repository table |
| `migrate:refresh` | Roll back every migration and run them again |
| `migrate:reset` | Roll back every migration that has run |
| `migrate:rollback` | Roll back the last migration batch |
| `migrate:status` | Show which migrations have run |

### `model`

| Command | Description |
| --- | --- |
| `model:prune` | Prune models that are no longer needed |
| `model:show` | Show a model's table, attributes, relationships, and events |

### `optimize`

| Command | Description |
| --- | --- |
| `optimize:clear` | Clear the application cache and the compiled templates |

### `queue`

| Command | Description |
| --- | --- |
| `queue:clear` | Delete all of the jobs waiting on a queue |
| `queue:failed` | List failed queue jobs |
| `queue:flush` | Delete all of the failed queue jobs |
| `queue:forget` | Delete a failed queue job |
| `queue:listen` | Listen to a given queue (continuous worker loop) |
| `queue:monitor` | Show the size of each named queue, flagging the busy ones |
| `queue:prune-failed` | Prune stale entries from the failed jobs table |
| `queue:restart` | Ask every running worker to stop once it finishes its current job |
| `queue:retry` | Retry a failed queue job |
| `queue:work` | Process the next job on a queue |

### `route`

| Command | Description |
| --- | --- |
| `route:list` | List the application's registered routes |

### `schedule`

| Command | Description |
| --- | --- |
| `schedule:clear-cache` | Release without-overlapping locks left behind by a stuck task |
| `schedule:interrupt` | Stop an in-progress schedule:run at the end of this second |
| `schedule:list` | List the scheduled tasks and when each next runs |
| `schedule:run` | Run the tasks that are due (wire this to cron, every minute) |
| `schedule:test` | Run one scheduled task now, whatever its frequency says |
| `schedule:work` | Run the scheduler in the foreground, minute after minute |

### `scout`

| Command | Description |
| --- | --- |
| `scout:delete-all-indexes` | Delete all indexes from the search engine |
| `scout:delete-index` | Delete an index from the search engine |
| `scout:flush` | Flush all of the model's records from the index |
| `scout:import` | Import the given model into the search index |
| `scout:index` | Create an index on the search engine |
| `scout:queue-import` | Import the given model into the search index using queued jobs |
| `scout:status` | Show the search engine and the models it indexes |
| `scout:sync-index-settings` | Sync the configured index settings with the search engine |

### `storage`

| Command | Description |
| --- | --- |
| `storage:link` | Create the symbolic links configured for the application |
| `storage:unlink` | Delete the symbolic links configured for the application |

### `stub`

| Command | Description |
| --- | --- |
| `stub:publish` | Publish the generator stubs into stubs/ so they can be edited |

### `vendor`

| Command | Description |
| --- | --- |
| `vendor:publish` | Publish the files a package's provider offers |

### `view`

| Command | Description |
| --- | --- |
| `view:cache` | Compile every Prism template |
| `view:clear` | Drop the compiled Prism templates |
## `dump()` / `dd()`

Debug helpers live on the package root:

```python
from almasix import dump, dd

dump(user, request)   # Rich panel(s) in the terminal; execution continues
dd(User.find(1))      # same chrome, then halt
```

| Context | Behavior |
| --- | --- |
| HTTP **web** | Dedicated `dd()` HTML page (CDN-free), status 200 — not reported as an error |
| HTTP **api** | JSON `{dd, caller, values}` |
| Console command | Pretty print, exit code `0` |
| Loupe | Pretty print, leave the REPL |

`DumpAndDie` is never logged by the exception Handler (`should_report` is false).

In Prism views: `@dump(user)` embeds an HTML card; `@dd(user)` halts with the dump page. See [Stacks & Directives](/prism/stacks/#debugging).

Shell preference:

1. **IPython** (preferred) — colored prompts, autoawait, coroutine displayhook
2. **ptpython** — if IPython is absent
3. **Rich fallback** — pretty output + tip to install IPython

```bash
pip install 'almasix[loupe]'
# or, for contributors:
pip install -e '.[dev]'
```

Preloaded names typically include `app`, `config`, `Route`, `url`, `DB`, `Model`, `log`, `run`, and app models such as `User` / `Post` when present.

### Choosing what Loupe preloads

`config/loupe.py` decides what is waiting for you in the shell:

```python
config = {
    # Commands to have as callables: "inspire" → inspire()
    "commands": ["inspire"],
    # Extra names to import, as name -> dotted path
    "alias": {"Str": "almasix.support.Str"},
    # Names to keep out, even if a model would have claimed them
    "dont_alias": ["Post"],
}
```

Your models under `app/models` are aliased automatically; `dont_alias` wins over everything, including `alias`. A command listed in `commands` becomes a callable — `:` and `-` become `_`, arguments are positional, and options are keywords:

```python
inspire()
queue_work(once=True)     # smith queue:work --once
```

## Prompts

Interactive UI lives in [`almasix.console.prompts`](/prompts/) — `text`, `select`, `confirm`, `spin`, `progress`, and Command helpers `ask` / `choice` / `secret` / `anticipate`.

## Related

- [Prompts](/prompts/)
- [Task Scheduling](/scheduling/)
- [Error Handling](/errors/)
- [Logging](/logging/)
