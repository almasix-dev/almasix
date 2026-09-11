---
title: Prompts
description: Beautiful interactive console prompts for Smith commands.
---

## Introduction

Almasix Prompts give Smith commands rich terminal UX: styled text fields,
arrow-key selects, confirmations, spinners, and progress bars. Colours follow
**One Dark Pro** (true color when the terminal supports it) so interactive
prompts match Loupe and feel at home in a Smith session.

```python title="examples/prompts.py"
from almasix.console.prompts import text, select, confirm, spin, progress, intro, outro

intro("Create a user")
name = text("Name", required=True, placeholder="Ada Lovelace")
role = select("Role", ["admin", "editor", "viewer"], default="viewer")
if confirm("Proceed?", default=True):
    spin(lambda: create_user(name, role), "Creating…")
outro("Done")
```

Inside a `Command`, use the built-in helpers:

```python title="examples/prompts.py"
name = self.ask("Name", default="Sam")
role = self.choice("Role", ["admin", "user"])
secret = self.secret("API token")
ok = self.confirm("Continue?", default=True)
city = self.anticipate("City", ["Nairobi", "Mombasa"])
```

## Available prompts

| Helper | Purpose |
| --- | --- |
| `text` / `textarea` / `password` / `number` | Free-form input |
| `confirm` / `pause` | Yes/No and continue |
| `select` / `multiselect` | Arrow-key lists (space toggles multi) |
| `suggest` / `search` | Autocomplete / type-to-filter |
| `note` / `info` / `warning` / `error` / `alert` | Styled panels |
| `intro` / `outro` | Section bookends |
| `table` / `clear` | Rich table + clear screen |
| `spin` / `progress` | Busy UI |

### Validation

```python title="examples/prompts.py"
text(
    "Name",
    required="Name is required.",
    validate=lambda v: "Too short" if len(v) < 3 else None,
)
```

Return an error string from `validate`, or `None` when valid.

## Non-interactive fallbacks

When stdin/stdout are not a TTY, `CI=true`, or `ALMASIX_PROMPTS_INTERACTIVE=0`:

- Prompts return `default` (or the first option for `select`)
- `spin` / `progress` run without animation
- Missing required values raise `RuntimeError`

That keeps CI and scripted runs deterministic.

## Try it in your app

Add a Smith command that calls `text`, `select`, and `confirm`, then run it
from your app root:

```bash title="terminal"
python smith make:command GreetUser
# edit handle() to use the prompt helpers, then:
python smith greet:user
```

In CI (`CI=true`), prompts use defaults instead of waiting for a TTY.

## Related

- [Smith Console](/console/)
- [Task Scheduling](/scheduling/)
