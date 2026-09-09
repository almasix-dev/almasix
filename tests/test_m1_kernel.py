"""M1 kernel unit tests: env, config, container, providers, Application."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.config import ConfigRepository, config, env, load_environment, set_repository
from almasix.framework import Application, Container, ResolutionError
from almasix.providers import ServiceProvider


class Greeter:
    def __init__(self, suffix: str = "!") -> None:
        self.suffix = suffix

    def greet(self, name: str) -> str:
        return f"Hello {name}{self.suffix}"


class UsesGreeter:
    def __init__(self, greeter: Greeter) -> None:
        self.greeter = greeter


class CycleA:
    def __init__(self, other: CycleB) -> None:
        self.other = other


class CycleB:
    def __init__(self, other: CycleA) -> None:
        self.other = other


class OptionalCycleA:
    """A cycle whose parameters both have defaults."""

    def __init__(self, other: OptionalCycleB = None) -> None:  # type: ignore[assignment]
        self.other = other


class OptionalCycleB:
    def __init__(self, other: OptionalCycleA = None) -> None:  # type: ignore[assignment]
        self.other = other


class NeedsHint:
    def __init__(self, value) -> None:
        self.value = value


def test_env_invalid_numeric_defaults(monkeypatch) -> None:
    monkeypatch.setenv("BAD_INT", "nope")
    monkeypatch.setenv("BAD_FLOAT", "nope")
    assert env("BAD_INT", 9) == 9
    assert env("BAD_FLOAT", 1.25) == 1.25


def test_config_edge_paths(tmp_path: Path) -> None:
    repo = ConfigRepository()
    repo.load_directory(tmp_path / "missing")
    assert repo.get("") is None
    repo.set("x.y.z", 1)
    assert repo.get("x.y.z") == 1
    repo.set("x.y", {"z": 2})
    assert repo.get("x.y.z") == 2


def test_env_loader_and_coercion(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_NAME=KernelApp\nAPP_DEBUG=true\nAPP_PORT=8080\nAPP_RATIO=1.5\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_DEBUG", raising=False)
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("APP_RATIO", raising=False)

    assert load_environment(tmp_path) is True
    assert env("APP_NAME") == "KernelApp"
    assert env("APP_DEBUG", False) is True
    assert env("APP_PORT", 0) == 8080
    assert env("APP_RATIO", 0.0) == 1.5
    assert env("MISSING", "fallback") == "fallback"
    assert load_environment(tmp_path / "nope") is False


def test_config_repository_dot_access(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "app.py").write_text(
        'config = {"name": "Almasix", "nested": {"enabled": True}}\n',
        encoding="utf-8",
    )
    (config_dir / "database.py").write_text(
        'default = "sqlite"\nconnections = {"sqlite": {"driver": "sqlite"}}\n',
        encoding="utf-8",
    )

    repo = ConfigRepository()
    repo.load_directory(config_dir)
    assert repo.get("app.name") == "Almasix"
    assert repo.get("app.nested.enabled") is True
    assert repo.get("database.default") == "sqlite"
    assert repo.has("database.connections.sqlite.driver")
    assert repo.get("missing", "x") == "x"
    repo.set("app.timezone", "UTC")
    assert repo.get("app.timezone") == "UTC"
    assert "app" in repo.all()


def test_config_helper_requires_bootstrap() -> None:
    set_repository(None)
    with pytest.raises(RuntimeError, match="not set"):
        config("app.name")


def test_container_autowire_and_cycle() -> None:
    container = Container()
    container.singleton(Greeter, lambda c: Greeter("!!"))
    user = container.resolve(UsesGreeter)
    assert user.greeter.greet("Almasix") == "Hello Almasix!!"
    assert container.make(UsesGreeter) is not user

    container.singleton(UsesGreeter, lambda c: c._autowire(UsesGreeter))
    assert container.resolve(UsesGreeter) is container.resolve(UsesGreeter)

    with pytest.raises(ResolutionError, match="Circular"):
        container.resolve(CycleA)

    with pytest.raises(ResolutionError, match="no type hint"):
        container.resolve(NeedsHint)

    with pytest.raises(ResolutionError, match="Nothing bound"):
        container.resolve("missing-service")

    container.alias(Greeter, "greeter")
    assert container.has("greeter")
    assert container.resolve("greeter").suffix == "!!"


def test_an_annotated_parameter_with_a_default_may_go_unfilled() -> None:
    # A parameter that says both what it wants and what to do without it is
    # optional. Middleware written `def __init__(self, mode: str | None = None)`
    # must build even though nobody bound `str`.
    class Optional:
        def __init__(self, mode: str | None = None, greeter: Greeter | None = None) -> None:
            self.mode = mode
            self.greeter = greeter

    container = Container()

    built = container.resolve(Optional)

    assert built.mode is None
    assert built.greeter is None


def test_the_container_still_fills_a_default_when_something_is_bound() -> None:
    class Optional:
        def __init__(self, greeter: Greeter = None) -> None:  # type: ignore[assignment]
            self.greeter = greeter

    container = Container()
    container.singleton(Greeter, lambda c: Greeter("?"))

    assert container.resolve(Optional).greeter.suffix == "?"


def test_a_cycle_is_reported_even_when_the_parameter_has_a_default() -> None:
    # A default cannot stand in for a cycle: that is a mistake in the wiring
    # rather than a name nobody registered, and silence would hide it.
    from almasix.framework import CircularDependencyError

    with pytest.raises(CircularDependencyError, match="Circular"):
        Container().resolve(OptionalCycleA)


def test_bound_reports_registration_rather_than_buildability() -> None:
    class Plain:
        pass

    container = Container()

    assert container.bound(Plain) is False
    # ...and yet it builds, which is exactly why the two questions differ.
    assert isinstance(container.resolve(Plain), Plain)


def test_application_bootstrap(tmp_path: Path, monkeypatch) -> None:
    providers = tmp_path / "app" / "providers"
    providers.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (providers / "__init__.py").write_text("", encoding="utf-8")
    (providers / "tracking_provider.py").write_text(
        """
from almasix.providers import ServiceProvider

class TrackingProvider(ServiceProvider):
    registered = False
    booted = False

    def register(self):
        TrackingProvider.registered = True

    def boot(self):
        TrackingProvider.booted = True
""",
        encoding="utf-8",
    )

    (tmp_path / ".env").write_text("APP_NAME=BootedApp\nAPP_DEBUG=false\n", encoding="utf-8")
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "app.py").write_text(
        """
from almasix.config import env

config = {
    "name": env("APP_NAME", "Fallback"),
    "debug": env("APP_DEBUG", True),
    "providers": ["app.providers.tracking_provider.TrackingProvider"],
}
""",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    # Ensure no leftover living-example ``app`` package wins the import.
    from tests.support import purge_generated_app_modules

    purge_generated_app_modules()
    monkeypatch.delenv("APP_NAME", raising=False)
    monkeypatch.delenv("APP_DEBUG", raising=False)

    app = Application(tmp_path).bootstrap()
    assert app.is_bootstrapped is True
    assert app.is_booted is True
    assert app.config.get("app.name") == "BootedApp"
    assert app.config.get("app.debug") is False
    assert config("app.name") == "BootedApp"
    assert app.resolve(Application) is app
    assert app.make(ConfigRepository) is app.config

    app.bootstrap()
    app.boot()

    count = len(app._providers)
    app.config.set(
        "app.providers",
        ["almasix.providers.foundation.FoundationServiceProvider"],
    )
    app.register_configured_providers()
    # Foundation is always registered once; duplicate string entry is skipped.
    assert len(app._providers) == count + 1

    from app.providers.tracking_provider import TrackingProvider

    assert TrackingProvider.registered is True
    assert TrackingProvider.booted is True


def test_register_provider_instances_and_invalid(tmp_path: Path) -> None:
    app = Application(tmp_path)
    provider = ServiceProvider(app)
    assert app.register(provider) is provider

    with pytest.raises(TypeError):
        app.register(object())  # type: ignore[arg-type]

    with pytest.raises(ImportError):
        app.register("NotAPath")

    with pytest.raises(TypeError):
        app.register("almasix.framework.application.Application")
