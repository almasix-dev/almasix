"""M56 — engine behaviour: bail, exclude, messages, Rule lists."""

from __future__ import annotations

from almasix.validation import Rule, ValidationException, validator


def test_bail_stops_after_first_failure() -> None:
    errors = validator({"f": "a"}, {"f": "bail|min:5|alpha_num"}).errors()
    assert list(errors) == ["f"]
    assert len(errors["f"]) == 1


def test_exclude_removes_field_from_validated() -> None:
    data = validator(
        {"keep": "1", "drop": "x"}, {"keep": "required", "drop": "exclude"}
    ).validated()
    assert data == {"keep": "1"}


def test_custom_messages_and_attributes() -> None:
    errors = validator(
        {},
        {"title": "required"},
        messages={"title.required": "Need a :attribute."},
        attributes={"title": "headline"},
    ).errors()
    assert errors["title"] == ["Need a headline."]


def test_rule_objects_in_list() -> None:
    assert validator({"n": "Ada"}, {"n": [Rule.required(), Rule.min(2)]}).passes()


def test_validated_raises() -> None:
    try:
        validator({}, {"n": "required"}).validate()
    except ValidationException as exc:
        assert exc.to_dict()["status"] == 422
        assert "n" in exc.errors
    else:
        raise AssertionError("expected ValidationException")
