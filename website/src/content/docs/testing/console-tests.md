---
title: Console Tests
description: Run Smith commands from a test — answer their prompts, read their output, and assert on the code they exit with.
---

## Introduction

`artisan()` runs a command for real: the same kernel, the same signature
parsing, the same `handle()`. Only the terminal is a fake — questions are
answered from a queue the test fills, and output goes to a buffer the
assertions read.

```python
from almasix.testing import artisan


def test_the_importer_reports_what_it_did() -> None:
    artisan("app:import", {"file": "posts.csv"}).assert_successful()
```

Inside a `TestCase`, `self.artisan(...)` is the same call against the
application the case booted.

## Expectations

```python
(
    artisan("mail:send")
    .expects_question("Who is it for?", "ada@example.com")
    .expects_confirmation("Send it now?", True)
    .expects_choice("Which mailer?", "smtp", ["smtp", "log"])
    .expects_output("Sent 1 message")
    .doesnt_expect_output("Traceback")
    .expects_table(["Mailer", "Sent"], [["smtp", 1]])
    .assert_successful()
)
```

| Expectation | What it does |
| --- | --- |
| `expects_question(text, answer)` | Answers `ask()` and `anticipate()` |
| `expects_confirmation(text, answer)` | Answers `confirm()`; takes `True`, `"yes"`, or `False` |
| `expects_choice(text, answer, choices)` | Answers `choice()` |
| `expects_output(text)` | The command printed this |
| `doesnt_expect_output(text)` | The command did not |
| `expects_table(headers, rows)` | Every header and cell was printed |

An answer is matched to the question that contains its text, whatever order the
command asks in. A question nothing answers takes the command's own default, so
a test only has to say what it cares about.

## Assertions

```python
pending = artisan("app:import").assert_successful()

pending.assert_exit_code(0)
pending.assert_not_exit_code(1)
pending.assert_ok()             # the same as assert_successful()
pending.assert_failed()
pending.assert_output_contains("imported")
pending.assert_asked("Which file?")
pending.assert_nothing_asked()
```

The command runs on the first assertion and not again, so a chain of them reads
one run. `pending.output` and `pending.exit_code` are there for anything an
assertion does not cover.

## Arguments and options

Arguments and options are spelled the way Laravel spells them — one mapping,
with options carrying their dashes:

```python
artisan("app:import", {"file": "posts.csv", "--chunk": 100, "--dry-run": True})
```

`--dry-run` reaches the command as `dry_run`, the way the signature parser
names it.

## Which kernel

`artisan()` finds the console kernel the way `smith` does. Pass one explicitly
when a test builds its own:

```python
artisan("demo:greet", kernel=kernel).assert_successful()
artisan("demo:greet", app=application).assert_successful()
```

## Testing the command class

A command whose work lives in a method is worth testing directly, without the
console at all:

```python
async def test_the_importer_skips_rows_without_a_title() -> None:
    imported = await ImportPosts().import_rows([{"title": ""}, {"title": "Hi"}])

    assert imported == 1
```

Keep `handle()` thin enough that this is possible, and use `artisan()` for what
only the console can prove: the signature, the prompts, and the exit code.
