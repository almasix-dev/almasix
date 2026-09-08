"""Migration name inference (Laravel TableGuesser) and stub generation."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from almasix.orm import guess_migration, make_migration
from almasix.orm.migration import MigrationError, _load
from almasix.smith.cli import app as smith_app

runner = CliRunner()


@pytest.mark.parametrize(
    ("name", "table", "create"),
    [
        ("create_users_table", "users", True),
        ("create_users", "users", True),
        ("create_user_profiles_table", "user_profiles", True),
        ("create_widgets_table", "widgets", True),
        ("add_slug_to_posts_table", "posts", False),
        ("add_description_column_to_posts_table", "posts", False),
        # Mistaken create_ prefix must not invent table "add_slug_to_posts".
        ("create_add_slug_to_posts_table", "posts", False),
        ("add_payable_to_to_checks_table", "checks", False),
        ("drop_slug_from_posts_table", "posts", False),
        ("rename_title_in_posts_table", "posts", False),
        ("add_email_to_users", "users", False),
        ("do_something_custom", None, False),
    ],
)
def test_guess_migration(name: str, table: str | None, create: bool) -> None:
    assert guess_migration(name) == (table, create)


def test_make_migration_infers_create_stub(tmp_path: Path) -> None:
    path = make_migration("create_users_table", tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "class CreateUsersTable(Migration)" in text
    assert 'Schema.create(\n            "users"' in text or 'Schema.create(\n            "users",' in text
    assert "drop_if_exists(\"users\")" in text
    cls = _load(path)
    assert cls.__name__ == "CreateUsersTable"


def test_make_migration_infers_update_stub(tmp_path: Path) -> None:
    path = make_migration("add_slug_to_posts_table", tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "class AddSlugToPostsTable(Migration)" in text
    assert 'Schema.table(\n            "posts"' in text
    assert "Schema.create" not in text
    assert _load(path).__name__ == "AddSlugToPostsTable"

    # Accidental create_ prefix still yields an update stub for posts.
    mistyped = make_migration("create_add_slug_to_posts_table", tmp_path / "mistyped")
    mistyped_text = mistyped.read_text(encoding="utf-8")
    assert "Schema.create" not in mistyped_text
    assert 'Schema.table(\n            "posts"' in mistyped_text


def test_make_migration_blank_and_overrides(tmp_path: Path) -> None:
    blank = make_migration("do_something_custom", tmp_path)
    assert "class DoSomethingCustom(Migration)" in blank.read_text(encoding="utf-8")

    forced = make_migration(
        "create_users_table",
        tmp_path / "forced",
        table="accounts",
        create=True,
    )
    text = forced.read_text(encoding="utf-8")
    assert "class CreateUsersTable(Migration)" in text
    assert '"accounts"' in text

    alter = make_migration("touch_notes", tmp_path / "alter", table="notes", create=False)
    assert 'Schema.table(\n            "notes"' in alter.read_text(encoding="utf-8")

    with pytest.raises(MigrationError):
        make_migration("", tmp_path)


def test_cli_make_migration_infers_from_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrations = tmp_path / "database" / "migrations"
    migrations.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(
        smith_app,
        ["make:migration", "create_widgets_table"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.stdout
    files = list(migrations.glob("*_create_widgets_table.py"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "class CreateWidgetsTable(Migration)" in text
    assert '"widgets"' in text
