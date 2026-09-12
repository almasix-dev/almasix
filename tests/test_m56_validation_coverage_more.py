"""Close remaining coverage on engine / parser / helpers / messages."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError, field_validator

from almasix.validation import ValidationException, validator
from almasix.validation.engine import AttributeValidator
from almasix.validation.messages import humanize, translate
from almasix.validation.parser import parse_field_rules, parse_rule_string
from almasix.validation.rules.base import RuleBase


def test_attribute_validator_direct_api() -> None:
    runner = AttributeValidator({"n": "x"}, {"n": "required|min:1"})
    assert runner.passes()
    assert runner.validated() == {"n": "x"}
    assert runner.errors() == {}


def test_attribute_validator_raises() -> None:
    runner = AttributeValidator({}, {"n": "required"})
    with pytest.raises(ValidationException):
        runner.validated()


def test_prohibits_fails_when_other_present() -> None:
    assert validator({"a": "1", "b": "2"}, {"a": "prohibits:b"}).fails()
    assert validator({"a": "1"}, {"a": "prohibits:b"}).passes()


def test_exclude_unless_keeps_field_when_matched() -> None:
    # exclude unless x is 1 → when x=1, do NOT exclude → string must pass
    assert validator({"x": "1", "f": "ok"}, {"f": "exclude_unless:x,1|string"}).passes()


def test_parser_rulebase_and_regex_comma() -> None:
    rules = parse_field_rules(parse_rule_string("required")[0])
    assert rules[0].name == "required"
    rule = parse_rule_string(r"regex:/a,b/")[0]
    assert rule.name == "regex"


def test_helpers_schema_type_error() -> None:
    with pytest.raises(TypeError):
        validator({}, object).fails()  # type: ignore[arg-type]


def test_messages_override_format_and_blanks() -> None:
    class M(BaseModel):
        name: str

        @field_validator("name")
        @classmethod
        def _v(cls, value: str) -> str:
            raise ValueError("nope")

    try:
        M.model_validate({"name": "x"})
    except ValidationError as exc:
        bag = translate(
            exc,
            messages={"name": "bad {attribute} :attribute"},
            attributes={"name": "label"},
        )
        assert "name" in bag
        # broken format still returns something
        bag2 = translate(exc, messages={"name": "bad {unterminated"})
        assert "name" in bag2
    assert humanize("first_name") == "first name"


def test_rulebase_abstractmethod_path() -> None:
    class Empty(RuleBase):
        name = "empty"

    with pytest.raises(NotImplementedError):
        Empty().passes("f", 1, {})
