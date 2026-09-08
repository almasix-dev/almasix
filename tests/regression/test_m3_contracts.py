"""Locked M3 public contracts — validation + DX."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.http import redirect
from almasix.installer.scaffold import scaffold_app
from almasix.routing import UrlGenerator, asset, url
from almasix.smith.make import BLUEPRINTS
from almasix.validation import Field, FormRequest, ValidationException

pytestmark = [pytest.mark.regression]


def test_m3_public_exports() -> None:
    assert Field is not None
    assert asset is not None and url is not None
    assert redirect is not None
    assert hasattr(FormRequest, "authorize")
    assert hasattr(FormRequest, "prepare_for_validation")
    assert hasattr(FormRequest, "passed_validation")
    assert hasattr(FormRequest, "messages")
    assert hasattr(FormRequest, "attributes")
    assert hasattr(FormRequest, "validated")
    assert hasattr(FormRequest, "validation_data")
    assert hasattr(FormRequest, "validate_request")


def test_validation_failure_reuses_the_locked_422_envelope() -> None:
    """M2 locked `{message, status, errors}` — M3 must not invent a new shape."""

    class Payload(FormRequest):
        email: str = Field(min_length=3)

    class _Stub:
        def all(self) -> dict[str, object]:
            return {}

    with pytest.raises(ValidationException) as exc:
        Payload.validate_request(_Stub())

    payload = exc.value.to_dict()
    assert set(payload) == {"message", "status", "errors"}
    assert payload["status"] == 422
    assert payload["message"] == "The given data was invalid."
    assert payload["errors"] == {"email": ["The email field is required."]}


def test_url_generation_never_emits_root_absolute_paths_under_a_prefix() -> None:
    generator = UrlGenerator("https://example.com", "/apps/foo")
    for path in ("/", "/progress", "api/health", "css/app.css"):
        assert generator.to(path, absolute=False).startswith("/apps/foo")


def test_make_blueprints_target_python_app_directories() -> None:
    assert BLUEPRINTS["controller"].directory == ("app", "http", "controllers")
    assert BLUEPRINTS["middleware"].directory == ("app", "http", "middleware")
    assert BLUEPRINTS["provider"].directory == ("app", "providers")
    assert BLUEPRINTS["request"].directory == ("app", "http", "requests")
    assert BLUEPRINTS["model"].directory == ("app", "models")


def test_scaffold_declares_base_path_config(tmp_path: Path) -> None:
    root = scaffold_app("m3_contract", destination=tmp_path / "m3_contract")
    assert "APP_BASE_PATH=" in (root / ".env").read_text(encoding="utf-8")
    assert 'env("APP_BASE_PATH"' in (root / "config" / "app.py").read_text(encoding="utf-8")
    welcome = (root / "app" / "http" / "controllers" / "welcome_controller.py").read_text(
        encoding="utf-8"
    )
    assert "url(" in welcome
