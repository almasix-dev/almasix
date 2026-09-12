---
title: Validation
description: Validate HTTP input with request.validate, FormRequest, or validator() — available rules, custom rules, and the 422 envelope.
---

Almasix validates incoming data with a **rule engine** and optional **Pydantic**
FormRequest schemas. Invalid input becomes a **422** with a field → messages
map; valid input is ready for your controller.

## Quick start: `request.validate`

### Schema (Pydantic / FormRequest)

```python title="app/http/controllers/post_controller.py"
from almasix.http import Controller, Request
from almasix.validation import Field, FormRequest


class StorePostRules(FormRequest):
    title: str = Field(min_length=3)


class PostController(Controller):
    async def store(self, request: Request) -> dict:
        return request.validate(StorePostRules)
```

### Rule strings and `Rule` objects

```python title="app/http/controllers/post_controller.py"
data = request.validate({
    "title": "required|string|min:3",
    "email": ["required", "email"],
})
```

```python title="app/http/controllers/post_controller.py"
from almasix.validation import Rule

data = request.validate({
    "title": [Rule.required(), Rule.min(3)],
    "email": "required|email|unique:users,email",
})
```

## FormRequest injection

Type-hint a FormRequest; the kernel validates before the action:

```python title="app/http/controllers/post_controller.py"
async def store(self, request: StorePostRequest) -> dict:
    return {"title": request.data.title}
```

```bash title="terminal"
smith make:request StorePostRequest
```

## Soft checks

```python title="app/http/controllers/post_controller.py"
from almasix.validation import validator

check = validator(request.all(), {"email": "required|email"})
if check.fails():
    return {"errors": check.errors()}
return check.validated()
```

| Method | Purpose |
| --- | --- |
| `passes()` / `fails()` | Boolean outcome |
| `errors()` | `dict[str, list[str]]` |
| `validated()` / `validate()` | Cleaned dict or raise `ValidationException` |

## Available validation rules

Pipe syntax (`required|email`) and `Rule.*` both work unless a rule is
cross-field only (`required_if`, `confirmed`, `exclude_*`, and similar) — those
belong on the **rule-string / `Rule` list** path.

### accepted

The field must be yes, on, 1, or true.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "accepted"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.accepted()]})
```

### accepted_if

The field must be accepted when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "accepted_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.accepted_if()]})
```

### active_url

The field must be a URL with a resolvable host.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "active_url"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.active_url()]})
```

### after

The field must be a date after the given date or field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "after"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.after()]})
```

### after_or_equal

The field must be a date after or equal to the given date.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "after_or_equal"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.after_or_equal()]})
```

### alpha

The field must contain only letters.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "alpha"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.alpha()]})
```

### alpha_dash

The field may contain letters, numbers, dashes, and underscores.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "alpha_dash"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.alpha_dash()]})
```

### alpha_num

The field must contain only letters and numbers.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "alpha_num"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.alpha_num()]})
```

### any_of

The field must satisfy at least one of the given rule sets.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "any_of"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.any_of()]})
```

### array

The field must be a list or mapping.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "array"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.array()]})
```

### ascii

The field must contain only single-byte ASCII characters.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "ascii"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.ascii()]})
```

### bail

Stop running further rules for this field after the first failure.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "bail"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.bail()]})
```

### before

The field must be a date before the given date or field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "before"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.before()]})
```

### before_or_equal

The field must be a date before or equal to the given date.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "before_or_equal"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.before_or_equal()]})
```

### between

The field size must fall between the given min and max.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "between"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.between()]})
```

### boolean

The field must be true or false (including 0/1 string forms).

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "boolean"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.boolean()]})
```

### confirmed

The field must match `{field}_confirmation`.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "confirmed"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.confirmed()]})
```

### contains

A list field must contain the given values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "contains"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.contains()]})
```

### current_password

The field must match the authenticated user's password.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "current_password"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.current_password()]})
```

### date

The field must be a valid date.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "date"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.date()]})
```

### date_equals

The field must equal the given date.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "date_equals"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.date_equals()]})
```

### date_format

The field must match the given date format.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "date_format"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.date_format()]})
```

### decimal

The field must be numeric with the given decimal places.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "decimal"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.decimal()]})
```

### declined

The field must be no, off, 0, or false.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "declined"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.declined()]})
```

### declined_if

The field must be declined when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "declined_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.declined_if()]})
```

### different

The field must differ from another field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "different"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.different()]})
```

### digits

The field must be a number with exactly N digits.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "digits"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.digits()]})
```

### digits_between

The field must be a number with a digit count in range.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "digits_between"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.digits_between()]})
```

### dimensions

An uploaded image must match the given dimension constraints.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "dimensions"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.dimensions()]})
```

### distinct

A list field must not contain duplicate values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "distinct"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.distinct()]})
```

### doesnt_contain

A list field must not contain the given values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "doesnt_contain"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.doesnt_contain()]})
```

### doesnt_end_with

The field must not end with any of the given values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "doesnt_end_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.doesnt_end_with()]})
```

### doesnt_start_with

The field must not start with any of the given values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "doesnt_start_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.doesnt_start_with()]})
```

### email

The field must be a valid email address.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "email"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.email()]})
```

### encoding

The field must be valid in the given character encoding.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "encoding"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.encoding()]})
```

### ends_with

The field must end with one of the given values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "ends_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.ends_with()]})
```

### enum

The field must be one of the listed values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "enum"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.enum()]})
```

### exclude

Exclude this field from the validated payload.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "exclude"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.exclude()]})
```

### exclude_if

Exclude this field when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "exclude_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.exclude_if()]})
```

### exclude_unless

Exclude this field unless another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "exclude_unless"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.exclude_unless()]})
```

### exclude_with

Exclude this field when another field is present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "exclude_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.exclude_with()]})
```

### exclude_without

Exclude this field when another field is missing.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "exclude_without"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.exclude_without()]})
```

### exists

The value must exist in the given database table/column.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "exists"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.exists()]})
```

### extensions

An upload must have one of the given file extensions.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "extensions"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.extensions()]})
```

### file

The field must be an uploaded file.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "file"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.file()]})
```

### filled

If the field is present, it must not be empty.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "filled"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.filled()]})
```

### gt

The field must be greater than the given value or field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "gt"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.gt()]})
```

### gte

The field must be greater than or equal to the given value or field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "gte"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.gte()]})
```

### hex_color

The field must be a valid hexadecimal color.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "hex_color"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.hex_color()]})
```

### image

The field must be an image upload.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "image"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.image()]})
```

### in

The field must be one of the listed values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "in:a,b,c"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.in_("a", "b", "c")]})
```

### in_array

The field value must exist in another field's list.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "in_array"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.in_array()]})
```

### in_array_keys

A mapping field must contain at least one of the given keys.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "in_array_keys"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.in_array_keys()]})
```

### integer

The field must be an integer.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "integer"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.integer()]})
```

### ip

The field must be a valid IP address.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "ip"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.ip()]})
```

### ipv4

The field must be a valid IPv4 address.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "ipv4"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.ipv4()]})
```

### ipv6

The field must be a valid IPv6 address.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "ipv6"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.ipv6()]})
```

### json

The field must be a valid JSON string.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "json"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.json()]})
```

### list

The field must be a list (not a mapping).

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "list"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.list()]})
```

### lowercase

The field must be lowercase.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "lowercase"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.lowercase()]})
```

### lt

The field must be less than the given value or field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "lt"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.lt()]})
```

### lte

The field must be less than or equal to the given value or field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "lte"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.lte()]})
```

### mac_address

The field must be a valid MAC address.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "mac_address"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.mac_address()]})
```

### max

The field size must be at most the given maximum.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "max:10"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.max(10)]})
```

### max_digits

A numeric field may have at most N digits.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "max_digits"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.max_digits()]})
```

### mimes

An upload must match one of the given extensions.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "mimes"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.mimes()]})
```

### mimetypes

An upload must match one of the given MIME types.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "mimetypes"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.mimetypes()]})
```

### min

The field size must be at least the given minimum.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "min:3"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.min(3)]})
```

### min_digits

A numeric field must have at least N digits.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "min_digits"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.min_digits()]})
```

### missing

The field must not be present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "missing"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.missing()]})
```

### missing_if

The field must be missing when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "missing_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.missing_if()]})
```

### missing_unless

The field must be missing unless another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "missing_unless"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.missing_unless()]})
```

### missing_with

The field must be missing when any of the given fields are present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "missing_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.missing_with()]})
```

### missing_with_all

The field must be missing when all given fields are present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "missing_with_all"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.missing_with_all()]})
```

### multiple_of

The field must be a multiple of the given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "multiple_of"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.multiple_of()]})
```

### not_in

The field must not be one of the listed values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "not_in"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.not_in()]})
```

### not_regex

The field must not match the given pattern.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "not_regex"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.not_regex()]})
```

### nullable

Empty values are allowed; other rules are skipped when empty.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "nullable"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.nullable()]})
```

### numeric

The field must be numeric.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "numeric"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.numeric()]})
```

### present

The field must be present (may be empty).

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "present"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.present()]})
```

### present_if

The field must be present when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "present_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.present_if()]})
```

### present_unless

The field must be present unless another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "present_unless"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.present_unless()]})
```

### present_with

The field must be present when any of the given fields are present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "present_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.present_with()]})
```

### present_with_all

The field must be present when all given fields are present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "present_with_all"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.present_with_all()]})
```

### prohibited

The field must not be present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "prohibited"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.prohibited()]})
```

### prohibited_if

The field is prohibited when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "prohibited_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.prohibited_if()]})
```

### prohibited_if_accepted

The field is prohibited when another field is accepted.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "prohibited_if_accepted"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.prohibited_if_accepted()]})
```

### prohibited_if_declined

The field is prohibited when another field is declined.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "prohibited_if_declined"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.prohibited_if_declined()]})
```

### prohibited_unless

The field is prohibited unless another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "prohibited_unless"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.prohibited_unless()]})
```

### prohibits

When this field is present, the listed fields must be missing.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "prohibits"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.prohibits()]})
```

### regex

The field must match the given pattern.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": r"regex:/^[a-z]+$/"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.regex("^[a-z]+$")]})
```

### required

The field must be present and not empty.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required()]})
```

### required_array_keys

A mapping must contain the listed keys.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_array_keys"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_array_keys()]})
```

### required_if

The field is required when another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_if"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_if()]})
```

### required_if_accepted

The field is required when another field is accepted.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_if_accepted"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_if_accepted()]})
```

### required_if_declined

The field is required when another field is declined.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_if_declined"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_if_declined()]})
```

### required_unless

The field is required unless another field has a given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_unless"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_unless()]})
```

### required_with

The field is required when any of the given fields are present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_with()]})
```

### required_with_all

The field is required when all given fields are present.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_with_all"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_with_all()]})
```

### required_without

The field is required when any of the given fields are missing.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_without"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_without()]})
```

### required_without_all

The field is required when all given fields are missing.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "required_without_all"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.required_without_all()]})
```

### same

The field must match another field.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "same"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.same()]})
```

### size

The field size must equal the given value.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "size"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.size()]})
```

### sometimes

Only validate this field when it is present on the payload.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "sometimes"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.sometimes()]})
```

### starts_with

The field must start with one of the given values.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "starts_with"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.starts_with()]})
```

### string

The field must be a string.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "string"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.string()]})
```

### timezone

The field must be a valid timezone identifier.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "timezone"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.timezone()]})
```

### ulid

The field must be a valid ULID.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "ulid"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.ulid()]})
```

### unique

The value must be unique in the given database table/column.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "unique"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.unique()]})
```

### uppercase

The field must be uppercase.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "uppercase"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.uppercase()]})
```

### url

The field must be a valid URL.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "url"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.url()]})
```

### uuid

The field must be a valid UUID.

```python title="app/http/controllers/example_controller.py"
request.validate({"field": "uuid"})
# or
from almasix.validation import Rule
request.validate({"field": [Rule.uuid()]})
```

## Custom rules

```bash title="terminal"
smith make:rule Uppercase
```

Attach with `AfterValidator` on a FormRequest field, or raise `ValueError` from
`@field_validator`.

## Messages

Override per call with `messages=` / `attributes=`, via FormRequest
`messages()` / `attributes()`, or publish the catalog:

```bash title="terminal"
smith lang:publish
```

## Failure envelope

```json title="response"
{
  "message": "The given data was invalid.",
  "status": 422,
  "errors": {
    "email": ["The email field must be a valid email address."]
  }
}
```

## Related

- [Requests](/requests/)
- [Controllers](/controllers/)
- [Error Handling](/errors/)
- [Helpers](/helpers/#validator)
