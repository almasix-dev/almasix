"""Locked M1 public contracts — fail if kernel DX regresses."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix import config as config_pkg
from almasix import framework as framework_pkg
from almasix import providers as providers_pkg
from almasix.config import config, env
from almasix.framework import Application, Container, ResolutionError
from almasix.installer.scaffold import scaffold_app
from almasix.providers import FoundationServiceProvider, ServiceProvider

pytestmark = [pytest.mark.regression]


class _ContractDep:
    pass


class _ContractConsumer:
    def __init__(self, dependency: _ContractDep) -> None:
        self.dependency = dependency


def test_public_exports_remain_stable() -> None:
    assert hasattr(framework_pkg, "Application")
    assert hasattr(framework_pkg, "Container")
    assert hasattr(framework_pkg, "ResolutionError")
    assert hasattr(config_pkg, "config")
    assert hasattr(config_pkg, "env")
    assert hasattr(config_pkg, "load_environment")
    assert hasattr(config_pkg, "ConfigRepository")
    assert hasattr(providers_pkg, "ServiceProvider")
    assert hasattr(providers_pkg, "FoundationServiceProvider")
    assert issubclass(FoundationServiceProvider, ServiceProvider)
    assert issubclass(ResolutionError, KeyError)


def test_bootstrap_lifecycle_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("APP_NAME=ContractApp\n", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "app.py").write_text(
        'config = {"name": "ContractApp", "providers": []}\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("APP_NAME", raising=False)

    app = Application(tmp_path)
    assert app.is_bootstrapped is False
    assert app.is_booted is False

    app.bootstrap()
    assert app.is_bootstrapped is True
    assert app.is_booted is True
    assert config("app.name") == "ContractApp"
    assert app.resolve(Application) is app
    assert app.make(Container) is app.container

    # Idempotent — regressions often break double-bootstrap
    app.bootstrap()
    assert app.is_bootstrapped is True


def test_scaffold_kernel_files_contract(tmp_path: Path) -> None:
    root = scaffold_app("contract_app", destination=tmp_path / "contract_app")
    required = [
        "smith",
        ".env",
        ".env.example",
        "bootstrap/app.py",
        "config/app.py",
        "app/providers/app_service_provider.py",
        "app/http/controllers/welcome_controller.py",
    ]
    for relative in required:
        assert (root / relative).exists(), f"missing scaffold file: {relative}"

    bootstrap = (root / "bootstrap" / "app.py").read_text(encoding="utf-8")
    assert "Application.configure(BASE_PATH)" in bootstrap
    assert "with_middleware" in bootstrap
    assert ".create()" in bootstrap
    assert "asgi = application.asgi" in bootstrap

    config_app = (root / "config" / "app.py").read_text(encoding="utf-8")
    assert "providers" in config_app
    assert "AppServiceProvider" in config_app


def test_container_autowire_contract() -> None:
    container = Container()
    container.singleton(_ContractDep, lambda c: _ContractDep())
    first = container.resolve(_ContractConsumer)
    second = container.resolve(_ContractConsumer)
    assert isinstance(first.dependency, _ContractDep)
    assert first is not second

    with pytest.raises(ResolutionError):
        container.resolve("not-registered")


def test_env_override_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real process env wins over ``.env`` (12-factor / Laravel dotenv default)."""
    monkeypatch.setenv("APP_NAME", "FromProcess")
    (tmp_path / ".env").write_text("APP_NAME=FromDotEnv\n", encoding="utf-8")
    from almasix.config import load_environment

    assert load_environment(tmp_path) is True
    assert env("APP_NAME") == "FromProcess"

    monkeypatch.delenv("APP_NAME", raising=False)
    assert load_environment(tmp_path) is True
    assert env("APP_NAME") == "FromDotEnv"
