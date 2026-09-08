"""Shipped English validation messages — byte-identical to M3 wording."""

translations = {
    "required": "The :attribute field is required.",
    "string": "The :attribute must be a string.",
    "integer": "The :attribute must be an integer.",
    "numeric": "The :attribute must be a number.",
    "boolean": "The :attribute field must be true or false.",
    "array": "The :attribute must be an array.",
    "min": {
        "string": "The :attribute must be at least :min characters.",
        "array": "The :attribute must have at least :min items.",
        "numeric": "The :attribute must be at least :min.",
        "file": "The :attribute must be at least :min kilobytes.",
    },
    "max": {
        "string": "The :attribute may not be greater than :max characters.",
        "array": "The :attribute may not have more than :max items.",
        "numeric": "The :attribute may not be greater than :max.",
        "file": "The :attribute may not be greater than :max kilobytes.",
    },
    "gt": "The :attribute must be greater than :min.",
    "lt": "The :attribute must be less than :max.",
    "regex": "The :attribute format is invalid.",
    "in": "The selected :attribute is invalid.",
    "url": "The :attribute must be a valid URL.",
    "uuid": "The :attribute must be a valid UUID.",
    "date": "The :attribute is not a valid date.",
    "json": "The :attribute must be a valid JSON string.",
    "custom": "The :attribute is invalid.",
}
