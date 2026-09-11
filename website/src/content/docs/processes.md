---
title: Processes
description: Run, stream, pool, and pipe subprocesses with Process.run and fakes for tests.
---

## Introduction

Almasix's process layer lives in `almasix.process`. It wraps Python's
`subprocess` behind one façade for running commands, waiting on them,
streaming their output, running them concurrently, piping one into the next,
and faking all of it in tests.

```python title="examples/processes.py"
from almasix.process import Process

result = Process.run("ls -la")

result.successful()     # True
result.exit_code()      # 0
result.output()         # the standard output
result.error_output()   # the standard error
```

The `ProcessServiceProvider` (registered with the foundation) binds a
process-wide `Factory`. You rarely construct it yourself.

## File map

| Piece | Path |
| --- | --- |
| Façade | `src/almasix/process/facade.py` — `Process` |
| Pending process | `src/almasix/process/pending.py` — `PendingProcess` |
| Result | `src/almasix/process/result.py` — `ProcessResult` |
| Running process | `src/almasix/process/invoked.py` — `InvokedProcess` |
| Pools | `src/almasix/process/pool.py` — `Pool`, `InvokedProcessPool`, `ProcessPoolResults` |
| Pipes | `src/almasix/process/pipe.py` — `Pipe` |
| Fakes / recording | `src/almasix/process/factory.py`, `src/almasix/process/fake.py` |
| Subprocess engine | `src/almasix/process/runner.py` — `ProcessHandle` |
| Provider | `src/almasix/process/provider.py` — `ProcessServiceProvider` |
| Exceptions | `src/almasix/process/exceptions.py` |

## Invoking processes

`Process.run()` runs a command and blocks until it finishes.

```python title="examples/processes.py"
result = Process.run("ls -la")
```

A **string** command runs through the shell, so pipes and globs work. A
**list** command does not, which is what you want for anything built from user
input:

```python title="examples/processes.py"
Process.run(["git", "commit", "-m", message])
```

### Throwing exceptions

`throw()` raises `ProcessFailedException` when the process failed and returns
the result otherwise, so it chains:

```python title="examples/processes.py"
Process.run("bash deploy.sh").throw()

result = Process.run("bash deploy.sh").throw_if(deploying)
result = Process.run("bash deploy.sh").throw_unless(dry_run)
```

`throw()` takes a callback that runs before the exception is raised:

```python title="examples/processes.py"
Process.run("bash deploy.sh").throw(
    lambda result, exception: logger.error(result.error_output())
)
```

The exception proxies the result, so `exception.exit_code()` and
`exception.error_output()` work, and `exception.result` is the result itself.

## Process options

Every option returns a **copy** of the pending process, so a configured builder
is safe to reuse:

```python title="examples/processes.py"
git = Process.path(repo).timeout(15)

git.run("git fetch")
git.run("git status")
```

### Working directory

```python title="examples/processes.py"
Process.path("/var/www/app").run("ls -la")
```

### Input

```python title="examples/processes.py"
Process.input("Hello World").run("cat")
```

### Timeouts

The default timeout is **60 seconds**, and blowing it raises
`ProcessTimedOutException` — which carries the partial result gathered before
the process was killed, on `exception.result`.

```python title="examples/processes.py"
Process.timeout(120).run("bash import.sh")
Process.forever().run("bash import.sh")
```

`idle_timeout()` measures time since the last byte of output rather than total
runtime:

```python title="examples/processes.py"
Process.timeout(60).idle_timeout(30).run("bash import.sh")
```

### Environment variables

Variables are merged into the environment the parent inherited:

```python title="examples/processes.py"
Process.env({"IMPORT_MODE": "test"}).run("bash import.sh")
```

### TTY mode

`tty()` connects the process to the parent's terminal. Output goes to the
screen, which means it is *not* captured and `result.output()` is empty.

```python title="examples/processes.py"
Process.tty().run("vim")
```

### Extra options

`options()` passes keyword arguments straight to `subprocess.Popen` for the
cases the façade does not name:

```python title="examples/processes.py"
Process.options({"start_new_session": True}).run("bash long-job.sh")
```

### Conditional configuration

```python title="examples/processes.py"
Process.when(verbose, lambda process, _: process.tty()).run("bash import.sh")
Process.unless(quiet, lambda process, _: process.tty()).run("bash import.sh")
```

## Process output

`output()` and `error_output()` return everything the process wrote.
`see_in_output()` and `see_in_error_output()` answer the common question
directly:

```python title="examples/processes.py"
if Process.run("ls -la").see_in_output("README.md"):
    ...
```

### Real-time output

Pass a callback as the second argument to `run()`. It receives the stream name
(`"out"` or `"err"`) and the chunk:

```python title="examples/processes.py"
Process.run("bash import.sh", lambda kind, chunk: print(chunk, end=""))
```

The constants live in `almasix.process` as `OUT` and `ERR`.

### Disabling process output

`quietly()` discards output rather than streaming it, and skips the callback:

```python title="examples/processes.py"
Process.quietly().run("bash import.sh")
```

## Pipelines

`Process.pipe()` feeds each command's output into the next one's input and
returns the **last** result. A failing stage short-circuits the pipeline and is
returned as-is.

```python title="examples/processes.py"
result = Process.pipe([
    "cat example.txt",
    "grep -i almasix",
])

result.output()
```

Name the stages when you want to know which one produced which output:

```python title="examples/processes.py"
Process.pipe(
    lambda pipe: [
        pipe.as_("read").command("cat example.txt"),
        pipe.as_("filter").command("grep -i almasix"),
    ],
    lambda kind, chunk, key: print(f"{key}: {chunk}", end=""),
)
```

## Asynchronous processes

`Process.start()` returns an `InvokedProcess` immediately.

```python title="examples/processes.py"
process = Process.start("bash import.sh")

while process.running():
    time.sleep(1)

result = process.wait()
```

| Method | What it does |
| --- | --- |
| `id()` | The process ID |
| `running()` | Whether the process is still going |
| `output()` / `error_output()` | Everything written so far |
| `latest_output()` / `latest_error_output()` | Only what arrived since the last call |
| `signal(sig)` | Send a signal |
| `stop(timeout=10, sig=None)` | Terminate, then kill if it outlives `timeout` |
| `wait(callback=None)` | Block for the result, optionally streaming output |

```python title="examples/processes.py"
process = Process.start("bash import.sh")

while process.running():
    print(process.latest_output(), end="")

process.signal(signal.SIGUSR2)
```

A started process still honours its timeout: `wait()` raises
`ProcessTimedOutException` once the deadline passes.

## Concurrent processes

`Process.pool()` collects processes and starts them together.

```python title="examples/processes.py"
pool = Process.pool(lambda pool: [
    pool.command("bash import-1.sh"),
    pool.command("bash import-2.sh"),
    pool.command("bash import-3.sh"),
])

running = pool.start()

while running.running().is_not_empty():
    time.sleep(0.1)

results = running.wait()

for result in results:
    print(result.output())
```

`Process.concurrently()` is the shorthand for start-then-wait:

```python title="examples/processes.py"
results = Process.concurrently(lambda pool: [
    pool.command("bash import-1.sh"),
    pool.command("bash import-2.sh"),
])

results[0].output()
```

### Naming pool processes

Integer keys are awkward to read, so name them with `as_()` — results answer to
the name *and* to the position:

```python title="examples/processes.py"
results = Process.concurrently(lambda pool: [
    pool.as_("first").command("bash import-1.sh"),
    pool.as_("second").command("bash import-2.sh"),
])

results["first"].output()
results[0].output()
```

`ProcessPoolResults` also gives you `successful()`, `failed()`, `keys()`,
`output()`, and `collect()` (a Support `Collection`).

### Pool process IDs and signals

```python title="examples/processes.py"
running = pool.start()

for process in running:
    print(process.id())

running.signal(signal.SIGUSR2)
running.stop()
```

The start callback receives the pool key as a third argument:

```python title="examples/processes.py"
pool.start(lambda kind, chunk, key: print(f"{key}: {chunk}", end=""))
```

## Testing

### Faking processes

`Process.fake()` with no arguments makes every process succeed with empty
output:

```python title="examples/processes.py"
Process.fake()

Process.run("bash import.sh")

Process.assert_ran("bash import.sh")
```

### Faking specific processes

Pass a mapping of command patterns to results. `*` is the only wildcard, and
patterns must match the whole command:

```python title="examples/processes.py"
Process.fake({
    "cat *": "file contents",
    "bash *": Process.result(error_output="failed", exit_code=1),
})
```

A bare string (or list of lines) becomes successful output.
`Process.result()` spells out all three parts:

```python title="examples/processes.py"
Process.result(output="ok", error_output="", exit_code=0)
Process.result(output=["line one", "line two"])
```

Commands with **no** matching pattern still run for real — `fake()` is a
mapping, not a wall. `prevent_stray_processes()` turns the misses into a
`StrayProcessException`:

```python title="examples/processes.py"
Process.fake({"cat *": "file contents"})
Process.prevent_stray_processes()

Process.run("rm -rf /")   # StrayProcessException
```

A callable stub receives the pending process, so the fake can depend on the
command:

```python title="examples/processes.py"
Process.fake(lambda process: Process.result(output=process.described_command))
```

### Faking process sequences

When the same command is run repeatedly and should answer differently:

```python title="examples/processes.py"
Process.fake({
    "bash deploy.sh": Process.sequence()
        .push_result(error_output="locked", exit_code=1)
        .push_output("deployed"),
})
```

A drained sequence raises `OutOfFakeProcesses`. `dont_fail_when_empty()` or
`when_empty(result)` opt out of that, `fail_when_empty()` restores it, and
`Process.assert_sequences_are_empty()` asserts every queued result was used.

`Process.fake_sequence("git *")` attaches a sequence to a pattern in one call.

### Faking asynchronous process lifecycles

`Process.describe()` scripts an asynchronous process: each `running()` check
releases the next chunk of output.

```python title="examples/processes.py"
Process.fake({
    "bash import.sh": Process.describe()
        .id(1234)
        .output("Import started")
        .error_output("Warning: slow")
        .output("Import finished")
        .exit_code(0)
        .iterations(3),
})

process = Process.start("bash import.sh")

while process.running():
    print(process.latest_output(), end="")
```

`runs_for(iterations=...)` is another name for the same iteration limit.
`replace_output()` and `replace_error_output()` discard what was scripted
before.

### Available assertions

| Assertion | Passes when |
| --- | --- |
| `Process.assert_ran(pattern_or_callable)` | At least one recorded process matches |
| `Process.assert_didnt_run(pattern_or_callable)` | None match |
| `Process.assert_ran_times(pattern, times)` | Exactly `times` match |
| `Process.assert_nothing_ran()` | No process ran at all |
| `Process.assert_sequences_are_empty()` | Every queued fake result was consumed |

A callable assertion receives the pending process, and the result too if it
takes a second argument:

```python title="examples/processes.py"
Process.assert_ran(lambda process: process.described_command == "ls -la")
Process.assert_ran(lambda process, result: result.successful())
```

`Process.recorded()` returns the `(process, result)` pairs directly, optionally
filtered by the same pattern or callable.

## Python-shaped details

- **`as_()` carries a trailing underscore** in pools and pipes, because `as` is
  a Python keyword. Same for `input`, which shadows a builtin only inside the
  builder.
- **Fluent calls copy** the pending process instead of mutating it, matching
  Almasix's HTTP client.
- **`options()` takes `subprocess.Popen` keyword arguments**, not a separate
  process-options vocabulary.
- **`described_command`** is a property, not a `command` accessor method, so it
  does not collide with the fluent `command()` setter.
- **Signals are the `signal` module's integers** — there is no
  cross-platform signal abstraction.
- **`quietly()` also silences the run callback.** Almasix captures output
  either way, so the callback is the only thing left to silence.
