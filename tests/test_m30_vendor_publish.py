"""M30 — ``vendor:publish`` and the provider publishing contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from almasix.console.commands.vendor import VendorPublishCommand
from almasix.providers.provider import ServiceProvider


@pytest.fixture(autouse=True)
def forget_declarations() -> Any:
    ServiceProvider.forget_publishes()
    yield
    ServiceProvider.forget_publishes()


@pytest.fixture
def app(tmp_path: Path) -> Any:
    from almasix.framework.application import Application

    return Application(tmp_path)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    """A pretend installed package with a config file and an assets directory."""
    root = tmp_path / "vendor" / "courier"
    (root / "config").mkdir(parents=True)
    (root / "assets" / "css").mkdir(parents=True)
    (root / "config" / "courier.py").write_text("config = {'driver': 'pigeon'}\n")
    (root / "assets" / "css" / "courier.css").write_text(".courier { display: none }\n")
    (root / "assets" / "logo.svg").write_text("<svg/>\n")
    return root


def declare(app: Any, package: Path, *tags: str) -> type[ServiceProvider]:
    class CourierServiceProvider(ServiceProvider):
        def boot(self) -> None:
            self.publishes(
                {
                    package / "config" / "courier.py": app.path("config", "courier.py"),
                    package / "assets": app.path("public", "vendor", "courier"),
                },
                *tags,
            )

    CourierServiceProvider(app).boot()
    return CourierServiceProvider


def run(app: Any, **options: Any) -> tuple[int, str]:
    command = VendorPublishCommand(app)
    return command.run(None, options), ""


def test_a_provider_that_declares_nothing_offers_nothing(app: Any) -> None:
    assert ServiceProvider.publishable_providers() == []
    assert ServiceProvider.paths_to_publish() == {}


def test_declaring_paths_does_not_copy_them(app: Any, package: Path) -> None:
    declare(app, package)

    assert ServiceProvider.publishable_providers() != []
    assert not (app.path("config", "courier.py")).exists()


def test_publishing_a_provider_copies_its_files_and_its_directories(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = declare(app, package)

    code, _ = run(app, provider=provider.provider_name())
    output = capsys.readouterr().out

    assert code == 0
    assert (app.path("config", "courier.py")).read_text().startswith("config =")
    assert (app.path("public", "vendor", "courier", "css", "courier.css")).exists()
    assert (app.path("public", "vendor", "courier", "logo.svg")).exists()
    assert "Published" in output


def test_a_tag_publishes_across_providers(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    declare(app, package, "courier-config")

    code, _ = run(app, tag=["courier-config"])

    assert code == 0
    assert (app.path("config", "courier.py")).exists()
    assert "Published" in capsys.readouterr().out


def test_an_unknown_tag_says_so_rather_than_publishing_everything(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    declare(app, package, "courier-config")

    code, _ = run(app, tag=["nope"])

    assert code == 0
    assert "No files are tagged 'nope'" in capsys.readouterr().out
    assert not (app.path("config", "courier.py")).exists()


def test_a_provider_with_no_declarations_says_so(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    declare(app, package)

    code, _ = run(app, provider="app.providers.Nothing")

    assert code == 0
    assert "offers nothing to publish" in capsys.readouterr().out


def test_all_publishes_every_provider(app: Any, package: Path) -> None:
    declare(app, package)

    code, _ = run(app, **{"all": True})

    assert code == 0
    assert (app.path("config", "courier.py")).exists()


def test_an_existing_file_is_kept_unless_force_is_given(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = declare(app, package)
    destination = app.path("config", "courier.py")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("config = {'driver': 'mine'}\n")

    run(app, provider=provider.provider_name())
    assert "mine" in destination.read_text()
    assert "use --force" in capsys.readouterr().out

    run(app, provider=provider.provider_name(), force=True)
    assert "pigeon" in destination.read_text()


def test_existing_publishes_only_over_files_already_there(app: Any, package: Path) -> None:
    provider = declare(app, package)

    code, _ = run(app, provider=provider.provider_name(), existing=True)

    assert code == 0
    assert not (app.path("config", "courier.py")).exists()


def test_a_declared_path_that_is_missing_is_reported(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (package / "config" / "courier.py").unlink()
    provider = declare(app, package)

    code, _ = run(app, provider=provider.provider_name())

    assert code == 0
    assert "Missing:" in capsys.readouterr().err


def test_publishing_nothing_at_all_says_nothing_to_publish(
    app: Any, package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    provider = declare(app, package)
    run(app, provider=provider.provider_name())
    capsys.readouterr()

    run(app, provider=provider.provider_name())

    assert "Nothing to publish." in capsys.readouterr().out


def test_a_provider_and_a_tag_together_narrow_to_their_overlap(app: Any, package: Path) -> None:
    class OtherProvider(ServiceProvider):
        def boot(self) -> None:
            self.publishes(
                {package / "assets" / "logo.svg": app.path("public", "other.svg")}, "shared"
            )

    provider = declare(app, package, "shared")
    OtherProvider(app).boot()

    paths = ServiceProvider.paths_to_publish(provider.provider_name(), "shared")

    assert app.path("public", "other.svg") not in paths.values()
    assert app.path("config", "courier.py") in paths.values()


def test_with_no_selection_it_asks_rather_than_guessing(
    app: Any, package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    declare(app, package, "courier-config")
    asked: list[list[str]] = []

    def fake_choice(self: Any, question: str, choices: list[str], *args: Any, **kwargs: Any) -> str:
        asked.append(list(choices))
        return "Tag: courier-config"

    monkeypatch.setattr(VendorPublishCommand, "choice", fake_choice)

    code, _ = run(app)

    assert code == 0
    assert asked == [["Tag: courier-config", ServiceProvider.publishable_providers()[0]]]
    assert (app.path("config", "courier.py")).exists()


def test_choosing_a_provider_at_the_prompt_publishes_that_provider(
    app: Any, package: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = declare(app, package)
    monkeypatch.setattr(
        VendorPublishCommand,
        "choice",
        lambda self, question, choices, *a, **k: provider.provider_name(),
    )

    code, _ = run(app)

    assert code == 0
    assert (app.path("config", "courier.py")).exists()


def test_with_nothing_declared_at_all_it_fails_instead_of_prompting(
    app: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = run(app)

    assert code == 1
    assert "No provider offers anything to publish." in capsys.readouterr().err


def test_a_destination_outside_the_application_is_named_in_full(
    app: Any,
    package: Path,
    tmp_path_factory: pytest.TempPathFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outside = tmp_path_factory.mktemp("outside") / "logo.svg"

    class ElsewhereProvider(ServiceProvider):
        def boot(self) -> None:
            self.publishes({package / "assets" / "logo.svg": outside})

    ElsewhereProvider(app).boot()

    code, _ = run(app, provider=ElsewhereProvider.provider_name())

    assert code == 0
    assert outside.exists()
    assert str(outside) in capsys.readouterr().out


def test_a_command_without_an_application_still_names_its_destinations(
    package: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """``vendor:publish`` is only ever run inside an app, but output must not depend on one."""
    destination = tmp_path_factory.mktemp("appless") / "logo.svg"
    command = VendorPublishCommand(None)
    ServiceProvider._publishes["Bare"] = {package / "assets" / "logo.svg": destination}

    assert command.run(None, {"provider": "Bare"}) == 0
    assert str(destination) in capsys.readouterr().out


def test_the_framework_offers_its_own_stubs_and_language_files(tmp_path: Path) -> None:
    """``vendor:publish`` must not be an empty command in a fresh application."""
    from almasix.framework.application import Application

    application = Application(tmp_path)
    application.load_environment()
    application.load_configuration()
    application.register_configured_providers()
    application.boot()

    assert "almasix-stubs" in ServiceProvider.publishable_tags()
    assert "almasix-lang" in ServiceProvider.publishable_tags()

    command = VendorPublishCommand(application)
    assert command.run(None, {"tag": ["almasix-stubs"]}) == 0
    assert (tmp_path / "stubs" / "model.stub").exists()
