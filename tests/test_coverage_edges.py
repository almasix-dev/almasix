"""Import milestone stubs and cover remaining edges for coverage."""

from __future__ import annotations

import almasix.auth
import almasix.http
import almasix.orm
import almasix.prism
import almasix.routing
import almasix.translation
import almasix.validation
from almasix.framework import Application, Container
from almasix.providers import ServiceProvider


def test_stub_packages_importable() -> None:
    assert almasix.routing.__all__
    assert "FormRequest" in almasix.validation.__all__
    assert "Translator" in almasix.translation.__all__
    assert "__" in almasix.translation.__all__
    assert "Model" in almasix.orm.__all__
    assert "QueryBuilder" in almasix.orm.__all__
    assert "AuthManager" in almasix.auth.__all__
    assert "Authenticate" in almasix.auth.__all__
    assert "Password" in almasix.auth.__all__
    assert "auth" in almasix.auth.__all__
    assert "Engine" in almasix.prism.__all__
    assert "view" in almasix.prism.__all__
    assert "Controller" in almasix.http.__all__
    assert "Route" in almasix.routing.__all__


def test_container_instance_edge() -> None:
    container = Container()
    container.instance("app_name", "Almasix")
    assert container.resolve("app_name") == "Almasix"
    container._instances["orphan"] = 42  # noqa: SLF001
    assert container.resolve("orphan") == 42


def test_service_provider_hooks() -> None:
    app = Application(base_path=".")
    provider = ServiceProvider(app)
    provider.register()
    provider.boot()
    assert provider.app is app
