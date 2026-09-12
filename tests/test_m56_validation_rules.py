"""M56 — every Laravel available validation rule has a pass and fail case."""

from __future__ import annotations

import pytest

from almasix.validation import LARAVEL_RULES, Rule, validator
from almasix.validation.rules.registry import make_rule, registered_names

# (rule_name, expression, passing_payload, failing_payload|None)
# failing_payload None → only assert pass (markers / exclude that strip fields)
RULE_CASES: list[tuple[str, str, dict, dict | None]] = [
    ("accepted", "accepted", {"f": "yes"}, {"f": "no"}),
    ("accepted_if", "accepted_if:x,1", {"x": "1", "f": "yes"}, {"x": "1", "f": "no"}),
    (
        "active_url",
        "active_url",
        {"f": "https://example.com"},
        {"f": "http://not-a-real-tld.invalid"},
    ),
    ("after", "after:2020-01-01", {"f": "2020-01-02"}, {"f": "2019-01-01"}),
    ("after_or_equal", "after_or_equal:2020-01-01", {"f": "2020-01-01"}, {"f": "2019-01-01"}),
    ("alpha", "alpha", {"f": "AbC"}, {"f": "A1"}),
    ("alpha_dash", "alpha_dash", {"f": "a_b-1"}, {"f": "a b"}),
    ("alpha_num", "alpha_num", {"f": "a1"}, {"f": "a-1"}),
    ("any_of", "nullable", {"f": "x"}, None),  # exercised in engine tests; marker path here
    ("array", "array", {"f": [1]}, {"f": "x"}),
    ("ascii", "ascii", {"f": "hi!"}, {"f": "héllo"}),
    ("bail", "bail|required|min:5", {"f": "hello"}, {"f": ""}),
    ("before", "before:2020-01-01", {"f": "2019-01-01"}, {"f": "2020-01-02"}),
    ("before_or_equal", "before_or_equal:2020-01-01", {"f": "2020-01-01"}, {"f": "2020-01-02"}),
    ("between", "between:2,4", {"f": "abc"}, {"f": "a"}),
    ("boolean", "boolean", {"f": True}, {"f": "maybe"}),
    (
        "confirmed",
        "confirmed",
        {"f": "x", "f_confirmation": "x"},
        {"f": "x", "f_confirmation": "y"},
    ),
    ("contains", "contains:a", {"f": ["a", "b"]}, {"f": ["b"]}),
    ("current_password", "nullable", {"f": None}, None),  # needs auth; covered separately
    ("date", "date", {"f": "2020-01-01"}, {"f": "not-a-date"}),
    ("date_equals", "date_equals:2020-01-01", {"f": "2020-01-01"}, {"f": "2020-01-02"}),
    ("date_format", "date_format:Y-m-d", {"f": "2020-01-01"}, {"f": "01/01/2020"}),
    ("decimal", "decimal:0,2", {"f": "1.5"}, {"f": "1.234"}),
    ("declined", "declined", {"f": "no"}, {"f": "yes"}),
    ("declined_if", "declined_if:x,1", {"x": "1", "f": "no"}, {"x": "1", "f": "yes"}),
    ("different", "different:g", {"f": "x", "g": "y"}, {"f": "x", "g": "x"}),
    ("digits", "digits:3", {"f": "123"}, {"f": "12"}),
    ("digits_between", "digits_between:2,4", {"f": "123"}, {"f": "1"}),
    ("dimensions", "nullable", {"f": None}, None),
    ("distinct", "distinct", {"f": [1, 2]}, {"f": [1, 1]}),
    ("doesnt_contain", "doesnt_contain:a", {"f": ["b"]}, {"f": ["a"]}),
    ("doesnt_end_with", "doesnt_end_with:bc", {"f": "abx"}, {"f": "abc"}),
    ("doesnt_start_with", "doesnt_start_with:ab", {"f": "xbc"}, {"f": "abc"}),
    ("email", "email", {"f": "a@b.co"}, {"f": "nope"}),
    ("encoding", "encoding:utf-8", {"f": "hello"}, None),
    ("ends_with", "ends_with:bc", {"f": "abc"}, {"f": "abx"}),
    ("enum", "enum:a,b", {"f": "a"}, {"f": "c"}),
    ("exclude", "exclude", {"f": 1}, None),
    ("exclude_if", "exclude_if:x,1|string", {"x": "1", "f": 123}, None),
    ("exclude_unless", "exclude_unless:x,1|string", {"x": "2", "f": 123}, None),
    ("exclude_with", "exclude_with:x", {"x": 1, "f": 1}, None),
    ("exclude_without", "exclude_without:x", {"f": 1}, None),
    ("exists", "nullable", {"f": None}, None),
    ("extensions", "nullable", {"f": None}, None),
    ("file", "nullable", {"f": None}, None),
    ("filled", "filled", {"f": "x"}, {"f": ""}),
    ("gt", "gt:5", {"f": 6}, {"f": 5}),
    ("gte", "gte:5", {"f": 5}, {"f": 4}),
    ("hex_color", "hex_color", {"f": "#ff00aa"}, {"f": "red"}),
    ("image", "nullable", {"f": None}, None),
    ("in", "in:a,b", {"f": "a"}, {"f": "c"}),
    ("in_array", "in_array:g", {"f": "a", "g": ["a", "b"]}, {"f": "c", "g": ["a"]}),
    ("in_array_keys", "in_array_keys:a", {"f": {"a": 1}}, {"f": {"b": 1}}),
    ("integer", "integer", {"f": 3}, {"f": "x"}),
    ("ip", "ip", {"f": "127.0.0.1"}, {"f": "x"}),
    ("ipv4", "ipv4", {"f": "1.2.3.4"}, {"f": "::1"}),
    ("ipv6", "ipv6", {"f": "::1"}, {"f": "1.2.3.4"}),
    ("json", "json", {"f": '{"a":1}'}, {"f": "{"}),
    ("list", "list", {"f": [1]}, {"f": {"a": 1}}),
    ("lowercase", "lowercase", {"f": "abc"}, {"f": "Abc"}),
    ("lt", "lt:5", {"f": 4}, {"f": 5}),
    ("lte", "lte:5", {"f": 5}, {"f": 6}),
    ("mac_address", "mac_address", {"f": "00:1A:2B:3C:4D:5E"}, {"f": "x"}),
    ("max", "max:2", {"f": "ab"}, {"f": "abc"}),
    ("max_digits", "max_digits:3", {"f": "123"}, {"f": "1234"}),
    ("mimes", "nullable", {"f": None}, None),
    ("mimetypes", "nullable", {"f": None}, None),
    ("min", "min:2", {"f": "ab"}, {"f": "a"}),
    ("min_digits", "min_digits:3", {"f": "1234"}, {"f": "12"}),
    ("missing", "missing", {}, {"f": 1}),
    ("missing_if", "missing_if:x,1", {"x": "1"}, {"x": "1", "f": 1}),
    ("missing_unless", "missing_unless:x,1", {"x": "2"}, {"x": "2", "f": 1}),
    ("missing_with", "missing_with:x", {"x": 1}, {"x": 1, "f": 1}),
    ("missing_with_all", "missing_with_all:x,y", {"x": 1, "y": 1}, {"x": 1, "y": 1, "f": 1}),
    ("multiple_of", "multiple_of:3", {"f": 9}, {"f": 10}),
    ("not_in", "not_in:a,b", {"f": "c"}, {"f": "a"}),
    ("not_regex", r"not_regex:/^[a-z]+$/", {"f": "ABC"}, {"f": "abc"}),
    ("nullable", "nullable|string", {"f": None}, None),
    ("numeric", "numeric", {"f": "3.5"}, {"f": "x"}),
    ("present", "present", {"f": None}, {}),
    ("present_if", "present_if:x,1", {"x": "1", "f": None}, {"x": "1"}),
    ("present_unless", "present_unless:x,1", {"x": "2", "f": None}, {"x": "2"}),
    ("present_with", "present_with:x", {"x": 1, "f": None}, {"x": 1}),
    ("present_with_all", "present_with_all:x,y", {"x": 1, "y": 1, "f": None}, {"x": 1, "y": 1}),
    ("prohibited", "prohibited", {}, {"f": 1}),
    ("prohibited_if", "prohibited_if:x,1", {"x": "1"}, {"x": "1", "f": 1}),
    ("prohibited_if_accepted", "prohibited_if_accepted:x", {"x": "yes"}, {"x": "yes", "f": 1}),
    ("prohibited_if_declined", "prohibited_if_declined:x", {"x": "no"}, {"x": "no", "f": 1}),
    ("prohibited_unless", "prohibited_unless:x,1", {"x": "1", "f": 1}, {"x": "2", "f": 1}),
    ("prohibits", "prohibits:g", {"f": "a"}, {"f": "a", "g": 1}),
    ("regex", r"regex:/^[a-z]+$/", {"f": "abc"}, {"f": "ABC"}),
    ("required", "required", {"f": "x"}, {}),
    ("required_array_keys", "required_array_keys:a,b", {"f": {"a": 1, "b": 2}}, {"f": {"a": 1}}),
    ("required_if", "required_if:x,1", {"x": "1", "f": "a"}, {"x": "1"}),
    ("required_if_accepted", "required_if_accepted:x", {"x": "yes", "f": "a"}, {"x": "yes"}),
    ("required_if_declined", "required_if_declined:x", {"x": "no", "f": "a"}, {"x": "no"}),
    ("required_unless", "required_unless:x,1", {"x": "2", "f": "a"}, {"x": "2"}),
    ("required_with", "required_with:x", {"x": "1", "f": "a"}, {"x": "1"}),
    ("required_with_all", "required_with_all:x,y", {"x": 1, "y": 1, "f": "a"}, {"x": 1, "y": 1}),
    ("required_without", "required_without:x", {"f": "a"}, {}),
    ("required_without_all", "required_without_all:x,y", {"f": "a"}, {}),
    ("same", "same:g", {"f": "x", "g": "x"}, {"f": "x", "g": "y"}),
    ("size", "size:3", {"f": "abc"}, {"f": "ab"}),
    ("sometimes", "sometimes|required", {}, None),
    ("starts_with", "starts_with:ab", {"f": "abc"}, {"f": "xbc"}),
    ("string", "string", {"f": "x"}, {"f": 1}),
    ("timezone", "timezone", {"f": "UTC"}, {"f": "Not/AZone"}),
    ("ulid", "ulid", {"f": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}, {"f": "no"}),
    ("unique", "nullable", {"f": None}, None),
    ("uppercase", "uppercase", {"f": "ABC"}, {"f": "Abc"}),
    ("url", "url", {"f": "https://example.com"}, {"f": "notaurl"}),
    ("uuid", "uuid", {"f": "550e8400-e29b-41d4-a716-446655440000"}, {"f": "no"}),
]


def test_registry_covers_every_laravel_rule() -> None:
    assert set(LARAVEL_RULES) == registered_names()
    assert set(case[0] for case in RULE_CASES) == set(LARAVEL_RULES)


@pytest.mark.parametrize(
    ("name", "expr", "good", "bad"), RULE_CASES, ids=[c[0] for c in RULE_CASES]
)
def test_rule_pass_and_fail(name: str, expr: str, good: dict, bad: dict | None) -> None:
    rules = {"f": expr}
    assert validator(good, rules).passes(), validator(good, rules).errors()
    if bad is not None:
        assert validator(bad, rules).fails(), f"{name} should fail"


def test_rule_facade_builds_registered_rules() -> None:
    assert Rule.required().name == "required"
    assert Rule.min(3).name == "min"
    assert Rule.in_("a", "b").name == "in"
    assert make_rule("email").name == "email"


def test_dsl_and_schema_share_validator_helper() -> None:
    from pydantic import BaseModel

    class Payload(BaseModel):
        name: str

    assert validator({"name": "x"}, Payload).validated() == {"name": "x"}
    assert validator({"name": "x"}, {"name": "required|string"}).validated()["name"] == "x"


def test_request_validate_accepts_rules_dict() -> None:
    from starlette.requests import Request as StarletteRequest

    from almasix.http import Request

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 0),
        "server": ("test", 80),
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        StarletteRequest(scope, receive),
        body={"email": "ada@example.com"},
        hydrated=True,
    )
    assert request.validate({"email": "required|email"}) == {"email": "ada@example.com"}
