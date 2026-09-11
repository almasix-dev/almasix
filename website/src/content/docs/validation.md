---
title: Validation
description: Validate incoming data with FormRequest before controller actions run.
---

Almasix validates HTTP input with **FormRequest** classes built on
**Pydantic v2**. Invalid input never reaches the controller action.

## Defining a form request

```python title="app/http/requests/store_post_request.py"
from pydantic import Field

from almasix.validation import FormRequest


class StorePostRequest(FormRequest):
    title: str = Field(min_length=3)
    published: bool = False

    async def authorize(self) -> bool:
        return True  # False → 403
```

Generate a stub:

```bash title="terminal"
smith make:request StorePostRequest
```

## Using it in a controller

Type-hint the FormRequest; the kernel builds, authorizes, and validates it:

```python title="app/http/controllers/post_controller.py"
class PostController(Controller):
    async def store(self, request: StorePostRequest) -> dict:
        return {"title": request.data.title}
```

Validated fields live on `request.data`. The FormRequest also **proxies** to
the underlying [`Request`](/requests/), so `input()`, `header()`, `file()`, and
friends remain available.

## Hooks

| Hook | Purpose |
| --- | --- |
| `authorize()` | Return `False` to abort with **403** |
| `prepare_for_validation()` | Mutate input before validation |
| `passed_validation()` | Run after a successful validate |
| `messages()` / `attributes()` | Customize error text and attribute names |
| `validation_data()` | Override the dict being validated |

Pydantic `@field_validator` / `@model_validator` on the FormRequest class are
honored.

## Failure envelope

Validation failures raise a **422** with this JSON shape:

```json title="response"
{
  "message": "The given data was invalid.",
  "status": 422,
  "errors": {
    "title": ["The title field must be at least 3 characters."]
  }
}
```

Messages resolve through Almasix's translator (localized catalogs under
`lang/`).

## Related

- [Requests](/requests/)
- [Controllers](/controllers/)
- [Error Handling](/errors/)
