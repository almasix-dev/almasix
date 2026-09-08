"""M3 — FormRequest validation and Laravel-shaped failure messages."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from almasix.framework import Application
from almasix.http import Controller, ForbiddenHttpException, Request
from almasix.routing import Route, set_router
from almasix.validation import Field, FormRequest, ValidationException
from tests.support import purge_generated_app_modules


class StoreRequest(FormRequest):
    name: str = Field(min_length=2, max_length=8)
    count: int = Field(default=1, ge=1, le=10)
    flag: bool = False
    tags: list[str] = Field(default_factory=list)
    note: str | None = None


class _Stub:
    """Minimal stand-in for the parts of Request that FormRequest touches."""

    def __init__(self, data: dict[str, object], headers: dict[str, str] | None = None) -> None:
        self._data = data
        self._headers = headers or {}

    def all(self) -> dict[str, object]:
        return dict(self._data)

    def header(self, key: str, default: object = None) -> object:
        return self._headers.get(key, default)

    def merge(self, values: dict[str, object]) -> None:
        self._data.update(values)


def test_valid_input_is_coerced_and_exposed() -> None:
    form = StoreRequest.validate_request(_Stub({"name": "almasix", "count": "3", "flag": "yes"}))

    assert form.data.name == "almasix"
    assert form.data.count == 3
    assert form.data.flag is True
    assert form.validated() == {
        "name": "almasix",
        "count": 3,
        "flag": True,
        "tags": [],
        "note": None,
    }
    assert form.validated("name", "count") == {"name": "almasix", "count": 3}
    assert form.validated("missing") == {}


def test_failure_messages_match_laravel_wording() -> None:
    with pytest.raises(ValidationException) as missing:
        StoreRequest.validate_request(_Stub({}))
    assert missing.value.to_dict() == {
        "message": "The given data was invalid.",
        "status": 422,
        "errors": {"name": ["The name field is required."]},
    }

    with pytest.raises(ValidationException) as invalid:
        StoreRequest.validate_request(
            _Stub({"name": "a", "count": 99, "flag": "maybe", "tags": "nope"})
        )
    errors = invalid.value.errors
    assert errors["name"] == ["The name must be at least 2 characters."]
    assert errors["count"] == ["The count may not be greater than 10."]
    assert errors["flag"] == ["The flag field must be true or false."]
    assert errors["tags"] == ["The tags must be an array."]

    with pytest.raises(ValidationException) as too_long:
        StoreRequest.validate_request(_Stub({"name": "wayyy-too-long"}))
    assert too_long.value.errors["name"] == [
        "The name may not be greater than 8 characters."
    ]


def test_size_messages_differ_for_strings_and_collections() -> None:
    class SizedRequest(FormRequest):
        code: str = Field(min_length=3)
        tags: list[str] = Field(default_factory=list, min_length=2, max_length=3)

    with pytest.raises(ValidationException) as short:
        SizedRequest.validate_request(_Stub({"code": "ab", "tags": ["one"]}))
    assert short.value.errors["code"] == ["The code must be at least 3 characters."]
    assert short.value.errors["tags"] == ["The tags must have at least 2 items."]

    with pytest.raises(ValidationException) as long:
        SizedRequest.validate_request(_Stub({"code": "abc", "tags": ["a", "b", "c", "d"]}))
    assert long.value.errors["tags"] == ["The tags may not have more than 3 items."]


def test_unmapped_errors_fall_back_to_pydantic_wording() -> None:
    from almasix.validation.messages import humanize, message_for

    assert humanize("first_name") == "first name"
    # An error type Almasix does not map keeps Pydantic's own message.
    assert message_for({"type": "some_new_type", "loc": ("x",), "msg": "Odd failure"}) == (
        "x",
        "Odd failure",
    )
    # Nested locations keep their dotted path.
    field, text = message_for({"type": "missing", "loc": ("address", "city"), "msg": ""})
    assert field == "address.city"
    assert text == "The address.city field is required."


def test_hooks_authorize_prepare_messages_and_attributes() -> None:
    class GuardedRequest(FormRequest):
        first_name: str
        slug: str = Field(default="x", min_length=3)

        def authorize(self) -> bool:
            return self.header("x-allow") == "yes"

        def prepare_for_validation(self) -> None:
            self.merge({"slug": str(self.all().get("slug", "")).lower()})

        def attributes(self) -> dict[str, str]:
            return {"slug": "URL slug"}

        def messages(self) -> dict[str, str]:
            return {"first_name.required": "We need your name."}

    with pytest.raises(ForbiddenHttpException) as denied:
        GuardedRequest.validate_request(_Stub({}))
    assert denied.value.to_dict() == {
        "message": "This action is unauthorized.",
        "status": 403,
        "errors": {},
    }

    allowed = {"x-allow": "yes"}
    with pytest.raises(ValidationException) as failed:
        GuardedRequest.validate_request(_Stub({"slug": "AB"}, allowed))
    assert failed.value.errors["first_name"] == ["We need your name."]
    # attributes() renames the field, prepare_for_validation() lowercased it.
    assert failed.value.errors["slug"] == ["The URL slug must be at least 3 characters."]

    ok = GuardedRequest.validate_request(_Stub({"first_name": "Ada", "slug": "ABC"}, allowed))
    assert ok.validated() == {"first_name": "Ada", "slug": "abc"}


def test_custom_validator_message_and_unvalidated_access() -> None:
    from pydantic import field_validator

    class CustomRequest(FormRequest):
        code: str

        @field_validator("code")
        @classmethod
        def _check(cls, value: str) -> str:
            if not value.startswith("AV-"):
                raise ValueError("The code must start with AV-.")
            return value

    with pytest.raises(ValidationException) as exc:
        CustomRequest.validate_request(_Stub({"code": "XX-1"}))
    assert exc.value.errors["code"] == ["The code must start with AV-."]

    form = CustomRequest(_Stub({"code": "AV-1"}))
    with pytest.raises(RuntimeError, match="has not been validated"):
        _ = form.data
    with pytest.raises(AttributeError):
        _ = form.nonexistent_helper


class ItemController(Controller):
    async def store(self, request: StoreRequest) -> dict[str, object]:
        return {"validated": request.validated(), "raw": request.all()}

    async def mixed(self, form: StoreRequest, raw: Request, item: str) -> dict[str, object]:
        return {"item": item, "validated": form.data.name, "path": raw.path}


def test_form_request_injects_into_controller_actions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    purge_generated_app_modules()
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "app.py").write_text(
        'config = {"name": "Validate", "debug": False, "providers": []}\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "http.py").write_text(
        "config = {'middleware': [], 'middleware_aliases': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "routes").mkdir()
    monkeypatch.chdir(tmp_path)
    app = Application(tmp_path)
    app.load_environment()
    app.load_configuration()
    app.register_configured_providers()
    app.boot()
    set_router(app.router)

    Route.post("/items", [ItemController, "store"])
    Route.post("/mixed/{item}", [ItemController, "mixed"])
    app._routes_loaded = True
    client = TestClient(app.asgi, raise_server_exceptions=False)

    ok = client.post("/items", json={"name": "almasix"})
    assert ok.status_code == 200
    assert ok.json()["validated"]["name"] == "almasix"
    # Query and body still merge, so the raw bag stays reachable.
    assert client.post("/items?extra=1", json={"name": "almasix"}).json()["raw"]["extra"] == "1"

    bad = client.post("/items", json={"name": ""})
    assert bad.status_code == 422
    assert bad.json()["errors"]["name"] == ["The name must be at least 2 characters."]

    # FormRequest injection must not shadow the M2 Request/route-param contract.
    mixed = client.post("/mixed/7", json={"name": "almasix"})
    assert mixed.json() == {"item": "7", "validated": "almasix", "path": "/mixed/7"}

    purge_generated_app_modules()
