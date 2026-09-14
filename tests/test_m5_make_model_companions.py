"""make:model companion flags (-c/-r/-s/-a/…) and clustered shorts."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.installer.scaffold import scaffold_app
from almasix.smith.cli import app as smith_app

runner = CliRunner()


def test_make_model_all_writes_companions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = scaffold_app("make_all", destination=tmp_path / "make_all")
    monkeypatch.chdir(root)
    result = runner.invoke(smith_app, ["make:model", "Flight", "-a"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    assert (root / "app" / "models" / "flight.py").is_file()
    assert (root / "database" / "factories" / "flight_factory.py").is_file()
    assert list((root / "database" / "migrations").glob("*create_flights_table.py"))
    assert (root / "database" / "seeders" / "flight_seeder.py").is_file()
    assert (root / "app" / "policies" / "flight_policy.py").is_file()
    controller = (root / "app" / "http" / "controllers" / "flight_controller.py").read_text(
        encoding="utf-8"
    )
    assert "async def show" in controller
    assert "from app.models.flight import Flight" in controller
    assert (root / "app" / "http" / "requests" / "store_flight_request.py").is_file()
    assert (root / "app" / "http" / "requests" / "update_flight_request.py").is_file()


def test_make_model_api_controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = scaffold_app("make_api", destination=tmp_path / "make_api")
    monkeypatch.chdir(root)
    result = runner.invoke(
        smith_app,
        ["make:model", "Ticket", "--api", "-c"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stdout
    body = (root / "app" / "http" / "controllers" / "ticket_controller.py").read_text(
        encoding="utf-8"
    )
    assert "async def show" in body
    assert "async def create" not in body  # API resource omits form actions


def test_make_model_clustered_seed_and_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = scaffold_app("make_sf", destination=tmp_path / "make_sf")
    monkeypatch.chdir(root)
    result = runner.invoke(smith_app, ["make:model", "Tag", "-mfs"], catch_exceptions=False)
    assert result.exit_code == 0, result.stdout
    assert (root / "database" / "factories" / "tag_factory.py").is_file()
    assert (root / "database" / "seeders" / "tag_seeder.py").is_file()
    assert list((root / "database" / "migrations").glob("*create_tags_table.py"))
