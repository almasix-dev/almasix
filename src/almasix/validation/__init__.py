"""FormRequest and validation.

Pydantic is a declared part of the validation contract (unlike FastAPI, which
the HTTP kernel hides), so `Field` is re-exported for convenience. Laravel-style
string / ``Rule`` lists are available via ``validator(data, {...})`` and
``request.validate({...})``.
"""

from pydantic import Field

from almasix.validation.form_request import FormRequest, ValidationException
from almasix.validation.helpers import Validator, validator
from almasix.validation.messages import translate
from almasix.validation.rules import LARAVEL_RULES, Rule

__all__ = [
    "LARAVEL_RULES",
    "Field",
    "FormRequest",
    "Rule",
    "ValidationException",
    "Validator",
    "translate",
    "validator",
]
