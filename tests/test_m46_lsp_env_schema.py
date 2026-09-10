"""Env-key and database-schema intelligence for the language server."""

from __future__ import annotations

from pathlib import Path

import pytest

from almasix.lsp.analysis import (
    call_at,
    context_at,
    dotenv_context_at,
    find_database_calls,
)
from almasix.lsp.env_context import (
    discover_env_keys,
    display_value,
    is_secret_key,
    parse_env_file,
)
from almasix.lsp.features import completions, definition, hover
from almasix.lsp.index import build_index
from almasix.lsp.schema_context import (
    discover_migration_schema,
    discover_model_tables,
    merge_tables,
    resolve_table,
)
from tests.support import purge_generated_app_modules, without_base_path

PROGRESS = Path(__file__).resolve().parents[1] / "examples" / "progress"


@pytest.fixture()
def progress_index(monkeypatch: pytest.MonkeyPatch):
    without_base_path(monkeypatch)
    purge_generated_app_modules()
    monkeypatch.chdir(PROGRESS)
    monkeypatch.syspath_prepend(str(PROGRESS))
    index = build_index(PROGRESS)
    assert index.ok, index.error
    return index


def test_parse_env_file_handles_quotes_comments_and_export(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# greeting\n"
        "APP_NAME=Progress\n"
        "export APP_URL='http://localhost'\n"
        'APP_KEY="base64:secret"  # keep\n'
        "EMPTY=\n",
        encoding="utf-8",
    )
    parsed = parse_env_file(path)
    assert parsed["APP_NAME"] == ("Progress", 1)
    assert parsed["APP_URL"] == ("http://localhost", 2)
    assert parsed["APP_KEY"] == ("base64:secret", 3)
    assert parsed["EMPTY"] == ("", 4)


def test_secret_values_are_redacted() -> None:
    assert is_secret_key("APP_KEY")
    assert is_secret_key("DB_PASSWORD")
    assert display_value("APP_KEY", "base64:abc") == "********"
    assert display_value("APP_NAME", "Progress") == "Progress"


def test_discover_env_keys_merges_files_and_config_usages(tmp_path: Path) -> None:
    # Progress may only ship ``.env.example`` in CI (``.env`` is gitignored).
    example = PROGRESS / ".env.example"
    assert example.is_file()
    found = discover_env_keys(PROGRESS)
    assert "APP_NAME" in found
    assert found["APP_NAME"].kind in {"env", "example"}
    assert any("config/app.py" in origin for origin in found["APP_NAME"].used_by)
    # DB_PASSWORD is only declared via env() with an empty default in the progress app.
    assert "DB_PASSWORD" in found
    assert found["DB_PASSWORD"].used_by

    # A real ``.env`` must win over the template.
    root = tmp_path / "app"
    root.mkdir()
    (root / ".env.example").write_text("APP_NAME=Example\n", encoding="utf-8")
    (root / ".env").write_text("APP_NAME=Live\n", encoding="utf-8")
    (root / "config").mkdir()
    (root / "config" / "app.py").write_text(
        'NAME = env("APP_NAME", "fallback")\n',
        encoding="utf-8",
    )
    merged = discover_env_keys(root)
    assert merged["APP_NAME"].kind == "env"
    assert merged["APP_NAME"].value == "Live"


def test_env_completion_definition_and_hover(progress_index) -> None:
    source = 'name = env("APP_")'
    items = completions(progress_index, source, 0, source.index("APP_") + 4, language="python")
    labels = {item.label for item in items}
    assert "APP_NAME" in labels
    assert "APP_KEY" in labels

    closed = 'name = env("APP_NAME")'
    loc = definition(
        progress_index,
        closed,
        0,
        closed.index("APP_NAME") + 1,
        language="python",
    )
    assert loc is not None
    assert loc.path.name in {".env", ".env.example"}

    tip = hover(
        progress_index,
        closed,
        0,
        closed.index("APP_NAME") + 1,
        language="python",
    )
    assert tip is not None
    assert "APP_NAME" in tip.contents

    secret = 'key = env("APP_KEY")'
    secret_tip = hover(
        progress_index,
        secret,
        0,
        secret.index("APP_KEY") + 1,
        language="python",
    )
    assert secret_tip is not None
    assert "********" in secret_tip.contents
    assert "base64:" not in secret_tip.contents


def test_dotenv_interpolation_and_key_completion(progress_index) -> None:
    source = "APP_NAME=Progress\nAPP_TITLE=${APP_}\n"
    line = source.splitlines()[1]
    char = line.index("${APP_") + len("${APP_")
    ctx = dotenv_context_at(source, 1, char)
    assert ctx is not None
    assert ctx.kind == "env"
    assert ctx.prefix == "APP_"
    labels = {
        item.label for item in completions(progress_index, source, 1, char, language="dotenv")
    }
    assert "APP_NAME" in labels

    # Typing a new key at the start of a line still offers known names.
    key_line = "DB_\n"
    key_ctx = dotenv_context_at(key_line, 0, 3)
    assert key_ctx is not None
    key_labels = {
        item.label for item in completions(progress_index, key_line, 0, 3, language="dotenv")
    }
    assert "DB_CONNECTION" in key_labels or "DB_DATABASE" in key_labels


def test_migration_schema_replays_create_alter_and_method_blueprints() -> None:
    tables = discover_migration_schema(PROGRESS)
    assert "posts" in tables
    assert "users" in tables
    assert "slug" in tables["posts"].columns
    assert tables["posts"].columns["slug"].type == "string"
    assert "email" in tables["users"].columns
    # Soft deletes and timestamps expand to their fixed names.
    assert "deleted_at" in tables["posts"].columns
    assert "created_at" in tables["posts"].columns
    # Morphs expand to _type / _id.
    assert "commentable_type" in tables["comments"].columns
    assert "commentable_id" in tables["comments"].columns


def test_model_tables_and_resolve_table() -> None:
    models = discover_model_tables(PROGRESS)
    assert models["posts"].model == "Post"
    assert "title" in models["posts"].columns
    tables = merge_tables(models, discover_migration_schema(PROGRESS))
    assert resolve_table("posts", tables) == "posts"
    assert resolve_table("Post", tables) == "posts"
    assert resolve_table("Missing", tables) is None


def test_table_and_column_completion(progress_index) -> None:
    table_source = 'q = DB.table("")'
    table_labels = {
        item.label
        for item in completions(
            progress_index,
            table_source,
            0,
            table_source.index('("")') + 2,
            language="python",
        )
    }
    assert "posts" in table_labels
    assert "users" in table_labels

    column_source = 'rows = DB.table("posts").where("")'
    column_labels = {
        item.label
        for item in completions(
            progress_index,
            column_source,
            0,
            len(column_source) - 2,
            language="python",
        )
    }
    assert "title" in column_labels
    assert "slug" in column_labels

    model_source = 'rows = Post.where("")'
    model_labels = {
        item.label
        for item in completions(
            progress_index,
            model_source,
            0,
            len(model_source) - 2,
            language="python",
        )
    }
    assert "slug" in model_labels

    has_column = 'ok = await Schema.has_column("users", "")'
    user_labels = {
        item.label
        for item in completions(
            progress_index,
            has_column,
            0,
            len(has_column) - 2,
            language="python",
        )
    }
    assert "email" in user_labels


def test_column_definition_and_hover(progress_index) -> None:
    source = 'rows = DB.table("posts").order_by("slug")'
    loc = definition(
        progress_index,
        source,
        0,
        source.index("slug") + 1,
        language="python",
    )
    assert loc is not None
    assert "add_slug_to_posts" in loc.path.name

    tip = hover(
        progress_index,
        source,
        0,
        source.index("slug") + 1,
        language="python",
    )
    assert tip is not None
    assert "posts.slug" in tip.contents

    table_tip = hover(
        progress_index,
        source,
        0,
        source.index("posts") + 1,
        language="python",
    )
    assert table_tip is not None
    assert "**table**" in table_tip.contents


def test_find_database_calls_capture_table_hints() -> None:
    source = 'rows = DB.table("posts").where("title").order_by("slug")'
    calls = find_database_calls(source)
    kinds = {(call.kind, call.value, call.table) for call in calls}
    assert ("table", "posts", None) in kinds
    assert ("column", "title", "posts") in kinds
    assert ("column", "slug", "posts") in kinds

    ctx = context_at(source, 0, source.index("title") + 1, language="python")
    assert ctx is not None
    assert ctx.kind == "column"
    assert ctx.table == "posts"

    open_ctx = call_at(source, 0, source.index("posts") + 1, language="python")
    assert open_ctx is not None
    assert open_ctx.kind == "table"


def test_migration_replay_handles_drop_rename_and_merge(tmp_path: Path) -> None:
    from almasix.lsp.schema_context import ColumnInfo, TableInfo, merge_tables

    migrations = tmp_path / "database" / "migrations"
    migrations.mkdir(parents=True)
    (migrations / "2024_01_01_000000_shape.py").write_text(
        """
from almasix.orm.schema import Schema


def up():
    Schema.create("widgets", lambda table: (
        table.id(),
        table.string("name"),
        table.timestamps(),
        table.soft_deletes(),
        table.morphs("owner"),
    ))
    Schema.table("widgets", lambda table: (
        table.rename_column("name", "title"),
        table.drop_column("title"),
        table.string("sku"),
        table.drop_morphs("owner"),
        table.drop_soft_deletes(),
        table.drop_timestamps(),
    ))
""",
        encoding="utf-8",
    )
    tables = discover_migration_schema(tmp_path)
    assert "widgets" in tables
    cols = tables["widgets"].columns
    assert "sku" in cols
    assert "name" not in cols
    assert "title" not in cols
    assert "owner_type" not in cols
    assert "deleted_at" not in cols

    modelish = {
        "widgets": TableInfo(
            name="widgets",
            columns={
                "extra": ColumnInfo(
                    name="extra",
                    table="widgets",
                    type="",
                    source="model",
                )
            },
            source="model",
            model="Widget",
        )
    }
    merged = merge_tables(modelish, tables)
    assert "sku" in merged["widgets"].columns
    assert "extra" in merged["widgets"].columns
    assert merged["widgets"].model == "Widget"
    assert resolve_table("widgets", merged) == "widgets"
    assert resolve_table("Widget", merged) == "widgets"
    assert resolve_table("missing", merged) is None
