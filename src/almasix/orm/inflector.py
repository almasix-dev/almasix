"""Minimal English inflection for table/key/relation naming."""

from __future__ import annotations

import re

_IRREGULAR = {
    "person": "people",
    "man": "men",
    "woman": "women",
    "child": "children",
    "tooth": "teeth",
    "foot": "feet",
    "mouse": "mice",
    "goose": "geese",
    "knife": "knives",
    "life": "lives",
    "wife": "wives",
    "leaf": "leaves",
    "tomato": "tomatoes",
    "potato": "potatoes",
    "hero": "heroes",
    "echo": "echoes",
}

_UNCOUNTABLE = {
    "equipment",
    "information",
    "money",
    "series",
    "sheep",
    "fish",
    "media",
    "news",
    "data",
}

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def snake(value: str) -> str:
    """`BlogPost` -> `blog_post`."""
    return _CAMEL_BOUNDARY.sub("_", value).replace("-", "_").lower()


def studly(value: str) -> str:
    """`blog_post` -> `BlogPost`."""
    parts = re.split(r"[_\-\s]+", value)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def camel(value: str) -> str:
    text = studly(value)
    return text[:1].lower() + text[1:]


def pluralize(value: str) -> str:
    lower = value.lower()
    if lower in _UNCOUNTABLE:
        return value
    if lower in _IRREGULAR:
        return _IRREGULAR[lower]

    if re.search(r"(s|x|z|ch|sh)$", lower):
        return value + "es"
    if re.search(r"[^aeiou]y$", lower):
        return value[:-1] + "ies"
    if lower.endswith("fe"):
        return value[:-2] + "ves"
    if lower.endswith("f"):
        return value[:-1] + "ves"
    if re.search(r"[^aeiou]o$", lower):
        return value + "es"
    return value + "s"


def singularize(value: str) -> str:
    lower = value.lower()
    if lower in _UNCOUNTABLE:
        return value
    for singular, plural in _IRREGULAR.items():
        if lower == plural:
            return singular

    if lower.endswith("ies") and len(value) > 3:
        return value[:-3] + "y"
    if lower.endswith("ves"):
        # knives → knife via irregular; leaves → leaf (ves → f) as a default.
        return value[:-3] + "f"
    if lower.endswith("oes") and not lower.endswith("shoes"):
        # tomatoes → tomato, heroes → hero (not shoes → sho).
        return value[:-2]
    if re.search(r"(s|x|z|ch|sh)es$", lower):
        return value[:-2]
    if lower.endswith("s") and not lower.endswith("ss"):
        return value[:-1]
    return value


def table_name(class_name: str) -> str:
    """`BlogPost` -> `blog_posts` (Eloquent's convention)."""
    return pluralize(snake(class_name))


def foreign_key(class_name: str, primary_key: str = "id") -> str:
    """`User` -> `user_id`."""
    return f"{snake(class_name)}_{primary_key}"


def pivot_table(first: str, second: str) -> str:
    """`User`, `Role` -> `role_user` (alphabetical singular join)."""
    names = sorted([snake(first), snake(second)])
    return "_".join(names)
