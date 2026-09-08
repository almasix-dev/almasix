from pathlib import Path

from typer.testing import CliRunner

from almasix.installer.cli import app as almasix_app
from almasix.installer.scaffold import ScaffoldError, scaffold_app, validate_app_name
from almasix.smith.cli import app as smith_app

runner = CliRunner()


def test_almasix_version() -> None:
    result = runner.invoke(almasix_app, ["version"])
    assert result.exit_code == 0
    assert "Almasix 0.1.0" in result.stdout


def test_almasix_new_creates_app(tmp_path: Path) -> None:
    result = runner.invoke(almasix_app, ["new", "demo_app", "--path", str(tmp_path)])
    assert result.exit_code == 0, result.stdout
    root = tmp_path / "demo_app"
    assert (root / "smith").is_file()
    assert (root / "bootstrap" / "app.py").is_file()
    assert (root / "app" / "http" / "controllers" / "welcome_controller.py").is_file()
    assert "Created Almasix application" in result.stdout


def test_almasix_new_rejects_existing(tmp_path: Path) -> None:
    scaffold_app("taken", destination=tmp_path / "taken")
    result = runner.invoke(almasix_app, ["new", "taken", "--path", str(tmp_path)])
    assert result.exit_code == 1


def test_smith_has_no_new_command() -> None:
    result = runner.invoke(smith_app, ["new", "demo"])
    assert result.exit_code != 0


def test_smith_version() -> None:
    result = runner.invoke(smith_app, ["version"])
    assert result.exit_code == 0
    assert "Almasix 0.1.0" in result.stdout


def test_smith_serve_requires_bootstrap(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(smith_app, ["serve"])
    assert result.exit_code == 1
    assert "bootstrap/app.py" in result.stderr


def test_validate_app_name() -> None:
    assert validate_app_name("blog") == "blog"
    try:
        validate_app_name("9bad")
        raise AssertionError("expected ScaffoldError")
    except ScaffoldError:
        pass
