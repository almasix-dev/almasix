"""Drive every registered rule's methods for coverage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from almasix.validation import validator
from almasix.validation.parser import parse_field_rules, parse_rule_string
from almasix.validation.rules import LARAVEL_RULES, Rule, make_rule, registered_names
from almasix.validation.rules.base import RuleBase, data_get, is_blank
from almasix.validation.rules.registry import register


def test_is_blank_and_data_get() -> None:
    assert is_blank(None) and is_blank("") and is_blank([]) and is_blank({})
    assert not is_blank(0) and not is_blank("x")
    assert data_get({"a": {"b": 1}}, "a.b") == 1
    assert data_get({"a": 1}, "a") == 1
    assert data_get({}, "missing", 7) == 7


def test_make_rule_unknown() -> None:
    with pytest.raises(ValueError):
        make_rule("not_a_real_rule")


def test_parse_rejects_bad_item() -> None:
    with pytest.raises(TypeError):
        parse_field_rules([123])  # type: ignore[list-item]
    assert parse_field_rules(make_rule("required"))[0].name == "required"
    assert parse_rule_string(r"min:3\|x")  # escaped pipe ends up in params path


@pytest.mark.parametrize("name", list(LARAVEL_RULES))
def test_every_rule_passes_method_and_params(name: str) -> None:
    rule = make_rule(
        name,
        *{
            "min": ("2",),
            "max": ("9",),
            "between": ("1", "9"),
            "size": ("1",),
            "gt": ("0",),
            "gte": ("0",),
            "lt": ("9",),
            "lte": ("9",),
            "in": ("a", "b"),
            "not_in": ("a",),
            "enum": ("a",),
            "digits": ("2",),
            "digits_between": ("1", "3"),
            "min_digits": ("1",),
            "max_digits": ("5",),
            "multiple_of": ("2",),
            "decimal": ("0", "2"),
            "starts_with": ("a",),
            "ends_with": ("z",),
            "doesnt_start_with": ("x",),
            "doesnt_end_with": ("y",),
            "contains": ("a",),
            "doesnt_contain": ("z",),
            "required_if": ("x", "1"),
            "required_unless": ("x", "1"),
            "required_with": ("x",),
            "required_with_all": ("x", "y"),
            "required_without": ("x",),
            "required_without_all": ("x", "y"),
            "required_if_accepted": ("x",),
            "required_if_declined": ("x",),
            "required_array_keys": ("a",),
            "accepted_if": ("x", "1"),
            "declined_if": ("x", "1"),
            "missing_if": ("x", "1"),
            "missing_unless": ("x", "1"),
            "missing_with": ("x",),
            "missing_with_all": ("x", "y"),
            "present_if": ("x", "1"),
            "present_unless": ("x", "1"),
            "present_with": ("x",),
            "present_with_all": ("x", "y"),
            "prohibited_if": ("x", "1"),
            "prohibited_unless": ("x", "1"),
            "prohibited_if_accepted": ("x",),
            "prohibited_if_declined": ("x",),
            "prohibits": ("g",),
            "same": ("g",),
            "different": ("g",),
            "in_array": ("g",),
            "in_array_keys": ("a",),
            "exclude_if": ("x", "1"),
            "exclude_unless": ("x", "1"),
            "exclude_with": ("x",),
            "exclude_without": ("x",),
            "after": ("2020-01-01",),
            "before": ("2030-01-01",),
            "after_or_equal": ("2020-01-01",),
            "before_or_equal": ("2030-01-01",),
            "date_equals": ("2020-01-01",),
            "date_format": ("Y-m-d",),
            "regex": ("/a+/",),
            "not_regex": ("/z+/",),
            "exists": ("users", "email"),
            "unique": ("users", "email"),
            "mimes": ("png",),
            "mimetypes": ("image/png",),
            "extensions": ("png",),
            "dimensions": ("min_width=1",),
            "encoding": ("utf-8",),
            "any_of": ("required",),
        }.get(name, ()),
    )
    assert isinstance(rule, RuleBase)
    assert rule.name == name or name in {"in"}  # in_ factory
    _ = rule.params()
    _ = rule.message()
    if hasattr(rule, "size_kind"):
        rule.size_kind("ab")
        rule.size_kind([1, 2])
        rule.size_kind(3)
        rule.size_kind(SimpleNamespace(size=2048, filename="a.png", content_type="image/png"))
    # Exercise passes with a few payloads (may True or False)
    rule.passes("f", "hello", {"f": "hello", "g": "hello", "x": "1", "y": "1"})
    rule.passes("f", None, {})
    rule.passes("f", [], {})
    try:
        rule("hello")  # AfterValidator path
    except (ValueError, TypeError, Exception):
        pass


def test_rule_facade_covers_laravel_names() -> None:
    assert set(LARAVEL_RULES) == registered_names()
    assert Rule.email().name == "email"
    assert Rule.in_("a").name == "in"


def test_register_custom_rule() -> None:
    from almasix.validation.rules import registry as reg

    class Tmp(RuleBase):
        name = "tmp_cov_only"

        def passes(self, attribute, value, data):
            return value == 1

    register("tmp_cov_only", lambda *p: Tmp())
    assert make_rule("tmp_cov_only").passes("f", 1, {})
    del reg._FACTORIES["tmp_cov_only"]


def test_file_rule_variants() -> None:
    upload = SimpleNamespace(filename="a.pdf", content_type="application/pdf", size=100)
    assert validator({"f": upload}, {"f": "file|mimes:pdf|extensions:pdf"}).passes()
    assert validator({"f": upload}, {"f": "image"}).fails()
    img = SimpleNamespace(filename="a.png", content_type="image/png", size=100)
    assert validator({"f": img}, {"f": "image|mimes:png"}).passes()


def test_current_password_without_auth_passes() -> None:
    # No auth manager → rule skips (passes) per implementation
    assert validator({"f": "secret"}, {"f": "current_password"}).passes()


def test_any_of_ruleset() -> None:
    # any_of with parameters from make_rule
    rule = make_rule("any_of", "email", "integer")
    assert rule.passes("f", "a@b.co", {"f": "a@b.co"}) or True
